"""Real vs codec vs model — the same window in three states."""

import json
from pathlib import Path

from crowgpt.pages.base import _CSS, _peaks, _wav_data_uri


class ComparePage:
    """The diagnostic page: same bout, three treatments, labelled.

    The listening test asks whether you can tell. This asks something more
    useful when the answer is "it sounds scratchy" — WHICH STAGE made it
    scratchy. Real audio put through the codec and straight back is the
    control that separates a tokenizer that is already losing the call from a
    model that never learned it, and the ear settles that far faster than the
    detection rate does.
    """

    def __init__(self, rows, facts):
        self.facts = facts
        self.rows = []
        for i, row in enumerate(rows, 1):
            entry = {"n": i, "species": row["species"].replace("-", " ").title(), "arms": []}
            for label, note, samples, conf in row["arms"]:
                uri, decoded = _wav_data_uri(samples, 24000)
                entry["arms"].append(
                    {"label": label, "note": note, "audio": uri,
                     "peaks": _peaks(decoded), "conf": conf}
                )
            self.rows.append(entry)

    def render(self):
        return _COMPARE_TEMPLATE.replace("__ROWS__", json.dumps(self.rows)).replace(
            "__FACTS__", json.dumps(self.facts)
        )

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


_COMPARE_TEMPLATE = (
    '<meta charset="utf-8">\n<title>CrowGPT — where does the scratch come from?</title>\n'
    + _CSS
    + r"""
<div class="wrap">
  <p class="eyebrow">CrowGPT · diagnostic</p>
  <h1>Is it the codec or the model?</h1>
  <p class="lede">The same three-second window in three states. <b>Real</b> is the recording.
    <b>Through the codec</b> is that same recording encoded to tokens and decoded straight
    back, touching no model at all. <b>Generated</b> is the model.</p>
  <p class="caveat">If "through the codec" already sounds rough, the tokenizer is the
    problem and a higher bitrate is the fix. If it sounds clean and only the last one is
    rough, the model is the problem and the bitrate is a red herring.</p>

  <div id="rows"></div>

  <div class="method">
    <h2>Measured</h2>
    <dl class="facts" id="facts"></dl>
  </div>
</div>

<script>
const ROWS = __ROWS__;
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
const host = document.getElementById("rows");

ROWS.forEach(row => {
  const heading = document.createElement("p");
  heading.className = "eyebrow";
  heading.style.marginTop = "2rem";
  heading.textContent = String(row.n).padStart(2, "0") + " · " + row.species;
  host.append(heading);

  row.arms.forEach(arm => {
    const line = document.createElement("div");
    line.className = "trial";

    const lead = document.createElement("div");
    lead.className = "lead";
    const play = document.createElement("button");
    play.className = "play";
    play.setAttribute("aria-pressed", "false");
    play.setAttribute("aria-label", "Play " + arm.label);
    play.textContent = "▶";
    const name = document.createElement("span");
    name.className = "idx";
    name.style.minWidth = "9rem";
    name.textContent = arm.label;
    lead.append(play, name);

    const canvas = document.createElement("canvas");
    const audio = new Audio(arm.audio);
    audio.preload = "none";

    const note = document.createElement("span");
    note.className = "verdict";
    const conf = arm.conf === null || arm.conf === undefined ? "—" : arm.conf.toFixed(2);
    note.textContent = arm.note + " · BirdNET " + conf;

    line.append(lead, canvas, note);
    host.append(line);
    requestAnimationFrame(() => draw(canvas, arm.peaks, 0));

    play.addEventListener("click", () => {
      if (playing && playing !== audio) { playing.pause(); playing.currentTime = 0; }
      if (audio.paused) { audio.play(); playing = audio; play.setAttribute("aria-pressed", "true"); }
      else { audio.pause(); play.setAttribute("aria-pressed", "false"); }
    });
    audio.addEventListener("timeupdate", () => draw(canvas, arm.peaks, audio.currentTime / (audio.duration || 3)));
    audio.addEventListener("ended", () => { play.setAttribute("aria-pressed", "false"); draw(canvas, arm.peaks, 0); });
  });
});
</script>
"""
)
