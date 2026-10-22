"""One clip per call type, for hearing what the token conditions."""

import json
from pathlib import Path

from crowgpt.pages.base import _CSS, _peaks, _wav_data_uri


class CallTypePage:
    """What came out when each call type was asked for, next to the real thing.

    0021 measured this as a confusion matrix and the matrix is the evidence, but
    it cannot answer "does the begging actually sound like begging" — a head
    agreeing with a prefix token is not the same claim as a bird sounding right.
    So each section puts real held-out bouts of a type beside generated ones,
    unshuffled and labelled.

    NOT A TEST, deliberately, unlike DemoPage. There is nothing to guess and no
    score: the answer is written on every row, because the question here is what
    the conditioning sounds like rather than whether it fools anyone. Hiding the
    labels would only make it slower to read.
    """

    def __init__(self, sections, facts):
        self.facts = facts
        self.sections = []
        for section in sections:
            entry = {"type": section["type"], "note": section["note"], "real": [], "generated": []}
            for kind in ("real", "generated"):
                for clip in section[kind]:
                    uri, samples = _wav_data_uri(clip["audio"], clip.get("sr", 24000))
                    entry[kind].append({"audio": uri, "peaks": _peaks(samples),
                                        "label": clip["label"], "hit": clip.get("hit"),
                                        "heard": clip.get("heard")})
            self.sections.append(entry)

    def render(self):
        return _CALLTYPE_TEMPLATE.replace("__SECTIONS__", json.dumps(self.sections)).replace(
            "__FACTS__", json.dumps(self.facts)
        )

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


_CALLTYPE_TEMPLATE = (
    '<meta charset="utf-8">\n<title>CrowGPT — ask it for a call type</title>\n'
    + _CSS
    + r"""
<style>
  .section { margin-top: 2.75rem; }
  .section > h2 { font-family: var(--mono); font-size: 1.05rem; font-weight: 600;
                  letter-spacing: -.01em; margin: 0 0 .2rem; }
  .section > p { font-family: var(--mono); font-size: .74rem; color: var(--soft);
                 margin: 0 0 1rem; }
  .band { font-family: var(--mono); font-size: .66rem; letter-spacing: .14em;
          text-transform: uppercase; color: var(--soft); margin: 1.1rem 0 .45rem; }
  .trial .idx { min-width: 11rem; }
  .hit  { color: var(--right); }
  .miss { color: var(--wrong); }
</style>

<div class="wrap">
  <p class="eyebrow">CrowGPT · experiment 0021</p>
  <h1>Ask it for a call type</h1>
  <p class="lede">The generator takes a call type as part of its prompt. Each section below
    asks for one, and puts what came back beside real held-out bouts a person labelled with
    that same type. Nothing here is hidden — read the labels as you listen.</p>
  <p class="caveat">The tag on each generated row is what an independent classifier heard,
    not what was asked for. Green means it agreed with the request. That classifier scores
    90.3% on real held-out bouts, so it is worth listening to, but it has only ever seen
    3 real <i>call</i> and 5 real <i>song</i> examples — treat those two sections gently.</p>

  <div id="sections"></div>

  <div class="method">
    <h2>Measured</h2>
    <dl class="facts" id="facts"></dl>
    <p>Recall tracks training data almost too neatly: 26,876 alarm bouts give 92.9%,
      2,349 begging give 50.0%, 1,113 song give 16.4%, and 272 <i>call</i> give 3.8%.
      The token is used — chance agreement is 25.5% and the model reaches 41.6% — but it
      buys control only where there was enough labelled audio behind it.</p>
    <p>Call types on the training bouts are the guesses of a classifier trained on the
      bouts a person did label; the human labels in the generator's test split were held
      back from everything, and are what both the classifier and this page are judged on.</p>
  </div>
</div>

<script>
const SECTIONS = __SECTIONS__;
const FACTS = __FACTS__;

const factsEl = document.getElementById("facts");
for (const [label, value] of Object.entries(FACTS)) {
  const cell = document.createElement("div");
  const dt = document.createElement("dt"); dt.textContent = label;
  const dd = document.createElement("dd"); dd.textContent = value;
  cell.append(dt, dd); factsEl.append(cell);
}

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
const drawn = [];
const host = document.getElementById("sections");

function addRow(parent, clip) {
  const line = document.createElement("div");
  line.className = "trial";

  const lead = document.createElement("div");
  lead.className = "lead";
  const play = document.createElement("button");
  play.className = "play";
  play.setAttribute("aria-pressed", "false");
  play.setAttribute("aria-label", "Play " + clip.label);
  play.textContent = "▶";
  const name = document.createElement("span");
  name.className = "idx";
  name.textContent = clip.label;
  lead.append(play, name);

  const canvas = document.createElement("canvas");
  const audio = new Audio(clip.audio);
  audio.preload = "none";

  const note = document.createElement("span");
  note.className = "verdict" + (clip.hit === true ? " hit" : clip.hit === false ? " miss" : "");
  note.textContent = clip.hit === null || clip.hit === undefined ? "" :
    (clip.hit ? "✓ " : "✗ ") + clip.heard;

  line.append(lead, canvas, note);
  parent.append(line);
  drawn.push([canvas, clip.peaks]);
  requestAnimationFrame(() => draw(canvas, clip.peaks, 0));

  play.addEventListener("click", () => {
    if (playing && playing !== audio) { playing.pause(); playing.currentTime = 0; }
    if (audio.paused) { audio.play(); playing = audio; play.setAttribute("aria-pressed", "true"); }
    else { audio.pause(); play.setAttribute("aria-pressed", "false"); }
  });
  audio.addEventListener("timeupdate", () => draw(canvas, clip.peaks, audio.currentTime / (audio.duration || 3)));
  audio.addEventListener("ended", () => { play.setAttribute("aria-pressed", "false"); draw(canvas, clip.peaks, 0); });
}

SECTIONS.forEach(section => {
  const block = document.createElement("div");
  block.className = "section";
  const title = document.createElement("h2");
  title.textContent = "Asked for: " + section.type;
  const note = document.createElement("p");
  note.textContent = section.note;
  block.append(title, note);

  const realBand = document.createElement("p");
  realBand.className = "band";
  realBand.textContent = "Real bouts a person labelled " + section.type;
  block.append(realBand);
  section.real.forEach(clip => addRow(block, clip));

  const genBand = document.createElement("p");
  genBand.className = "band";
  genBand.textContent = "Generated when asked for " + section.type;
  block.append(genBand);
  section.generated.forEach(clip => addRow(block, clip));

  host.append(block);
});

window.addEventListener("resize", () => drawn.forEach(([canvas, peaks]) => draw(canvas, peaks, 0)));
</script>
"""
)


#: The historic good/bad copy, kept as the default so the five experiments
#: that built rating pages before labels existed render exactly as they did.
