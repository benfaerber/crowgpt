"""The public can-you-tell listening test, recorder and all."""

import json
from pathlib import Path
import numpy as np

from crowgpt.pages.base import _CSS, _peaks, _wav_data_uri


class DemoPage:
    """Renders the trials, the score strip, the method note and the recorder.

    THE SCORE USED TO LIVE IN A VARIABLE AND NOWHERE ELSE. The page has always
    been a real forced-choice instrument and it has never once kept a reading:
    close the tab and the sitting was gone. So the answers are now written down
    — per trial, with how long the decision took and how many times the clip was
    played — and carry a hash of the weights they judged, so several short
    sittings on one checkpoint pool into a single verdict and two sittings on
    different weights cannot be silently averaged.

    Saving is local on purpose. This file opens from a disk, works on a phone
    with no network and needs no server, and posting a few kilobytes of JSON to
    the field server would trade all of that away for nothing.
    """

    def __init__(self, clips, facts, seed=0, title=None, checkpoint=None):
        self.rng = np.random.default_rng(seed)
        self.facts = facts
        self.title = title
        self.checkpoint = checkpoint or {}
        self.trials = self._build(clips)

    def _build(self, clips):
        order = list(clips)
        self.rng.shuffle(order)
        trials = []
        for i, clip in enumerate(order, 1):
            uri, samples = _wav_data_uri(clip["audio"], clip.get("sr", 24000))
            trials.append(
                {
                    "n": i,
                    "clip_id": clip.get("clip_id", i - 1),
                    "condition_index": clip.get("condition_index"),
                    "arm": clip["arm"],
                    "truth": "generated" if clip["arm"] == "C_generated" else "real",
                    "slug": clip["species"],
                    "species": clip["species"].replace("-", " ").title(),
                    # Per-trial, so one sitting can judge two checkpoints. A
                    # cross-session comparison is confounded by everything about
                    # the listener that changed in between, and on 2026-08-01
                    # that was 8.3 points on identical weights — larger than the
                    # model effect under test. Interleaved, practice and time of
                    # day are shared and cancel.
                    "checkpoint": clip.get("checkpoint"),
                    "conf": clip.get("conf"),
                    "called": clip.get("called"),
                    "audio": uri,
                    "peaks": _peaks(samples),
                }
            )
        return trials

    def render(self):
        page = (
            _TEMPLATE.replace("__TRIALS__", json.dumps(self.trials))
            .replace("__FACTS__", json.dumps(self.facts))
            .replace("__CHECKPOINT__", json.dumps(self.checkpoint))
        )
        if self.title:
            page = page.replace("<title>CrowGPT — can you tell?</title>",
                                f"<title>{self.title}</title>", 1)
        return page

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


