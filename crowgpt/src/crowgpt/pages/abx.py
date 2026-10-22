"""ABX discrimination: which of two clips matches the anchor."""

import json
from collections import defaultdict
from pathlib import Path
import numpy as np

from crowgpt.pages.base import _CSS, _wav_data_uri


class ABXPage:
    """Is X the same as A or as B? A discrimination task with no criterion in it.

    THE INSTRUMENT RatingPage IS NOT. RatingPage writes its criterion down —
    "Good: could be a real recording... Bad: robotic, xylophone-ish" — and that
    is as good as a rating task gets, but it is still a definition the listener
    has to hold in their head for 120 clips at about 2.3 seconds each. On
    2026-08-02 Ben reported having marked clips good "knowing it was AI but it
    was a good AI call", which is that definition slipping in the direction it
    always slips: toward the arm rather than toward the reference.

    Nothing here can slip, because there is no quality judgement anywhere in the
    task. Every trial is one bout rendered two ways; X is a byte-identical copy
    of one of them; the answer is which. Chance is exactly 50% and it does not
    depend on anything the listener believes. **A round-trip a listener cannot
    beat chance on is transparent — that is what the word means**, and it is not
    a claim a rating task can make, however it is worded.

    Four things this page does on purpose.

    NO WAVEFORMS. RatingPage hides the shape until a clip is rated; here the
    shape cannot be drawn at all. Three canvases side by side would let anyone
    match X to A or B by eye in a second, and the score would be a measurement
    of image comparison.

    A AND B SWAP. Which side carries the raw audio is redrawn per trial, so
    "A is always the good one" is not learnable and a listener who settles into
    always answering A scores exactly chance rather than exactly right.

    UNLIMITED REPLAY, and every play counted. The question is whether a
    difference is audible at all, not whether it survives a 2.3-second first
    impression, so nothing here is timed against the listener. Play counts go
    into the session because "correct after eleven plays" and "correct after
    two" are different findings about the same trial.

    THE ANSWER IS REVEALED. Learning to hear the artefact is not contamination
    here, it is the result: a difference that becomes obvious once you know what
    to listen for was never transparent. Split the session by trial index if the
    learning curve is the question.
    """

    def _balanced(self, count):
        """`count` labels, half "a" and half "b", in random order.

        NOT A COIN FLIP PER TRIAL, and the difference is not cosmetic. Independent
        flips left one build with 18 of 30 control trials answered "b", so a
        listener who heard nothing and pressed B every time would have scored
        0.600 — which is exactly the p = 0.049 significance threshold at n = 30,
        on the arm whose only job is to prove the sitting was working. A response
        bias could have certified a broken sitting. Balanced by construction, the
        best a fixed answer can do is 50% plus one trial.
        """
        labels = np.array(["a", "b"]).repeat([count - count // 2, count // 2])
        self.rng.shuffle(labels)
        return list(labels)

    def __init__(self, trials, facts, seed=0, title=None, balance_by=None):
        """`balance_by` names a key to balance within — normally "arm".

        Balancing globally is not enough when the arms are scored separately: a
        50/50 split over 120 trials still leaves each arm a hypergeometric draw,
        and it is the per-arm rate that gets tested against chance.
        """
        self.rng = np.random.default_rng(seed)
        self.facts = facts
        self.title = title or "Which one is X?"
        order = list(trials)
        self.rng.shuffle(order)

        groups = defaultdict(list)
        for position, trial in enumerate(order):
            groups[trial.get(balance_by) if balance_by else None].append(position)
        truths, references = [None] * len(order), [None] * len(order)
        for positions in groups.values():
            for position, truth, reference in zip(
                positions, self._balanced(len(positions)), self._balanced(len(positions))
            ):
                truths[position], references[position] = truth, reference

        self.trials = []
        for i, trial in enumerate(order, 1):
            reference, treated = trial["reference"], trial["treated"]
            sr = trial.get("sr", 24000)
            # Native rate, never the 16 kHz the other pages use — see
            # _wav_data_uri. Costs about half as much again in page size and
            # keeps the top of the spectrum, where a codec artefact may be the
            # only thing distinguishing the two clips.
            ref_uri, _ = _wav_data_uri(reference, sr, target_sr=None)
            trt_uri, _ = _wav_data_uri(treated, sr, target_sr=None)
            if ref_uri == trt_uri:
                # THE ONE FAILURE THAT LOOKS LIKE THE ANSWER. Two identical
                # renderings are unanswerable, so the trial scores chance — and
                # chance is precisely what this page is built to report as
                # "transparent". A codec silently passing audio through, an arm
                # wired to the wrong variable, or a difference that is pure gain
                # (`_wav_data_uri` peak-normalises, so level alone survives
                # nothing) would all arrive here and read as a positive result.
                raise ValueError(
                    f"trial {i} renders identically on both sides "
                    f"({trial.get('arm', 'unnamed')}, bout {trial.get('bout')}): "
                    "ABX on two copies of one clip measures nothing and scores "
                    "50%, which is the transparency verdict. Check the treatment "
                    "actually ran."
                )
            # Which side the untouched audio sits on, per trial.
            reference_is_a = references[i - 1] == "a"
            a_uri, b_uri = (ref_uri, trt_uri) if reference_is_a else (trt_uri, ref_uri)
            x_is_a = truths[i - 1] == "a"
            self.trials.append({
                "n": i,
                "clip_id": trial.get("clip_id", i - 1),
                "a": a_uri,
                "b": b_uri,
                # X IS A POINTER, NOT A THIRD CLIP. The page plays `trial[truth]`,
                # so X is the very same source as the side it belongs to and
                # cannot drift from it — a re-render would differ in the last
                # bits and hand the answer to anyone with a spectrogram, and a
                # copy is one refactor away from becoming a re-render. It also
                # takes a third off the page, which matters at 120 trials of
                # embedded audio on a phone.
                "truth": "a" if x_is_a else "b",
                "reference_side": "a" if reference_is_a else "b",
                "hidden": {k: v for k, v in trial.items()
                           if k not in ("reference", "treated", "sr")},
            })

    def render(self):
        return (_ABX_TEMPLATE
                .replace("__TRIALS__", json.dumps(self.trials))
                .replace("__FACTS__", json.dumps(self.facts))
                .replace("__TITLE__", json.dumps(self.title)))

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


_ABX_TEMPLATE = (
    '<meta charset="utf-8">\n<title>CrowGPT — which one is X?</title>\n'
    + _CSS
    + r"""
<style>
  .trial { grid-template-columns: auto 1fr; }
  .players { display: flex; gap: .45rem; flex-wrap: wrap; align-items: center; }
  .players button { font-family: var(--mono); min-width: 3.4rem; }
  .players .x { border-color: var(--accent); color: var(--accent); }
  .answers { display: flex; gap: .45rem; flex-wrap: wrap; align-items: center;
             margin-left: auto; }
  .trial.current { border-color: var(--accent); }
  .trial.current .idx { color: var(--accent); font-weight: 600; }
  .keyhint { font-family: var(--mono); font-size: .72rem; color: var(--soft); margin: .4rem 0 0; }
  .reveal { font-family: var(--mono); font-size: .7rem; color: var(--soft);
            grid-column: 2 / -1; margin-top: -.35rem; }
  .row2 { grid-column: 2 / -1; display: flex; gap: .6rem; flex-wrap: wrap;
          align-items: center; }
</style>

<div class="wrap">
  <p class="eyebrow">CrowGPT · ABX</p>
  <h1>Which one is X?</h1>
  <p class="lede">Three clips a trial, all of them the same bout. <b>A</b> and <b>B</b> are
    two different renderings of it. <b>X</b> is an exact copy of one of them. Say which.</p>
  <p class="lede">There is no quality judgement anywhere in this task. Nothing is good or
    bad, nothing is real or fake — X is either A or it is B, and that is the whole
    question. Chance is 50%.</p>
  <p class="caveat"><b>Play them as many times as you like — and do.</b> Nothing is
    timed. The way this task works is <b>X against A, then X against B, then back again</b>;
    one listen each is rarely enough for a small difference. In the last sitting three
    quarters of trials got exactly one play per clip and scored 51%, while the handful
    that got four or more scored far better. If a trial feels like a coin flip, replay
    before you call it one.</p>
  <p class="caveat"><b>Guess when you cannot tell.</b> A guessed trial is data — it is what
    50% is made of. Skipping the hard ones is what turns a transparency test into a test
    of the trials you found easy.</p>
  <p class="caveat">Which side is which is redrawn every trial, so answering A every time
    scores 50% and nothing else.</p>
  <p class="keyhint">Keyboard: <b>1</b> A &nbsp; <b>2</b> B &nbsp; <b>3</b> X &nbsp;
    <b>&larr;</b> X is A &nbsp; <b>&rarr;</b> X is B &nbsp; — they act on the highlighted row.</p>

  <div class="score">
    <div><span>Answered</span><b id="done">0 / 0</b></div>
    <div><span>Correct</span><b id="correct">0</b></div>
    <div><span>Rate</span><b id="rate">—</b></div>
  </div>
  <p id="status" class="caveat" role="alert"></p>

  <div id="trials"></div>

  <div class="recorder">
    <h2>Save this sitting</h2>
    <p>Answers only become a measurement once the file is on disk.</p>
    <textarea id="note" placeholder="Anything worth saying in words? What did the difference sound like, when you could hear one?"></textarea>
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

const answers = new Map();
const sessionId = Math.random().toString(36).slice(2, 10);
const startedAt = new Date().toISOString();

/* ONE MEDIA ELEMENT FOR THE WHOLE PAGE, and this is not a micro-optimisation.
   The first version built `new Audio(uri)` per clip and held every one of them
   in a closure — 360 elements at 120 trials, none ever reclaimable because they
   stayed referenced. Ben's first sitting died at trial 72: buttons simply
   stopped responding, with play counts and decision times normal right up to
   the last answered trial, which is what a browser hitting its media-element
   ceiling looks like from the outside. Swapping `src` on a single element caps
   the cost at one regardless of how long the sitting is. */
function announce(message) {
  const box = document.getElementById("status");
  if (box) box.textContent = message;
}

const player = new Audio();
let playingButton = null;
let loadedSource = null;
let generation = 0;

function stopPlaying() {
  /* Bumping the generation cancels any start still waiting on `canplay`. */
  generation += 1;
  player.pause();
  if (playingButton) playingButton.setAttribute("aria-pressed", "false");
  playingButton = null;
}
player.addEventListener("ended", stopPlaying);
player.addEventListener("error", stopPlaying);

/* TWO RULES, AND THEY PULL AGAINST EACH OTHER. Both were learned the hard way,
   one broken page each.

   1. NEVER SEEK BEFORE THE MEDIA LOADS. Assigning src starts an asynchronous
      load; `currentTime = 0` before it finishes throws InvalidStateError, which
      killed the whole click handler and left every button dead.

   2. NEVER LEAVE THE GESTURE TO FIX RULE 1. Waiting for `canplay` and playing
      from there does avoid the throw — and a browser then refuses the play()
      as autoplay, because it is no longer in the synchronous turn of a user
      click. The symptom is worse than a crash: aria-pressed flips, the handler
      completes, the promise rejects into a .catch, and there is simply no
      sound and nothing in the console.

   So play() stays here, inside the click, where the gesture is. Calling it
   before the load completes is fine and always was — the browser queues it and
   starts when data arrives. Only the SEEK needs guarding, and it is only ever
   needed to replay a source already loaded; a freshly assigned src begins at
   zero on its own. */
function playSource(source, button) {
  const wasThis = playingButton === button;
  stopPlaying();
  if (wasThis) return;
  playingButton = button;
  button.setAttribute("aria-pressed", "true");

  if (loadedSource !== source) {
    loadedSource = source;
    player.src = source;
  } else if (player.readyState >= 1) {
    try { player.currentTime = 0; } catch (e) { /* leave it where it is */ }
  }
  const started = player.play();
  if (started && started.catch) {
    started.catch(err => {
      /* Never swallow it. A silent rejection is exactly how the last two
         builds shipped mute, and the page is the only place Ben would see it. */
      if (err && err.name === "AbortError") return;   // normal on a fast reclick
      stopPlaying();
      announce("playback blocked: " + ((err && err.message) || err));
    });
  }
}

const ROWS = [], ANSWER = [], PLAY = [], DONE = [];
let cursor = 0;

TRIALS.forEach((trial, index) => {
  const row = document.createElement("div");
  row.className = "trial";

  const idx = document.createElement("div");
  idx.className = "idx"; idx.textContent = trial.n;

  const players = document.createElement("div");
  players.className = "players";

  let firstPlay = null;
  const plays = {a: 0, b: 0, x: 0};

  for (const role of ["a", "b", "x"]) {
    /* X plays the same source as the side it belongs to — see ABXPage. */
    const source = role === "x" ? trial[trial.truth] : trial[role];
    const button = document.createElement("button");
    button.textContent = role.toUpperCase();
    if (role === "x") button.className = "x";
    button.addEventListener("click", () => {
      const resumed = playingButton === button;
      playSource(source, button);
      if (resumed) return;
      plays[role] += 1;
      if (firstPlay === null) firstPlay = performance.now();
    });
    players.append(button);
  }

  const answersEl = document.createElement("div");
  answersEl.className = "answers";
  const isA = document.createElement("button"); isA.textContent = "X is A";
  const isB = document.createElement("button"); isB.textContent = "X is B";
  answersEl.append(isA, isB);

  function answer(choice) {
    if (DONE[index]) return;
    DONE[index] = true;
    stopPlaying();
    const correct = choice === trial.truth;
    answers.set(trial.n, {
      trial_index: trial.n, clip_id: trial.clip_id, answer: choice,
      truth: trial.truth, correct: correct, reference_side: trial.reference_side,
      decision_ms: firstPlay === null ? null : Math.round(performance.now() - firstPlay),
      /* WALL CLOCK PER TRIAL. Without it a page left open across a whole day
         is indistinguishable from a sitting done in one go: the first ABX
         session spanned 10h41m of which 7.4 minutes were decisions, and the
         only trace was start and finish timestamps nobody thought to subtract.
         A discrimination task assumes attention and playback conditions hold
         still, and over ten hours neither does. */
      answered_at: new Date().toISOString(),
      plays_a: plays.a, plays_b: plays.b, plays_x: plays.x,
      plays: plays.a + plays.b + plays.x,
      ...trial.hidden,
    });

    const verdict = document.createElement("span");
    verdict.className = "verdict " + (correct ? "right" : "wrong");
    verdict.textContent = correct ? "correct" : "wrong";
    answersEl.replaceWith(verdict);

    const meta = document.createElement("div");
    meta.className = "reveal";
    meta.textContent = "X was " + trial.truth.toUpperCase() + " · "
      + Object.entries(trial.hidden).filter(([k]) => k !== "clip_id")
          .map(([k, v]) => k + " " + v).join(" · ");
    row.append(meta);

    const total = answers.size;
    const right = [...answers.values()].filter(a => a.correct).length;
    document.getElementById("done").textContent = total + " / " + TRIALS.length;
    document.getElementById("correct").textContent = right;
    document.getElementById("rate").textContent = Math.round(100 * right / total) + "%";
    autosave();
    if (index === cursor) {
      const next = DONE.findIndex(d => !d);
      cursor = next === -1 ? cursor : next;
      highlight();
    }
  }

  isA.addEventListener("click", () => answer("a"));
  isB.addEventListener("click", () => answer("b"));

  row.append(idx, players, answersEl);
  document.getElementById("trials").append(row);
  ROWS.push(row);
  ANSWER.push(answer);
  PLAY.push(role => players.children[{a: 0, b: 1, x: 2}[role]].click());
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
  if (event.key === "1" || event.key === "2" || event.key === "3") {
    event.preventDefault();
    PLAY[cursor]({1: "a", 2: "b", 3: "x"}[event.key]);
  } else if (event.key === "ArrowLeft") {
    event.preventDefault(); ANSWER[cursor]("a");
  } else if (event.key === "ArrowRight") {
    event.preventDefault(); ANSWER[cursor]("b");
  }
});

function payload() {
  const done = [...answers.values()];
  return {
    session_id: sessionId, subject: "ben", kind: "abx", title: TITLE,
    started_at: startedAt, finished_at: new Date().toISOString(),
    answered: done.length, of: TRIALS.length,
    correct: done.filter(a => a.correct).length,
    note: document.getElementById("note").value,
    trials: done.sort((a, b) => a.trial_index - b.trial_index),
  };
}
function text() { return JSON.stringify(payload(), null, 2); }
function autosave() {
  try { localStorage.setItem("crowgpt.abx." + sessionId, text()); } catch (e) {}
}

const savedEl = document.getElementById("saved");
function flash(m) { savedEl.textContent = m; setTimeout(() => { savedEl.textContent = ""; }, 4000); }

document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([text()], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "abx-" + sessionId + ".json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  flash("saved " + answers.size + " answers");
});
document.getElementById("copy").addEventListener("click", async () => {
  const box = document.getElementById("payload");
  try { await navigator.clipboard.writeText(text()); flash("copied"); }
  catch (e) { box.style.display = "block"; box.value = text(); box.select(); flash("select all and copy"); }
});

document.getElementById("done").textContent = "0 / " + TRIALS.length;
highlight();
</script>
"""
)
