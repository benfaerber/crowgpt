"""Paired real-vs-generated trials with dosing and a rest lockout."""

import json
from pathlib import Path
import numpy as np

from crowgpt.pages.base import DEMO_SR, MIN_GRADEABLE_SECONDS, _CSS, _check_gradeable, _peaks, _wav_data_uri


def _by_pairing(pairs):
    """Positions grouped by which two arms they compare, order-insensitive."""
    groups = {}
    for position, pair in enumerate(pairs):
        key = tuple(sorted((pair["a"]["arm"], pair["b"]["arm"])))
        groups.setdefault(key, []).append(position)
    return groups


class PairPage:
    """Two clips, one question: which is less robotic.

    EXISTS BECAUSE ABSOLUTE RATING TURNED OUT TO BE CONTRAST-SENSITIVE. 0038
    caught `model-fair-k8` — identical weights — scoring 0.21 in one sitting and
    0.54 in the next while the real anchor sat at 0.92 in both, and across every
    repeated arm the score tracked the arm's RANK inside its sitting. A listener
    grades a clip against the company it is keeping, and no instruction reliably
    stops that. A forced choice has no company: the question is only ever A or B.

    It is also the more efficient estimator. Rating two arms separately carries
    two lots of binomial noise and then differences them; this estimates one
    quantity, P(A preferred), against a null of exactly 0.5.

    NEVER PAIR GENERATED AGAINST REAL AS A TEST ARM. Real rates 0.85-0.97 and
    generated 0.22, so the answer is known before the trial runs and the trial
    measures nothing. Ben's objection, and it is right. Real appears here only as
    CATCH TRIALS, scored separately: they confirm the listener is engaged and are
    excluded from every model comparison.

    SIDE IS RANDOMISED PER TRIAL and recorded, so a preference for the left
    button cannot be read as a preference for a model — and so the bias can be
    measured afterwards rather than assumed absent.
    """

    def __init__(self, pairs, facts, seed=0, title=None,
                 min_seconds=MIN_GRADEABLE_SECONDS, dose=None, rest_minutes=30):
        """`pairs` is [{a: clip, b: clip, catch: bool}], each clip
        {audio, sr, arm}. Which of a/b lands on the left is decided here.

        `min_seconds` refuses clips too short to grade — see 0044 and
        `_check_gradeable`. Pass 0 only with a reason.

        `dose` serves the sitting in blocks of that many trials with a
        `rest_minutes` lockout between them, because grading bad audio in one
        wall of trials is taxing enough that Ben built exactly this by hand
        (twenty at a time, thirty minutes out) before it lived here. Each
        block is saved through the normal export flow as its own sitting —
        listen.py already sums sittings on the same weights, so dosing costs
        the statistics nothing. The lockout is localStorage per page title,
        so reopening the file resumes where the last block left off.
        """
        self.rng = np.random.default_rng(seed)
        self.facts = facts
        self.title = title or "Which of these two is less robotic?"
        self.dose = int(dose or 0)
        self.rest_minutes = rest_minutes
        if min_seconds:
            _check_gradeable(
                [(c["audio"], c.get("sr", 24000))
                 for pair in pairs for c in (pair["a"], pair["b"])],
                "PairPage")
        order = list(pairs)
        self.rng.shuffle(order)
        # SIDES ARE BALANCED, NOT RANDOMISED, and 0041 is why. Ben chose the left
        # clip on 65% of decided trials (CI [0.53, 0.75], excludes 0.5) — a side
        # effect as large as the model effect under test. Random flipping only
        # makes that noise in expectation; over 32 trials it left one arm on the
        # left 14 times and the right 18, so the bias leaked straight into the
        # comparison and had to be corrected for afterwards.
        #
        # Exactly half of each arm-pairing is flipped instead, so a side
        # preference cancels BY CONSTRUCTION rather than on average. The
        # remainder of an odd group is decided by the rng, which is the only part
        # left to chance.
        # A 2x2, NOT TWO COIN FLIPS. Ben's question: "what if to correct the bias
        # it randomly plays left or right first?" — and he is pointing at
        # something the side balance alone cannot reach. Until now the left clip
        # was ALWAYS heard first, so "left bias" and "first-heard bias" were the
        # same measurement wearing two names, and no amount of balancing which
        # ARM sits left tells them apart.
        #
        # So side and play order are balanced independently and jointly: each
        # pairing gets its four (side, order) cells in equal numbers. That makes
        # both effects estimable from the same sitting rather than confounded,
        # and cancels whichever one turns out to be real.
        flips, firsts = {}, {}
        cells = [(False, "left"), (True, "right"), (False, "right"), (True, "left")]
        for key, group in _by_pairing(order).items():
            plan = [cells[i % 4] for i in range(len(group))]
            self.rng.shuffle(plan)
            for position, (mark, first) in zip(group, plan):
                flips[position] = mark
                firsts[position] = first
        self.trials = []
        for i, pair in enumerate(order, 1):
            flip = flips[i - 1]
            left, right = (pair["b"], pair["a"]) if flip else (pair["a"], pair["b"])
            left_uri, left_samples = _wav_data_uri(left["audio"], left.get("sr", 24000))
            right_uri, right_samples = _wav_data_uri(right["audio"], right.get("sr", 24000))
            self.trials.append({
                "n": i,
                "first": firsts[i - 1],
                "left": {"audio": left_uri, "peaks": _peaks(left_samples)},
                "right": {"audio": right_uri, "peaks": _peaks(right_samples)},
                # Read only after the answer is in, never shown before it.
                #
                # DURATION IS RECORDED BECAUSE IT DECIDES TRIALS. Ben, after
                # 0044: "too short clips instantly loose. 0.1 second is always
                # worse." Generated bouts run from 0.08 s to about 3 s, so a
                # pairing that happens to put a fragment against a full bout is
                # answered on length rather than on timbre — and without the
                # number here that cannot even be checked afterwards, which is
                # exactly the hole 0041's side bias would have fallen into.
                "left_seconds": round(len(left_samples) / DEMO_SR, 3),
                "right_seconds": round(len(right_samples) / DEMO_SR, 3),
                "hidden": {
                    "left_arm": left["arm"], "right_arm": right["arm"],
                    "flipped": flip, "catch": bool(pair.get("catch", False)),
                    "played_first": firsts[i - 1],
                    "left_seconds": round(len(left_samples) / DEMO_SR, 3),
                    "right_seconds": round(len(right_samples) / DEMO_SR, 3),
                },
            })

    def render(self):
        import hashlib

        page_key = hashlib.md5(
            f"{self.title}|{len(self.trials)}".encode()).hexdigest()[:12]
        return (_PAIR_TEMPLATE
                .replace("__TRIALS__", json.dumps(self.trials))
                .replace("__FACTS__", json.dumps(self.facts))
                .replace("__TITLE__", json.dumps(self.title))
                .replace("__DOSE__", str(self.dose))
                .replace("__REST_MS__", str(int(self.rest_minutes * 60_000)))
                .replace("__PAGE_KEY__", json.dumps(page_key)))

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


