"""Graded -2..+2 responses over labelled rows, with a defect vocabulary."""

import json
from pathlib import Path
import numpy as np

from crowgpt.pages.base import _CSS, _peaks, _wav_data_uri


class RatingPage:
    """Rate each clip good or bad. The reason is hidden, and so is the waveform.

    Built to test one hypothesis: that what Ben hears as quality is unit count.
    On ten bouts from a single recording his good/bad split matched the burst
    count exactly — every clip he called bad held one unit, every good one held
    two to four — and he said so while looking at the waveforms, which is the
    problem this page exists to remove.

    THE WAVEFORM IS THE CONFOUND. He can read choppiness off the picture, so a
    page that draws it is asking him to count peaks rather than to listen. The
    canvas stays flat until a clip is rated, exactly as DemoPage hides it to stop
    the shape giving away real from generated, and for the same reason: the
    instrument must measure the ear.

    Nothing about the clip is shown before rating — not its unit count, not its
    duration, not whether a model made it.
    """

    #: (button label, recorded value) in negative / unsure / positive order.
    #: The recorded value lands verbatim in the saved session JSON, so an
    #: analysis never has to guess which button "good" meant on a page whose
    #: question was something else (0071 asks scream / no-scream).
    DEFAULT_LABELS = (("Bad", "bad"), ("Unsure", "unsure"), ("Good", "good"))

    def __init__(self, clips, facts, seed=0, title=None, labels=None,
                 instructions=None):
        self.rng = np.random.default_rng(seed)
        self.facts = facts
        self.title = title or "Which of these sound good?"
        self.labels = [list(pair) for pair in (labels or self.DEFAULT_LABELS)]
        self.instructions = instructions or _RATING_DEFAULT_INSTRUCTIONS
        order = list(clips)
        self.rng.shuffle(order)
        self.trials = []
        for i, clip in enumerate(order, 1):
            uri, samples = _wav_data_uri(clip["audio"], clip.get("sr", 24000))
            self.trials.append({
                "n": i,
                "clip_id": clip.get("clip_id", i - 1),
                "audio": uri,
                "peaks": _peaks(samples),
                # Everything below is written into the saved session and shown
                # only after the rating, so it cannot steer it.
                "hidden": {k: v for k, v in clip.items() if k not in ("audio", "sr")},
            })

    def render(self):
        return (_RATING_TEMPLATE
                .replace("__INSTRUCTIONS__", self.instructions)
                .replace("__TRIALS__", json.dumps(self.trials))
                .replace("__FACTS__", json.dumps(self.facts))
                .replace("__TITLE__", json.dumps(self.title))
                .replace("__LABELS__", json.dumps(self.labels)))

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


_RATING_DEFAULT_INSTRUCTIONS = """
  <h1>Which of these sound good?</h1>
  <p class="lede">One judgement per clip. There is no right answer and nothing is being
    scored.</p>
  <p class="lede"><b>Good</b> — could be a real recording, however poor a recording it is.
    Distant, noisy, quiet, muffled: still Good if a real bird could have made it.<br>
    <b>Bad</b> — robotic, xylophone-ish, modem-ish, synthetic. Caws present but robotic is
    <b>Bad</b>.<br>
    <b>Unsure</b> — genuinely cannot place it. A real answer, not a cop-out.</p>
  <p class="caveat"><b>Do not rate on how many caws you hear.</b> Density is a variable
    under test elsewhere, and rating on it would make these results circular. A clip with
    four caws that sounds synthetic is Bad; a clip with one distant caw that sounds real
    is Good.</p>
  <p class="caveat">The waveform stays flat until you rate, on purpose. The shape gives
    away the thing being tested, so this has to come from the ear alone.</p>
"""