# The page's own chrome around the shared stylesheet; base.py owns _CSS now,
# so the one-source-of-truth arrow points the other way than it used to.
_TEMPLATE = (
    r"""<meta charset="utf-8">
<title>CrowGPT — can you tell?</title>
"""
    + _CSS
    + r"""

<div class="wrap">
  <p class="eyebrow">Cawtalker · listening test</p>
  <h1>Which of these is a real crow?</h1>
  <p class="lede">Half of the clips below are field recordings from a public sound archive that the model
    has never heard. The other half it invented. Guess before you reveal — the score only
    means something if you commit first.</p>
  <p class="caveat">Every clip is three seconds, sat in real ambience so they get identical
    treatment. Species labels appear only after you answer.</p>
  <p class="keyhint">Keyboard: <b>&larr;</b> real &nbsp; <b>&rarr;</b> generated &nbsp;
    <b>space</b> replay &nbsp; — they apply to the highlighted row, which advances itself.</p>

  <div class="score">
    <div><span>Your score</span><b id="score">0 / 0</b></div>
    <div><span>Chance</span><b id="chance">50%</b></div>
    <div><span>Remaining</span><b id="left">0</b></div>
  </div>

  <div id="trials"></div>

  <div class="recorder">
    <h2>Save this sitting</h2>
    <p>Answers are kept in this browser as you go, but they only become a measurement
      once the file is saved into <code>results/listening/</code>. Anything worth saying
      in words goes in the box — it is attached to the exact weights you just judged.</p>
    <textarea id="note" placeholder="What did it sound like? Which ones gave themselves away?"></textarea>
    <div class="choices">
      <button id="download">Download</button>
      <button id="copy">Copy</button>
      <span id="saved"></span>
    </div>
    <textarea id="payload" readonly></textarea>
  </div>

  <div class="method">
    <h2>How this was made</h2>
    <dl class="facts" id="facts"></dl>
    <p>A small transformer trained from scratch on call bouts cut out of the archive
      corpus by energy segmentation, with no human labelling anywhere in the loop. Audio is
      tokenised with a neural codec; the model predicts the tokens and the codec's decoder
      turns them back into sound.</p>
    <p>The training audio was selected by BirdNET, which is a bootstrap rather than a call
      detector — a minority of what it kept is not crow, and the model inherits that. Clips
      are shown at 16 kHz, which throws away nothing: 96.8% of corvid call units roll off
      below 8 kHz.</p>
  </div>
</div>

<script>
const TRIALS = __TRIALS__;
const FACTS = __FACTS__;
const CHECKPOINT = __CHECKPOINT__;

class Recorder {
  constructor(checkpoint, total) {
    this.checkpoint = checkpoint;
    this.total = total;
    this.id = Math.random().toString(36).slice(2, 10);
    this.startedAt = new Date().toISOString();
    this.answers = new Map();
    this.key = "crowgpt.session." + (checkpoint.fingerprint || "unknown") + "." + this.id;
  }

  record(trial, answer, timing) {
    this.answers.set(trial.n, {
      trial_index: trial.n,
      clip_id: trial.clip_id,
      condition_index: trial.condition_index,
      checkpoint: trial.checkpoint || null,
      arm: trial.arm,
      species: trial.slug,
      truth: trial.truth,
      answer: answer,
      correct: answer === trial.truth,
      decision_ms: timing.decisionMs,
      plays: timing.plays,
    });
    this.autosave();
  }

  payload() {
    return {
      session_id: this.id,
      subject: "ben",
      started_at: this.startedAt,
      finished_at: new Date().toISOString(),
      answered: this.answers.size,
      of: this.total,
      note: document.getElementById("note").value,
      checkpoint: this.checkpoint,
      trials: [...this.answers.values()].sort((a, b) => a.trial_index - b.trial_index),
    };
  }

  text() { return JSON.stringify(this.payload(), null, 2); }

  /* Insurance against a closed tab, never the record of truth — a sitting only
     counts once its file lands in results/listening/. */
  autosave() {
    try { localStorage.setItem(this.key, this.text()); } catch (e) { /* private mode */ }
  }

  filename() {
    return "session-" + (this.checkpoint.name || "model") + "-" + this.id + ".json";
  }

  download() {
    const blob = new Blob([this.text()], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = this.filename();
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

const recorder = new Recorder(CHECKPOINT, TRIALS.length);

const factsEl = document.getElementById("facts");
for (const [label, value] of Object.entries(FACTS)) {
  const cell = document.createElement("div");
  const dt = document.createElement("dt"); dt.textContent = label;
  const dd = document.createElement("dd"); dd.textContent = value;
  cell.append(dt, dd); factsEl.append(cell);
}

let answered = 0, correct = 0;
const scoreEl = document.getElementById("score");
const leftEl = document.getElementById("left");
leftEl.textContent = TRIALS.length;

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

/* Keyboard answering, because sixty trials is sixty round trips of the mouse.
   Arrows act on the highlighted row, which is always the first unanswered one
   and advances itself, so a whole sitting can be done without pointing at
   anything. The mouse still works exactly as before. */
const ROWS = [], ANSWER = [], TOGGLE = [], DONE = [];
let cursor = 0;

/* A waveform you can read before answering is a way to pass this test with the
   sound off: generated bouts run shorter and flatter than real ones, and the
   shape gives that away. Level is already equalised by the ambience step, so
   the shape was the last leak. Until a trial is answered its canvas draws a
   flat bar — still a playback progress indicator, carrying nothing about the
   clip. The real waveform arrives with the verdict. */
const SHAPES = TRIALS.map(trial => trial.peaks.map(() => 0.3));

TRIALS.forEach((trial, index) => {
  const row = document.createElement("div");
  row.className = "trial";
  let plays = 0, firstPlay = null;

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
  const realBtn = document.createElement("button"); realBtn.textContent = "Real";
  const fakeBtn = document.createElement("button"); fakeBtn.textContent = "Generated";
  choices.append(realBtn, fakeBtn);

  const controls = document.createElement("div");
  controls.className = "controls";
  controls.append(play, choices);

  row.append(idx, canvas, controls);
  document.getElementById("trials").append(row);
  ROWS.push(row);
  requestAnimationFrame(() => draw(canvas, SHAPES[index], 0));

  play.addEventListener("click", () => {
    if (playing && playing !== audio) { playing.pause(); playing.currentTime = 0; }
    if (audio.paused) {
      audio.play(); playing = audio; play.setAttribute("aria-pressed", "true");
      plays += 1;
      if (firstPlay === null) firstPlay = performance.now();
    }
    else { audio.pause(); play.setAttribute("aria-pressed", "false"); }
  });
  audio.addEventListener("timeupdate", () => draw(canvas, SHAPES[index], audio.currentTime / (audio.duration || 3)));
  audio.addEventListener("ended", () => { play.setAttribute("aria-pressed", "false"); draw(canvas, SHAPES[index], 0); });

  function answer(guess) {
    const hit = guess === trial.truth;
    answered += 1; if (hit) correct += 1;
    scoreEl.textContent = correct + " / " + answered;
    leftEl.textContent = TRIALS.length - answered;

    recorder.record(trial, guess, {
      decisionMs: firstPlay === null ? null : Math.round(performance.now() - firstPlay),
      plays: plays,
    });
    SHAPES[index] = trial.peaks;
    draw(canvas, SHAPES[index], 0);

    const verdict = document.createElement("span");
    verdict.className = "verdict " + (hit ? "right" : "wrong");
    verdict.textContent = (hit ? "✓ " : "✗ ") + trial.truth;
    choices.replaceWith(verdict);

    const meta = document.createElement("div");
    meta.className = "meta";
    const conf = trial.conf === null || trial.conf === undefined ? "—" : trial.conf.toFixed(2);
    meta.textContent = trial.species + " · BirdNET " + conf +
      (trial.called ? " · heard as " + trial.called : " · not detected");
    row.append(meta);
  }

  /* One path for both mouse and keyboard, so the highlight cannot drift out of
     step with what has actually been answered. */
  function complete(guess) {
    if (DONE[index]) return;
    answer(guess);
    DONE[index] = true;
    if (index === cursor) {
      const next = DONE.findIndex(done => !done);
      cursor = next === -1 ? cursor : next;
      highlight();
    }
  }

  realBtn.addEventListener("click", () => complete("real"));
  fakeBtn.addEventListener("click", () => complete("generated"));
  ANSWER.push(complete);
  TOGGLE.push(() => play.click());
  DONE.push(false);
});

function highlight() {
  ROWS.forEach((row, i) => row.classList.toggle("current", i === cursor));
  const row = ROWS[cursor];
  if (row) row.scrollIntoView({block: "center", behavior: "smooth"});
}

document.addEventListener("keydown", event => {
  /* The note box is a text field on the same page; typing in it must not
     answer trials. */
  const tag = (event.target.tagName || "").toLowerCase();
  if (tag === "textarea" || tag === "input" || event.metaKey || event.ctrlKey) return;
  if (DONE[cursor] === undefined) return;

  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    if (DONE[cursor]) return;
    ANSWER[cursor](event.key === "ArrowLeft" ? "real" : "generated");
  } else if (event.key === " ") {
    event.preventDefault();
    TOGGLE[cursor]();
  }
});

highlight();

const savedEl = document.getElementById("saved");
function flash(message) {
  savedEl.textContent = message;
  setTimeout(() => { savedEl.textContent = ""; }, 4000);
}

document.getElementById("download").addEventListener("click", () => {
  recorder.download();
  flash("saved " + recorder.answers.size + " answers");
});

/* The mobile path: a file:// download is unreliable on a phone, and this page
   is meant to work on one. */
document.getElementById("copy").addEventListener("click", async () => {
  const text = recorder.text();
  const box = document.getElementById("payload");
  try {
    await navigator.clipboard.writeText(text);
    flash("copied " + recorder.answers.size + " answers");
  } catch (e) {
    box.style.display = "block";
    box.value = text;
    box.select();
    flash("select all and copy");
  }
});

window.addEventListener("resize", () => {
  document.querySelectorAll(".trial canvas").forEach((canvas, i) => draw(canvas, SHAPES[i], 0));
});
</script>
"""
)