_PAIR_TEMPLATE = (
    '<meta charset="utf-8">\n<title>CrowGPT — which is less robotic?</title>\n'
    + _CSS
    + r"""
<style>
  .pair { display: grid; grid-template-columns: 2.2rem 1fr 1fr; gap: .7rem;
          align-items: center; border: 1px solid var(--line); border-radius: 8px;
          padding: .7rem .9rem; margin-bottom: .55rem; }
  .pair.current { border-color: var(--accent); }
  .pair.current .idx { color: var(--accent); font-weight: 600; }
  .side { display: flex; align-items: center; gap: .5rem; }
  .side canvas { flex: 1; height: 34px; }
  .verdict-row { grid-column: 2 / -1; display: flex; gap: .5rem; align-items: center; }
  .reveal { font-family: var(--mono); font-size: .7rem; color: var(--soft);
            grid-column: 2 / -1; margin-top: -.2rem; }
  .keyhint { font-family: var(--mono); font-size: .72rem; color: var(--soft); margin: .4rem 0 0; }
</style>

<div class="wrap">
  <p class="eyebrow">CrowGPT · pairwise</p>
  <h1>Which of these two is less robotic?</h1>
  <p class="lede">Two clips a trial, played in a random order. Pick the one that sounds <b>less</b> synthetic —
    less robotic, garbled, xylophone-ish, modem-ish. Both may be bad; say which is
    <i>less</i> bad anyway. That is the whole question and there is no scale.</p>
  <p class="caveat"><b>This replaces rating them out of ten in your head.</b> An
    absolute judgement moves with whatever else is in the sitting — the same model
    scored 0.21 and 0.54 in consecutive sittings for that reason. A direct
    comparison has nothing to drift against, so answer only "this one over that
    one" and never "how good was it".</p>
  <p class="caveat"><b>Do not choose on how many caws you hear.</b> Density is
    measured elsewhere and choosing on it would make this circular.</p>
  <p class="caveat">Waveforms stay flat until you answer. The shape gives away the
    thing being tested.</p>
  <p class="keyhint">Keyboard: <b>&larr;</b> left &nbsp; <b>&rarr;</b> right &nbsp;
    <b>&darr;</b> too close to call &nbsp; <b>space</b> play both &nbsp;
    <b>a</b>/<b>d</b> play left / right</p>

  <div class="score">
    <div><span>Answered</span><b id="done">0 / 0</b></div>
  </div>

  <div id="trials"></div>

  <div class="recorder">
    <h2>Save this sitting</h2>
    <p>Answers only become a measurement once the file is on disk.</p>
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

const factsEl = document.getElementById("facts");
for (const [label, value] of Object.entries(FACTS)) {
  const cell = document.createElement("div");
  const dt = document.createElement("dt"); dt.textContent = label;
  const dd = document.createElement("dd"); dd.textContent = value;
  cell.append(dt, dd); factsEl.append(cell);
}

/* DOSING. A sitting served as one wall of trials is taxing enough that Ben
   rationed it by hand (twenty at a time, thirty minutes out) before it lived
   here: DOSE trials per block, REST_MS locked out between blocks, the block
   index in localStorage under the page's key so reopening the file resumes.
   Each block is exported as its own sitting — listen.py sums sittings on the
   same weights, so a dosed sitting and a monolithic one are the same
   measurement. DOSE = 0 disables all of it. */
const DOSE = __DOSE__;
const REST_MS = __REST_MS__;
const PAGE_KEY = __PAGE_KEY__;
const DOSE_STORE = "crowgpt.dose." + PAGE_KEY;
const BLOCKS = DOSE > 0 ? Math.ceil(TRIALS.length / DOSE) : 1;
let doseState = {block: 0, resumeAt: 0};
if (DOSE > 0) {
  try { doseState = {...doseState, ...JSON.parse(localStorage.getItem(DOSE_STORE) || "{}")}; }
  catch (e) {}
}
const BLOCK = Math.min(doseState.block, BLOCKS);
const LO = DOSE > 0 ? BLOCK * DOSE : 0;
const HI = DOSE > 0 ? Math.min(LO + DOSE, TRIALS.length) : TRIALS.length;

function restScreen(message, resumeAt) {
  const host = document.getElementById("trials");
  const card = document.createElement("div");
  card.className = "section";
  const words = document.createElement("p");
  words.className = "lede";
  words.textContent = message;
  card.append(words);
  if (resumeAt) {
    const clock = document.createElement("p");
    clock.className = "keyhint";
    card.append(clock);
    const tick = () => {
      const left = resumeAt - Date.now();
      if (left <= 0) { location.reload(); return; }
      clock.textContent = "unlocks in " + Math.ceil(left / 60000) + " min ("
        + new Date(resumeAt).toLocaleTimeString() + ")";
      setTimeout(tick, 5000);
    };
    tick();
  }
  host.append(card);
  document.querySelector(".recorder").style.display = "none";
  return true;
}

const RESTING = DOSE > 0 && (
  BLOCK >= BLOCKS
    ? restScreen("This sitting is complete — every block is answered.")
    : (Date.now() < doseState.resumeAt
        && restScreen("Block " + BLOCK + " of " + BLOCKS + " is saved. Resting "
                      + "— grading in walls is how sittings lose their power.",
                      doseState.resumeAt)));

const answers = new Map();
const sessionId = Math.random().toString(36).slice(2, 10);
const startedAt = new Date().toISOString();
let playing = null, cursor = 0;
const ROWS = [], PICK = [], PLAY = [], MEDIA = [], COUNT = [], MARK = [], DONE = [];
const ORDER = TRIALS.map(t => t.first);
let chainCleanup = null;
const SHAPES = TRIALS.map(t => [t.left.peaks.map(() => 0.3), t.right.peaks.map(() => 0.3)]);

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

TRIALS.forEach((trial, index) => {
  const row = document.createElement("div");
  row.className = "pair";
  const idx = document.createElement("span");
  idx.className = "idx";
  idx.textContent = String(trial.n).padStart(2, "0");
  row.append(idx);

  const plays = {left: 0, right: 0};
  let firstPlay = null;
  const media = {};
  for (const side of ["left", "right"]) {
    const box = document.createElement("div");
    box.className = "side";
    const btn = document.createElement("button");
    btn.className = "play";
    btn.setAttribute("aria-label", "Play " + side + " clip " + trial.n);
    btn.textContent = side === "left" ? "◀ ▶" : "▶ ▶";
    const canvas = document.createElement("canvas");
    const audio = new Audio(trial[side].audio);
    audio.preload = "none";
    media[side] = {audio: audio, canvas: canvas};
    btn.addEventListener("click", () => {
      cancelChain();
      if (playing && playing !== audio) { playing.pause(); playing.currentTime = 0; }
      if (audio.paused) {
        audio.play(); playing = audio;
        plays[side] += 1;
        if (firstPlay === null) firstPlay = performance.now();
      } else audio.pause();
    });
    audio.addEventListener("timeupdate", () => draw(
      canvas, SHAPES[index][side === "left" ? 0 : 1],
      audio.currentTime / (audio.duration || 3)));
    audio.addEventListener("ended", () => draw(
      canvas, SHAPES[index][side === "left" ? 0 : 1], 0));
    box.append(btn, canvas);
    row.append(box);
  }

  const verdictRow = document.createElement("div");
  verdictRow.className = "verdict-row";
  const bothBtn = document.createElement("button");
  bothBtn.textContent = "▶ Both";
  bothBtn.addEventListener("click", () => playBoth(index));
  const leftBtn = document.createElement("button"); leftBtn.textContent = "← Left";
  const tieBtn = document.createElement("button"); tieBtn.textContent = "Too close";
  const rightBtn = document.createElement("button"); rightBtn.textContent = "Right →";
  verdictRow.append(bothBtn, leftBtn, tieBtn, rightBtn);
  row.append(verdictRow);

  document.getElementById("trials").append(row);
  ROWS.push(row);
  requestAnimationFrame(() => {
    draw(media.left.canvas, SHAPES[index][0], 0);
    draw(media.right.canvas, SHAPES[index][1], 0);
  });

  function pick(choice) {
    if (DONE[index]) return;
    DONE[index] = true;
    const hidden = trial.hidden;
    answers.set(trial.n, {
      trial_index: trial.n,
      chose: choice,
      winner_arm: choice === "tie" ? null
        : (choice === "left" ? hidden.left_arm : hidden.right_arm),
      loser_arm: choice === "tie" ? null
        : (choice === "left" ? hidden.right_arm : hidden.left_arm),
      decision_ms: firstPlay === null ? null : Math.round(performance.now() - firstPlay),
      plays_left: plays.left, plays_right: plays.right,
      ...hidden,
    });
    SHAPES[index] = [trial.left.peaks, trial.right.peaks];
    draw(media.left.canvas, SHAPES[index][0], 0);
    draw(media.right.canvas, SHAPES[index][1], 0);
    const said = document.createElement("span");
    said.className = "verdict " + (choice === "tie" ? "" : "right");
    said.textContent = choice === "tie" ? "too close" : choice;
    verdictRow.replaceWith(said);
    const meta = document.createElement("div");
    meta.className = "reveal";
    meta.textContent = "left " + hidden.left_arm + " · right " + hidden.right_arm
      + (hidden.catch ? " · catch" : "");
    row.append(meta);
    document.getElementById("done").textContent = answers.size + " / " + (HI - LO)
      + (DOSE > 0 ? "  ·  block " + (BLOCK + 1) + " of " + BLOCKS : "");
    autosave();
    if (DOSE > 0 && answers.size >= HI - LO) {
      const last = BLOCK + 1 >= BLOCKS;
      try {
        localStorage.setItem(DOSE_STORE, JSON.stringify(
          {block: BLOCK + 1, resumeAt: last ? 0 : Date.now() + REST_MS}));
      } catch (e) {}
      const note = document.createElement("p");
      note.className = "caveat";
      note.textContent = "Block " + (BLOCK + 1) + " of " + BLOCKS
        + " done — save it below. " + (last ? "That was the last block."
          : "The next block unlocks " + Math.round(REST_MS / 60000)
            + " minutes from now; reopen the page then.");
      document.querySelector(".recorder").prepend(note);
    }
    if (index === cursor) {
      const next = DONE.findIndex(d => !d);
      cursor = next === -1 ? cursor : next;
      highlight();
    }
  }

  leftBtn.addEventListener("click", () => pick("left"));
  tieBtn.addEventListener("click", () => pick("tie"));
  rightBtn.addEventListener("click", () => pick("right"));
  PICK.push(pick);
  PLAY.push(side => {
    cancelChain();
    const el = media[side].audio;
    if (el.paused) {
      if (playing && playing !== el) { playing.pause(); playing.currentTime = 0; }
      playing = el; plays[side] += 1;
      if (firstPlay === null) firstPlay = performance.now();
      el.play();
    } else el.pause();
  });
  MEDIA.push(media);
  COUNT.push(plays);
  MARK.push(() => { if (firstPlay === null) firstPlay = performance.now(); });
  /* Outside the current dose window a trial is invisible AND pre-answered,
     so the cursor, the keyboard and the block-complete check all skip it. */
  const outside = RESTING || (DOSE > 0 && (index < LO || index >= HI));
  if (outside) row.style.display = "none";
  DONE.push(outside);
});

/* SPACE PLAYS BOTH, IN SEQUENCE — it used to play only the left one while the
   key hint said "replay both", which is worse than a missing feature because
   the listener believes they heard the pair. They cannot overlap: two clips at
   once is not a comparison, so the right one starts when the left one ends. */
function cancelChain() {
  if (chainCleanup) { chainCleanup(); chainCleanup = null; }
}

function playBoth(index) {
  cancelChain();
  const media = MEDIA[index];
  if (playing) { playing.pause(); playing.currentTime = 0; }
  /* WHICH SIDE GOES FIRST IS PART OF THE DESIGN, not always the left one. See
     the 2x2 in PairPage: playing left first every time made "left bias" and
     "first-heard bias" indistinguishable. */
  const firstSide = ORDER[index], secondSide = firstSide === "left" ? "right" : "left";
  const first = media[firstSide].audio, second = media[secondSide].audio;
  first.currentTime = 0; second.currentTime = 0;
  const advance = () => {
    first.removeEventListener("ended", advance);
    chainCleanup = null;
    COUNT[index][secondSide] += 1;
    playing = second;
    second.play();
  };
  first.addEventListener("ended", advance);
  chainCleanup = () => first.removeEventListener("ended", advance);
  COUNT[index][firstSide] += 1;
  MARK[index]();
  playing = first;
  first.play();
}

function highlight() {
  ROWS.forEach((row, i) => row.classList.toggle("current", i === cursor));
  const row = ROWS[cursor];
  if (row) row.scrollIntoView({block: "center", behavior: "smooth"});
}

document.addEventListener("keydown", event => {
  const tag = (event.target.tagName || "").toLowerCase();
  if (tag === "textarea" || tag === "input" || event.metaKey || event.ctrlKey) return;
  if (DONE[cursor] === undefined) return;
  const key = event.key;
  if (key === "ArrowLeft" || key === "ArrowRight" || key === "ArrowDown") {
    event.preventDefault();
    PICK[cursor]({ArrowLeft: "left", ArrowRight: "right", ArrowDown: "tie"}[key]);
  } else if (key === "a" || key === "d") {
    event.preventDefault();
    PLAY[cursor](key === "a" ? "left" : "right");
  } else if (key === " ") {
    event.preventDefault();
    playBoth(cursor);
  }
});

function payload() {
  return {
    session_id: sessionId, subject: "ben", kind: "pairwise", title: TITLE,
    started_at: startedAt, finished_at: new Date().toISOString(),
    rated: answers.size, of: TRIALS.length,
    block: DOSE > 0 ? BLOCK + 1 : null,
    blocks: DOSE > 0 ? BLOCKS : null,
    note: document.getElementById("note").value,
    trials: [...answers.values()].sort((a, b) => a.trial_index - b.trial_index),
  };
}
function text() { return JSON.stringify(payload(), null, 2); }
function autosave() {
  try { localStorage.setItem("crowgpt.pairwise." + sessionId, text()); } catch (e) {}
}

const savedEl = document.getElementById("saved");
function flash(m) { savedEl.textContent = m; setTimeout(() => { savedEl.textContent = ""; }, 4000); }
document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([text()], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "pairwise-" + sessionId + ".json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  flash("saved " + answers.size + " answers");
});
document.getElementById("copy").addEventListener("click", async () => {
  const box = document.getElementById("payload");
  try { await navigator.clipboard.writeText(text()); flash("copied"); }
  catch (e) { box.style.display = "block"; box.value = text(); box.select(); flash("select all and copy"); }
});

document.getElementById("done").textContent = "0 / " + (HI - LO)
  + (DOSE > 0 ? "  ·  block " + (BLOCK + 1) + " of " + BLOCKS : "");
window.addEventListener("resize", () => {
  document.querySelectorAll(".pair").forEach((row, i) => {
    const canvases = row.querySelectorAll("canvas");
    if (canvases[0]) draw(canvases[0], SHAPES[i][0], 0);
    if (canvases[1]) draw(canvases[1], SHAPES[i][1], 0);
  });
});
cursor = Math.max(0, DONE.findIndex(d => !d));
highlight();
</script>
"""
)