_RATING_TEMPLATE = (
    '<meta charset="utf-8">\n<title>CrowGPT — rating</title>\n'
    + _CSS
    + r"""
<style>
  .controls { display: flex; align-items: center; gap: .6rem; }
  .trial.current { border-color: var(--accent); }
  .trial.current .idx { color: var(--accent); font-weight: 600; }
  .keyhint { font-family: var(--mono); font-size: .72rem; color: var(--soft); margin: .4rem 0 0; }
  .reveal { font-family: var(--mono); font-size: .7rem; color: var(--soft);
            grid-column: 2 / -1; margin-top: -.35rem; }
</style>

<div class="wrap">
  <p class="eyebrow">Cawtalker · rating</p>
__INSTRUCTIONS__
  <p class="keyhint" id="keyhint"></p>


  <div class="score">
    <div><span>Rated</span><b id="done">0 / 0</b></div>
    <div><span id="pos-label">Good</span><b id="good">0</b></div>
  </div>

  <div id="trials"></div>

  <div class="recorder">
    <h2>Save this sitting</h2>
    <p>Ratings only become a measurement once the file is on disk.</p>
    <textarea id="note" placeholder="Anything worth saying in words?"></textarea>
    <div class="choices">
      <button id="download">Download</button>
      <button id="copy">Copy</button>
      <span id="saved"></span>
    </div>
    <textarea id="payload" readonly></textarea>
  </div>

  <div class="method">
    <h2>What this is</h2>
    <dl class="facts" id="facts"></dl>
  </div>
</div>

<script>
const TRIALS = __TRIALS__;
const FACTS = __FACTS__;
const TITLE = __TITLE__;

/* [label, recorded value] in negative / unsure / positive order. */
const LABELS = __LABELS__;

document.getElementById("pos-label").textContent = LABELS[2][0];
document.getElementById("keyhint").innerHTML =
  "Keyboard: <b>&larr;</b> " + LABELS[0][0].toLowerCase() +
  " &nbsp; <b>&darr;</b> " + LABELS[1][0].toLowerCase() +
  " &nbsp; <b>&rarr;</b> " + LABELS[2][0].toLowerCase() +
  " &nbsp; <b>space</b> replay &nbsp; — they act on the highlighted row.";

const factsEl = document.getElementById("facts");
for (const [label, value] of Object.entries(FACTS)) {
  const cell = document.createElement("div");
  const dt = document.createElement("dt"); dt.textContent = label;
  const dd = document.createElement("dd"); dd.textContent = value;
  cell.append(dt, dd); factsEl.append(cell);
}

const ratings = new Map();
const sessionId = Math.random().toString(36).slice(2, 10);
const startedAt = new Date().toISOString();

function draw(canvas, peaks, progress) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const styles = getComputedStyle(document.documentElement);
  const dim = styles.getPropertyValue("--line").trim();
  const lit = styles.getPropertyValue("--accent").trim();
  const step = width / peaks.length;
  peaks.forEach((peak, i) => {
    const barHeight = Math.max(1.5, peak * (height - 4));
    ctx.fillStyle = (i / peaks.length) <= progress ? lit : dim;
    ctx.fillRect(i * step, (height - barHeight) / 2, Math.max(1, step - 1), barHeight);
  });
}

let playing = null;
const ROWS = [], RATE = [], TOGGLE = [], DONE = [];
let cursor = 0;
/* Flat until rated — the shape is the thing being tested. */
const SHAPES = TRIALS.map(t => t.peaks.map(() => 0.3));

TRIALS.forEach((trial, index) => {
  const row = document.createElement("div");
  row.className = "trial";

  const idx = document.createElement("span");
  idx.className = "idx";
  idx.textContent = String(trial.n).padStart(2, "0");

  const play = document.createElement("button");
  play.className = "play";
  play.setAttribute("aria-pressed", "false");
  play.setAttribute("aria-label", "Play clip " + trial.n);
  play.textContent = "▶";

  const canvas = document.createElement("canvas");
  const audio = new Audio(trial.audio);
  audio.preload = "none";

  const choices = document.createElement("div");
  choices.className = "choices";
  const badBtn = document.createElement("button"); badBtn.textContent = LABELS[0][0];
  const unsureBtn = document.createElement("button"); unsureBtn.textContent = LABELS[1][0];
  const goodBtn = document.createElement("button"); goodBtn.textContent = LABELS[2][0];
  choices.append(badBtn, unsureBtn, goodBtn);

  const controls = document.createElement("div");
  controls.className = "controls";
  controls.append(play, choices);

  row.append(idx, canvas, controls);
  document.getElementById("trials").append(row);
  ROWS.push(row);
  requestAnimationFrame(() => draw(canvas, SHAPES[index], 0));

  let plays = 0, firstPlay = null;
  play.addEventListener("click", () => {
    if (playing && playing !== audio) { playing.pause(); playing.currentTime = 0; }
    if (audio.paused) {
      audio.play(); playing = audio; play.setAttribute("aria-pressed", "true");
      plays += 1;
      if (firstPlay === null) firstPlay = performance.now();
    } else { audio.pause(); play.setAttribute("aria-pressed", "false"); }
  });
  audio.addEventListener("timeupdate", () => draw(canvas, SHAPES[index], audio.currentTime / (audio.duration || 3)));
  audio.addEventListener("ended", () => { play.setAttribute("aria-pressed", "false"); draw(canvas, SHAPES[index], 0); });

  function rate(verdict) {
    if (DONE[index]) return;
    DONE[index] = true;
    ratings.set(trial.n, {
      trial_index: trial.n, clip_id: trial.clip_id, rating: verdict,
      decision_ms: firstPlay === null ? null : Math.round(performance.now() - firstPlay),
      plays: plays, ...trial.hidden,
    });
    SHAPES[index] = trial.peaks;
    draw(canvas, SHAPES[index], 0);

    const verdictEl = document.createElement("span");
    verdictEl.className = "verdict " +
      (verdict === LABELS[2][1] ? "right" : verdict === LABELS[0][1] ? "wrong" : "");
    verdictEl.textContent = verdict;
    choices.replaceWith(verdictEl);

    const meta = document.createElement("div");
    meta.className = "reveal";
    meta.textContent = Object.entries(trial.hidden)
      .filter(([k]) => k !== "clip_id")
      .map(([k, v]) => k + " " + v).join(" · ");
    row.append(meta);

    document.getElementById("done").textContent = ratings.size + " / " + TRIALS.length;
    document.getElementById("good").textContent =
      [...ratings.values()].filter(r => r.rating === LABELS[2][1]).length;
    autosave();
    if (index === cursor) {
      const next = DONE.findIndex(d => !d);
      cursor = next === -1 ? cursor : next;
      highlight();
    }
  }

  badBtn.addEventListener("click", () => rate(LABELS[0][1]));
  unsureBtn.addEventListener("click", () => rate(LABELS[1][1]));
  goodBtn.addEventListener("click", () => rate(LABELS[2][1]));
  RATE.push(rate);
  TOGGLE.push(() => play.click());
  DONE.push(false);
});

function highlight() {
  ROWS.forEach((row, i) => row.classList.toggle("current", i === cursor));
  const row = ROWS[cursor];
  if (row) row.scrollIntoView({block: "center", behavior: "smooth"});
}

document.addEventListener("keydown", event => {
  const tag = (event.target.tagName || "").toLowerCase();
  if (tag === "textarea" || tag === "input" || event.metaKey || event.ctrlKey) return;
  if (DONE[cursor] === undefined) return;
  if (event.key === "ArrowLeft" || event.key === "ArrowRight" || event.key === "ArrowDown") {
    event.preventDefault();
    RATE[cursor]({ArrowLeft: LABELS[0][1], ArrowDown: LABELS[1][1],
                  ArrowRight: LABELS[2][1]}[event.key]);
  } else if (event.key === " ") {
    event.preventDefault();
    TOGGLE[cursor]();
  }
});

function payload() {
  return {
    session_id: sessionId, subject: "ben", kind: "rating", title: TITLE,
    started_at: startedAt, finished_at: new Date().toISOString(),
    rated: ratings.size, of: TRIALS.length,
    note: document.getElementById("note").value,
    trials: [...ratings.values()].sort((a, b) => a.trial_index - b.trial_index),
  };
}
function text() { return JSON.stringify(payload(), null, 2); }
function autosave() {
  try { localStorage.setItem("crowgpt.rating." + sessionId, text()); } catch (e) {}
}

const savedEl = document.getElementById("saved");
function flash(m) { savedEl.textContent = m; setTimeout(() => { savedEl.textContent = ""; }, 4000); }

document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([text()], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "rating-" + sessionId + ".json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  flash("saved " + ratings.size + " ratings");
});
document.getElementById("copy").addEventListener("click", async () => {
  const box = document.getElementById("payload");
  try { await navigator.clipboard.writeText(text()); flash("copied"); }
  catch (e) { box.style.display = "block"; box.value = text(); box.select(); flash("select all and copy"); }
});

document.getElementById("done").textContent = "0 / " + TRIALS.length;
window.addEventListener("resize", () => {
  document.querySelectorAll(".trial canvas").forEach((c, i) => draw(c, SHAPES[i], 0));
});
highlight();
</script>
"""
)
