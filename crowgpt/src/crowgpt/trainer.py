"""The call-type ear trainer: quiz mode only, and it never writes a label.

FUTURE.txt's "contact-call head" entry is the brief. Contact calls are the most
common crow vocalisation and the corpus has zero labeled; the plan is for the
recordist to label them himself, and this page is the instrument that measures
whether his ear can be trusted first. His quiz accuracy IS the labeler
reliability, citable per class — so the page trains and measures, and nothing
else. The funnel that turns answers into labels is a later phase, gated on the
numbers this page produces, and deliberately not built here: a quiz that
quietly wrote labels would put uncalibrated guesses into the corpus under a
human's name.

THREE TIERS OF GROUND TRUTH, and the page says which is which on every reveal:

  - human-labeled: the vendored label corpus, ~2,300 hand-reviewed American
    Crow segments (alarm call, begging, call — mostly rattles — and song).
    These are the trustworthy classes.
  - recordist-asserted: archive recordings whose recordist metadata says
    contact call. European species (Hooded Crow, ravens), believed at one
    remove — they seed the contact class because nothing better exists, and
    the page must not let them pass as the same grade of truth.
  - field label: the recordist's own labels from the fleet database. Few, but
    the only American Crow ground truth in the project — and his own, so he
    may remember them; the provenance line says so.

THE MENU IS THE PHONE'S. Answer buttons come from `label_defs` in the fleet
database — same keys, colours resolved through the core mapping exactly as the
app's `colorForCall` does — so the ear being trained is the ear that will meet
the same menu in the field. Only classes with exemplars appear: a button that
is never the right answer measures nothing and teaches less.

THE DRAW IS ADAPTIVE, IN THE PAGE. Balanced round-robin across classes until a
class is missed; each miss earns that class an earlier re-draw, so the sitting
spends its trials where the ear is weakest. No clip repeats within a session —
a repeat measures memory, not the ear. Both properties live in the page's
script and are tested by driving it, not by trusting it.

Read-only everywhere: both databases are opened with SQLite's mode=ro and this
module contains no INSERT, no UPDATE, and no code path that writes anywhere
but the output HTML.
"""

import base64
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from crowgpt.demo import (DEMO_SR, MIN_GRADEABLE_SECONDS, _check_gradeable,
                          _CSS, _peaks, _wav_data_uri)

REPO = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get("DATA_DIR") or REPO / "data")
FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"
FIELD_MEDIA = REPO / "fieldserver" / "instance" / "media"
CORVID_DB = DATA / "corvid.db"

# Provenance tiers, in decreasing order of trust. Written on every clip and
# revealed after every answer, because a number that pools them silently would
# claim more than the contact class can back.
HUMAN = "human-labeled"
ASSERTED = "recordist-asserted"
FIELD = "field label"

# Mirrors the app's colorForCall fallback for a key with no colour anywhere.
UNTYPED = "#9aa5b1"

# A quiz clip long enough to judge but short enough that it holds one thing.
# The cap matters for the field labels especially, where a span can be a whole
# 30-second song bout; the middle of it is the exemplar.
MAX_CLIP_SECONDS = 4.0
PAD_SECONDS = 0.25

# A class this thin cannot be drawn from without repeating itself into a
# memory test. flight call sits below this today (one field label) and is
# excluded by the data rather than by anyone deciding against it.
MIN_CLASS_EXEMPLARS = 4


def _read_only(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


class Vocabulary:
    """The field label menu, read from the fleet database.

    The trainer teaches the menu the phone shows, so the vocabulary is read
    rather than copied — a key or colour changed server-side changes the next
    build of this page instead of drifting from it.
    """

    def __init__(self, rows):
        self.defs = {}
        for key, core, color, sort_order, trains in rows:
            self.defs[key] = {"core": core, "color": color,
                              "sort": sort_order, "trains": bool(trains)}

    @classmethod
    def load(cls, db_path=FIELD_DB):
        with _read_only(db_path) as db:
            rows = db.execute(
                "select key, core_mapping, color, sort_order, trains "
                "from label_defs where active = 1 order by sort_order"
            ).fetchall()
        return cls(rows)

    def core_of(self, key):
        entry = self.defs.get(key)
        return entry["core"] if entry else key

    def color_for(self, key):
        """The def's own colour, else its core's — the app's colorForCall.

        So "contact call" reads as the call it maps to, and anything
        unrecognised stays grey rather than borrowing a colour and implying a
        classification we don't have.
        """
        entry = self.defs.get(key)
        if entry is None:
            return UNTYPED
        if entry["color"]:
            return entry["color"]
        core = self.defs.get(entry["core"])
        return (core and core["color"]) or UNTYPED

    def menu(self, keys):
        """The given keys as menu entries, in the phone's order."""
        known = [k for k in keys if k in self.defs]
        unknown = sorted(set(keys) - set(known))
        if unknown:
            raise ValueError(
                f"not in the field vocabulary: {unknown}. The trainer teaches "
                f"the phone's menu; a class the phone cannot show trains an "
                f"ear for a button that does not exist."
            )
        ordered = sorted(known, key=lambda k: self.defs[k]["sort"])
        return [{"key": k, "core": self.core_of(k), "color": self.color_for(k)}
                for k in ordered]


def merge_adjacent(windows, gap=0.0):
    """[(start, end)] in any order -> merged spans, touching within `gap`.

    The corpus labels are one-second windows and the crawl detections are
    three-second ones; a bout crosses several of either. Merged, a clip is a
    natural stretch of calling rather than a window boundary's fragment.
    """
    spans = []
    for start, end in sorted(windows):
        if spans and start - spans[-1][1] <= gap:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return [(s, e) for s, e in spans]


def clip_window(start, end, pad=PAD_SECONDS, cap=MAX_CLIP_SECONDS):
    """The window actually cut: padded so an onset is not clipped, capped so
    one long bout does not become one long trial. A span over the cap keeps
    its middle, which is the least likely part to be something else."""
    if end - start > cap:
        middle = (start + end) / 2
        start, end = middle - cap / 2, middle + cap / 2
    return max(0.0, start - pad), end + pad


def cut(path, start, end, sr=24000):
    """Decode one window to mono float32 via ffmpeg.

    ffmpeg rather than soundfile because the exemplars are mp3 and flac from
    three different stores, and one decoder that reads them all beats three
    special cases. Seeking before the input keeps it fast on long recordings.
    """
    seconds = end - start
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}",
         "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "wav", "pipe:1"],
        capture_output=True, check=True)
    samples, rate = sf.read(io.BytesIO(out.stdout), dtype="float32")
    return np.asarray(samples, dtype=np.float32), rate


def spectrogram(samples, sr, width=150, height=48, floor_db=-70.0):
    """A small log-magnitude grid for the reveal, packed as base64 bytes.

    Computed here so the page needs no DSP and no network: the canvas just
    paints cells. Max-pooled rather than averaged, because a call is a ridge
    and averaging a ridge into a quiet window erases exactly the thing the
    reveal exists to show.
    """
    from scipy.signal import stft

    samples = np.asarray(samples, dtype=np.float32)
    nperseg = 512
    if samples.size < nperseg:
        samples = np.pad(samples, (0, nperseg - samples.size))
    _, _, grid = stft(samples, fs=sr, nperseg=nperseg, noverlap=nperseg // 2)
    power = 20 * np.log10(np.abs(grid) + 1e-9)
    power -= power.max()
    power = np.clip(power, floor_db, 0.0)

    bins, frames = power.shape
    width = min(width, frames)
    cells = np.zeros((height, width), dtype=np.float32)
    row_edges = np.linspace(0, bins, height + 1).astype(int)
    col_edges = np.linspace(0, frames, width + 1).astype(int)
    for r in range(height):
        rows = power[row_edges[r]:max(row_edges[r + 1], row_edges[r] + 1)]
        for c in range(width):
            block = rows[:, col_edges[c]:max(col_edges[c + 1], col_edges[c] + 1)]
            cells[r, c] = block.max()
    # Row 0 is the highest frequency, so the page paints top-down as-is.
    levels = ((cells[::-1] - floor_db) / -floor_db * 255).astype(np.uint8)
    return {"w": width, "h": height,
            "b64": base64.b64encode(levels.tobytes()).decode("ascii")}


def _crowtools_corpus():
    """corpus.py imported by path — the calltype.py pattern, same reason."""
    spec = importlib.util.spec_from_file_location(
        "crowtools_corpus", REPO / "pipelines" / "ingest" / "corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def corpus_exemplars(rng, per_class, min_seconds=MIN_GRADEABLE_SECONDS):
    """The trustworthy classes, from the vendored human-labeled corpus.

    Only segments carrying exactly one CORE label are used: a clip that is
    both alarm and begging has no single right answer, and a quiz question
    with two right answers measures the grader, not the ear.
    """
    corpus = _crowtools_corpus().LabelCorpus()
    windows = defaultdict(list)   # (label, path) -> [(start, end)]
    for segment in corpus.labeled_segments(require_audio=True):
        if len(segment.labels) != 1:
            continue
        label = next(iter(segment.labels))
        windows[(label, segment.audio_path)].append(
            (float(segment.start), float(segment.end)))

    spans = defaultdict(list)     # label -> [(path, start, end)]
    for (label, path), stretch in windows.items():
        for start, end in merge_adjacent(stretch):
            spans[label].append((path, start, end))

    out = defaultdict(list)
    for label, candidates in spans.items():
        order = list(candidates)
        rng.shuffle(order)
        for path, start, end in order:
            if len(out[label]) >= per_class:
                break
            lo, hi = clip_window(start, end)
            try:
                samples, sr = cut(path, lo, hi)
            except (subprocess.CalledProcessError, sf.LibsndfileError):
                continue
            if len(samples) / sr < min_seconds:
                continue
            out[label].append({
                "clip_id": f"corpus:{Path(path).stem}:{start:g}",
                "key": label, "audio": samples, "sr": sr,
                "provenance": HUMAN, "species": "American Crow",
                "note": "hand-reviewed segment from the vendored label corpus",
            })
    return dict(out)


def contact_exemplars(rng, per_class, db_path=CORVID_DB,
                      min_seconds=MIN_GRADEABLE_SECONDS, per_recording=2):
    """The contact class, from recordings whose recordist said contact.

    Weaker ground truth on purpose and marked as such: the label covers the
    recording, not the second — the detection windows say where a corvid was
    calling, and the recordist's word says what about. European species, which
    the reveal names. Capped per recording so one long raven session cannot
    become half the class.
    """
    with _read_only(db_path) as db:
        rows = db.execute(
            "select r.id, r.species, r.file_path, d.start_seconds, "
            "       d.end_seconds, d.confidence "
            "from recordings r join detections d on d.recording_id = r.id "
            "where lower(r.call_type) like '%contact%' and r.downloaded = 1 "
            "  and (lower(r.species) like '%crow%' or lower(r.species) like '%raven%' "
            "       or lower(r.species) like '%corvus%') "
            "  and (lower(d.species) like '%crow%' or lower(d.species) like '%raven%')"
        ).fetchall()

    best = {}   # (recording, window start) -> row, keeping the top confidence
    for rec_id, species, path, start, end, conf in rows:
        seen = best.get((rec_id, start))
        if seen is None or (conf or 0) > (seen[5] or 0):
            best[(rec_id, start)] = (rec_id, species, path, start, end, conf)

    by_recording = defaultdict(list)
    for row in best.values():
        by_recording[row[0]].append(row)

    candidates = []
    for windows in by_recording.values():
        windows.sort(key=lambda r: -(r[5] or 0))
        candidates.extend(windows[:per_recording])
    rng.shuffle(candidates)

    out = []
    for rec_id, species, path, start, end, conf in candidates:
        if len(out) >= per_class:
            break
        if not Path(path).exists():
            continue
        lo, hi = clip_window(float(start), float(end))
        try:
            samples, sr = cut(path, lo, hi)
        except (subprocess.CalledProcessError, sf.LibsndfileError):
            continue
        if len(samples) / sr < min_seconds:
            continue
        out.append({
            "clip_id": f"crawl:{rec_id}:{start:g}",
            "key": "contact call", "audio": samples, "sr": sr,
            "provenance": ASSERTED, "species": species,
            "note": "archive recording whose recordist called it a contact call "
                    "— the label covers the recording, not this second",
        })
    return out


def field_exemplars(rng, per_class, db_path=FIELD_DB, media_dir=FIELD_MEDIA,
                    min_seconds=MIN_GRADEABLE_SECONDS):
    """The recordist's own labels — the only American Crow ground truth.

    label_source='human' only: detected_calls are the model's guesses and a
    trainer built on them would teach the model's confusions back to the ear
    that is supposed to correct them.
    """
    with _read_only(db_path) as db:
        rows = db.execute(
            "select l.id, l.call_type, l.start_sec, l.end_sec, m.storage_ref "
            "from labels l "
            "join media m on m.id = l.media_id "
            "join label_defs d on d.key = l.call_type "
            "where l.label_source = 'human' and d.trains = 1 "
            "  and l.start_sec is not null and l.end_sec is not null"
        ).fetchall()
    rng.shuffle(rows)

    out = defaultdict(list)
    for label_id, call_type, start, end, storage_ref in rows:
        if len(out[call_type]) >= per_class:
            continue
        path = Path(media_dir) / storage_ref
        if not path.exists() or end - start < min_seconds:
            continue
        lo, hi = clip_window(float(start), float(end))
        try:
            samples, sr = cut(path, lo, hi)
        except (subprocess.CalledProcessError, sf.LibsndfileError):
            continue
        if len(samples) / sr < min_seconds:
            continue
        out[call_type].append({
            "clip_id": f"field:{label_id}",
            "key": call_type, "audio": samples, "sr": sr,
            "provenance": FIELD, "species": "American Crow",
            "note": "your own field label — you may remember this one",
        })
    return dict(out)


def assemble(per_class=12, field_per_class=3, seed=0,
             min_class=MIN_CLASS_EXEMPLARS):
    """All three sources into one clip list, balanced per class.

    Field labels substitute into their class rather than inflating it, capped
    so a class is never mostly clips the recordist wrote himself. The contact
    class takes whatever field labels exist first — today that is none, but
    the first context-anchored window captures will land here without anyone
    editing this function.
    """
    rng = np.random.default_rng(seed)
    pools = corpus_exemplars(rng, per_class)
    pools.setdefault("contact call", []).extend(contact_exemplars(rng, per_class))
    field = field_exemplars(rng, field_per_class)

    for key, extras in field.items():
        pool = pools.setdefault(key, [])
        room = max(0, per_class - len(extras))
        pools[key] = pool[:room] + extras

    thin = {k: len(v) for k, v in pools.items() if len(v) < min_class}
    for key in thin:
        del pools[key]
    clips = [clip for pool in pools.values() for clip in pool]
    return clips, thin


class TrainerPage:
    """The quiz page: one clip at a time, the phone's menu, adaptive draw.

    Python's half builds the pools — grouped by class, shuffled, every clip
    checked gradeable — and embeds them with the menu and a rotation order.
    The page's half owns the draw, because which clip comes next depends on
    answers that do not exist at build time.

    Nothing identifying a clip is rendered before the answer: waveform flat,
    spectrogram absent, species and provenance withheld. The species alone
    would leak the class — every contact exemplar is European.
    """

    def __init__(self, clips, menu, facts, seed=0, title=None,
                 min_seconds=MIN_GRADEABLE_SECONDS):
        self.facts = facts
        self.title = title or "What kind of call is this?"
        if min_seconds:
            _check_gradeable([(c["audio"], c.get("sr", 24000)) for c in clips],
                             "TrainerPage")
        keys = {c["key"] for c in clips}
        menu_keys = {m["key"] for m in menu}
        if not keys <= menu_keys:
            raise ValueError(f"clips carry classes missing from the menu: "
                             f"{sorted(keys - menu_keys)}")

        ids = [c["clip_id"] for c in clips]
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(
                f"repeated clip_id: {dupes}. A repeat inside a session tests "
                f"memory rather than the ear, so it is refused at build.")

        rng = np.random.default_rng(seed)
        self.menu = [dict(m) for m in menu if m["key"] in keys]
        pools = defaultdict(list)
        for clip in clips:
            uri, samples = _wav_data_uri(clip["audio"], clip.get("sr", 24000))
            pools[clip["key"]].append({
                "clip_id": clip["clip_id"],
                "key": clip["key"],
                "audio": uri,
                "peaks": _peaks(samples),
                "spec": spectrogram(samples, DEMO_SR),
                "seconds": round(len(samples) / DEMO_SR, 3),
                "provenance": clip["provenance"],
                "species": clip.get("species", "?"),
                "note": clip.get("note", ""),
            })
        self.pools = {}
        for key in sorted(pools):
            order = list(pools[key])
            rng.shuffle(order)
            self.pools[key] = order
        for entry in self.menu:
            entry["n"] = len(self.pools[entry["key"]])
        rotation = [m["key"] for m in self.menu]
        rng.shuffle(rotation)
        self.rotation = rotation

    def render(self):
        page = (_TRAINER_TEMPLATE
                .replace("__MENU__", json.dumps(self.menu))
                .replace("__POOLS__", json.dumps(self.pools))
                .replace("__ROTATION__", json.dumps(self.rotation))
                .replace("__FACTS__", json.dumps(self.facts))
                .replace("__TITLE__", json.dumps(self.title)))
        return page

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render())
        return path


def build_trainer(out, per_class=12, field_per_class=3, seed=0):
    """Gather, page, write. Returns (path, per-class provenance summary)."""
    vocabulary = Vocabulary.load()
    clips, thin = assemble(per_class=per_class, field_per_class=field_per_class,
                           seed=seed)
    menu = vocabulary.menu(sorted({c["key"] for c in clips}))

    summary = defaultdict(lambda: defaultdict(int))
    for clip in clips:
        summary[clip["key"]][clip["provenance"]] += 1

    facts = {"Classes": len(menu), "Clips": len(clips),
             "Human-labeled": sum(1 for c in clips if c["provenance"] == HUMAN),
             "Recordist-asserted": sum(1 for c in clips if c["provenance"] == ASSERTED),
             "Field labels": sum(1 for c in clips if c["provenance"] == FIELD),
             "Min clip": f"{MIN_GRADEABLE_SECONDS:g} s"}
    page = TrainerPage(clips, menu, facts, seed=seed)
    path = page.write(out)
    return path, {"per_class": {k: dict(v) for k, v in sorted(summary.items())},
                  "excluded_thin": thin}


_TRAINER_TEMPLATE = (
    '<meta charset="utf-8">\n<title>CrowGPT — ear trainer</title>\n'
    + _CSS
    + r"""
<style>
  .chips { display: flex; gap: .4rem; flex-wrap: wrap; margin: 0 0 1.5rem; }
  .chip { font-family: var(--mono); font-size: .7rem; padding: .35rem .6rem;
          border: 1px solid var(--line); border-left: 3px solid var(--line);
          border-radius: 2px; color: var(--soft); }
  .stage { background: var(--raised); border: 1px solid var(--line);
           border-radius: 2px; padding: 1.1rem 1.2rem; }
  .stage .lead { margin-bottom: .8rem; }
  .stage canvas { width: 100%; display: block; }
  #wave { height: 46px; }
  #spec { height: 110px; margin-top: .6rem; }
  .answers { display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .9rem; }
  .answers button { font-family: var(--mono); font-size: .74rem;
                    letter-spacing: .06em; text-transform: uppercase;
                    padding: .55rem .9rem; cursor: pointer;
                    background: transparent; color: var(--ink);
                    border: 1px solid var(--line); border-left-width: 4px;
                    border-radius: 2px; }
  .answers button:hover { border-color: var(--accent); color: var(--accent); }
  #verdict { display: block; margin-top: .9rem; min-height: 1.2em; }
  .reveal-note { font-family: var(--mono); font-size: .72rem; color: var(--soft);
                 margin: .25rem 0 0; }
  #next { font-family: var(--mono); font-size: .74rem; letter-spacing: .1em;
          text-transform: uppercase; padding: .5rem 1rem; margin-top: .8rem;
          cursor: pointer; background: transparent; color: var(--ink);
          border: 1px solid var(--line); border-radius: 2px; }
  #next:hover { border-color: var(--accent); color: var(--accent); }
</style>

<div class="wrap">
  <p class="eyebrow">CrowGPT · ear trainer</p>
  <h1>What kind of call is this?</h1>
  <p class="lede">One clip at a time. Listen, commit to a call type — the same menu the
    field app shows — and the verdict comes back at once, with the waveform, the
    spectrogram and where the clip came from.</p>
  <p class="lede">This page trains and measures an ear. <b>It writes no labels anywhere.</b>
    The per-class score below, interval and all, is the reading that will one day decide
    whether quiz answers can be trusted to become labels — that funnel is a later page,
    gated on this one.</p>
  <p class="caveat"><b>The contact-call clips are weaker ground truth than the rest.</b>
    Alarm, begging, call and song are hand-reviewed American Crow segments a person
    labelled one at a time. Contact call has no such exemplars anywhere: its clips are
    European birds — Hooded Crows and ravens — whose recordists said "contact call" about
    the whole recording. Believe them at one remove, and expect the timbre to differ from
    the crows outside your window.</p>
  <p class="caveat">"Call" here is mostly rattles — that is what the labeled corpus holds
    under that name. Classes you miss come back more often; no clip repeats within a
    sitting. Flight call is missing because nothing trustworthy exists to quiz it from.</p>
  <p class="keyhint">Keyboard: <b>1–9</b> answer &nbsp; <b>space</b> play &nbsp;
    <b>enter</b> next clip</p>

  <div class="score">
    <div><span>Correct</span><b id="score">0 / 0</b></div>
    <div><span>Remaining</span><b id="left">0</b></div>
  </div>
  <div class="chips" id="perclass"></div>

  <div class="stage" id="stage">
    <div class="lead">
      <button class="play" id="play" aria-pressed="false" aria-label="Play the clip">▶</button>
      <span class="idx" id="trialno"></span>
    </div>
    <canvas id="wave"></canvas>
    <div class="answers" id="answers"></div>
    <span id="verdict" class="verdict"></span>
    <canvas id="spec" style="display:none"></canvas>
    <div class="reveal-note" id="provenance"></div>
    <div class="reveal-note" id="sourcenote"></div>
    <button id="next" style="visibility:hidden">Next clip</button>
  </div>

  <div class="recorder">
    <h2>Save this sitting</h2>
    <p>Answers are kept in this browser as you go, but they only become a measurement —
      the labeler-reliability reading the funnel will be gated on — once the file is saved
      into <code>results/trainer/</code>.</p>
    <textarea id="note" placeholder="Which classes felt guessable? What were you listening for?"></textarea>
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
    <p>Exemplars come from three places, in decreasing order of trust: a hand-reviewed
      public label corpus of American Crow segments; archive recordings whose recordists
      described contact calls (European species — the only seed the contact class has);
      and the recordist's own field labels, few but local. Every reveal names its tier.</p>
    <p>Accuracy per class is shown with a Wilson 95% interval, which stays honest at the
      small n a sitting produces. The draw is balanced across classes and bends toward
      the ones being missed; no clip repeats within a sitting.</p>
  </div>
</div>

<script>
const MENU = __MENU__;
const POOLS = __POOLS__;
const ROTATION = __ROTATION__;
const FACTS = __FACTS__;
const TITLE = __TITLE__;

const TOTAL = MENU.reduce((sum, m) => sum + m.n, 0);
const MISS_BOOST = 1;

const factsEl = document.getElementById("facts");
for (const [label, value] of Object.entries(FACTS)) {
  const cell = document.createElement("div");
  const dt = document.createElement("dt"); dt.textContent = label;
  const dd = document.createElement("dd"); dd.textContent = value;
  cell.append(dt, dd); factsEl.append(cell);
}

/* Wilson 95% interval — the small-n honest one. */
function wilson(k, n) {
  if (!n) return [0, 1];
  const z = 1.96, p = k / n, denom = 1 + z * z / n;
  const centre = p + z * z / (2 * n);
  const margin = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n));
  return [(centre - margin) / denom, (centre + margin) / denom];
}

const STATS = {};
const NEXT = {};
for (const m of MENU) { STATS[m.key] = {asked: 0, right: 0, wrong: 0}; NEXT[m.key] = 0; }

/* THE DRAW. Priority = asked - MISS_BOOST * wrong, lowest first: with no
   misses that is an exact round robin over ROTATION, and every miss lowers a
   class's score by one, buying it exactly one extra earlier turn. Ties break
   by ROTATION order, which was shuffled at build so the phone's menu order is
   not also the quiz's habit. */
function drawClass() {
  let best = null, bestScore = Infinity;
  for (const key of ROTATION) {
    if (NEXT[key] >= POOLS[key].length) continue;
    const s = STATS[key];
    const score = s.asked - MISS_BOOST * s.wrong;
    if (score < bestScore) { best = key; bestScore = score; }
  }
  return best;
}

const chipEls = {};
const perclass = document.getElementById("perclass");
for (const m of MENU) {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.style.borderLeftColor = m.color;
  chip.textContent = m.key + " —";
  chipEls[m.key] = chip;
  perclass.append(chip);
}

function updateChips() {
  for (const m of MENU) {
    const s = STATS[m.key];
    if (!s.asked) { chipEls[m.key].textContent = m.key + " —"; continue; }
    const [lo, hi] = wilson(s.right, s.asked);
    chipEls[m.key].textContent = m.key + " " + s.right + "/" + s.asked +
      " · " + Math.round(100 * s.right / s.asked) + "% [" +
      Math.round(100 * lo) + "–" + Math.round(100 * hi) + "]";
  }
}

function drawWave(canvas, peaks, progress) {
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

function drawSpec(canvas, spec) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const styles = getComputedStyle(document.documentElement);
  const lit = styles.getPropertyValue("--accent").trim();
  const raw = atob(spec.b64);
  const cellW = width / spec.w, cellH = height / spec.h;
  ctx.fillStyle = lit;
  for (let r = 0; r < spec.h; r++) {
    for (let c = 0; c < spec.w; c++) {
      const level = raw.charCodeAt(r * spec.w + c) / 255;
      if (level <= 0.02) continue;
      ctx.globalAlpha = level;
      ctx.fillRect(c * cellW, r * cellH, Math.ceil(cellW), Math.ceil(cellH));
    }
  }
  ctx.globalAlpha = 1;
}

/* One media element for the whole page — the ABX lesson. Play stays inside
   the click's synchronous turn; only the seek is guarded behind readiness. */
const player = new Audio();
let loadedSource = null;
const playBtn = document.getElementById("play");
const waveEl = document.getElementById("wave");

function stopPlaying() {
  player.pause();
  playBtn.setAttribute("aria-pressed", "false");
}
player.addEventListener("ended", stopPlaying);
player.addEventListener("error", stopPlaying);
player.addEventListener("timeupdate", () => {
  if (!current) return;
  const shape = current.answered ? current.clip.peaks : FLAT;
  drawWave(waveEl, shape, player.currentTime / (player.duration || 3));
});

const FLAT = Array.from({length: 160}, () => 0.3);

const answers = new Map();
const sessionId = Math.random().toString(36).slice(2, 10);
const startedAt = new Date().toISOString();
let current = null;      // {clip, plays, firstPlay, answered}
let answeredCount = 0, correctCount = 0;

const verdictEl = document.getElementById("verdict");
const specEl = document.getElementById("spec");
const provenanceEl = document.getElementById("provenance");
const sourceEl = document.getElementById("sourcenote");
const nextBtn = document.getElementById("next");
const trialnoEl = document.getElementById("trialno");
const scoreEl = document.getElementById("score");
const leftEl = document.getElementById("left");

playBtn.addEventListener("click", () => {
  if (!current || current.finished) return;
  if (playBtn.getAttribute("aria-pressed") === "true") { stopPlaying(); return; }
  playBtn.setAttribute("aria-pressed", "true");
  if (loadedSource !== current.clip.audio) {
    loadedSource = current.clip.audio;
    player.src = current.clip.audio;
  } else if (player.readyState >= 1) {
    try { player.currentTime = 0; } catch (e) { /* leave it */ }
  }
  current.plays += 1;
  if (current.firstPlay === null) current.firstPlay = performance.now();
  const started = player.play();
  if (started && started.catch) {
    started.catch(err => {
      if (err && err.name === "AbortError") return;
      stopPlaying();
      verdictEl.textContent = "playback blocked: " + ((err && err.message) || err);
    });
  }
});

const answerButtons = [];
const answersEl = document.getElementById("answers");
MENU.forEach(m => {
  const button = document.createElement("button");
  button.textContent = m.key;
  button.style.borderLeftColor = m.color;
  button.addEventListener("click", () => answer(m.key));
  answerButtons.push(button);
  answersEl.append(button);
});

function present() {
  const key = drawClass();
  if (key === null) { finish(); return; }
  const clip = POOLS[key][NEXT[key]];
  NEXT[key] += 1;
  current = {clip: clip, plays: 0, firstPlay: null, answered: false};
  trialnoEl.textContent = "clip " + (answeredCount + 1) + " of " + TOTAL;
  verdictEl.textContent = "";
  verdictEl.className = "verdict";
  specEl.style.display = "none";
  provenanceEl.textContent = "";
  sourceEl.textContent = "";
  nextBtn.style.visibility = "hidden";
  stopPlaying();
  drawWave(waveEl, FLAT, 0);
}

function answer(guess) {
  if (!current || current.answered) return;
  current.answered = true;
  stopPlaying();
  const clip = current.clip;
  const truth = clip.key;
  const hit = guess === truth;
  const stats = STATS[truth];
  stats.asked += 1;
  if (hit) { stats.right += 1; correctCount += 1; } else { stats.wrong += 1; }
  answeredCount += 1;

  const menuByKey = {};
  MENU.forEach(m => { menuByKey[m.key] = m; });
  answers.set(answeredCount, {
    trial_index: answeredCount,
    clip_id: clip.clip_id,
    truth: truth,
    answer: guess,
    correct: hit,
    truth_core: menuByKey[truth] ? menuByKey[truth].core : truth,
    answer_core: menuByKey[guess] ? menuByKey[guess].core : guess,
    provenance: clip.provenance,
    species: clip.species,
    seconds: clip.seconds,
    decision_ms: current.firstPlay === null ? null
      : Math.round(performance.now() - current.firstPlay),
    plays: current.plays,
    answered_at: new Date().toISOString(),
  });

  verdictEl.className = "verdict " + (hit ? "right" : "wrong");
  verdictEl.textContent = (hit ? "✓ " : "✗ ") + truth;
  drawWave(waveEl, clip.peaks, 0);
  specEl.style.display = "block";
  drawSpec(specEl, clip.spec);
  provenanceEl.textContent = clip.provenance + " · " + clip.species +
    " · " + clip.seconds.toFixed(1) + " s";
  sourceEl.textContent = clip.note;
  nextBtn.style.visibility = "visible";

  scoreEl.textContent = correctCount + " / " + answeredCount;
  leftEl.textContent = TOTAL - answeredCount;
  updateChips();
  autosave();
}

function finish() {
  current = {finished: true, answered: true};
  trialnoEl.textContent = "done — " + correctCount + " / " + answeredCount +
    ". Save the sitting below.";
  verdictEl.className = "verdict";
  verdictEl.textContent = "";
  nextBtn.style.visibility = "hidden";
  drawWave(waveEl, FLAT, 0);
}

nextBtn.addEventListener("click", () => {
  if (current && current.answered && !current.finished) present();
});

document.addEventListener("keydown", event => {
  const tag = (event.target && event.target.tagName || "").toLowerCase();
  if (tag === "textarea" || tag === "input" || event.metaKey || event.ctrlKey) return;
  const digit = parseInt(event.key, 10);
  if (digit >= 1 && digit <= answerButtons.length) {
    event.preventDefault();
    answerButtons[digit - 1].click();
  } else if (event.key === " ") {
    event.preventDefault();
    playBtn.click();
  } else if (event.key === "Enter") {
    event.preventDefault();
    nextBtn.click();
  }
});

function perClassSummary() {
  const out = {};
  for (const m of MENU) {
    const s = STATS[m.key];
    const [lo, hi] = wilson(s.right, s.asked);
    out[m.key] = {asked: s.asked, right: s.right,
                  rate: s.asked ? s.right / s.asked : null,
                  wilson95: s.asked ? [lo, hi] : null};
  }
  return out;
}

function payload() {
  return {
    session_id: sessionId, subject: "ben", kind: "trainer", title: TITLE,
    started_at: startedAt, finished_at: new Date().toISOString(),
    answered: answeredCount, of: TOTAL,
    correct: correctCount,
    per_class: perClassSummary(),
    note: document.getElementById("note").value,
    trials: [...answers.values()].sort((a, b) => a.trial_index - b.trial_index),
  };
}
function text() { return JSON.stringify(payload(), null, 2); }
function autosave() {
  try { localStorage.setItem("crowgpt.trainer." + sessionId, text()); } catch (e) {}
}

const savedEl = document.getElementById("saved");
function flash(m) { savedEl.textContent = m; setTimeout(() => { savedEl.textContent = ""; }, 4000); }

document.getElementById("download").addEventListener("click", () => {
  const blob = new Blob([text()], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "trainer-" + sessionId + ".json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  flash("saved " + answers.size + " answers");
});
document.getElementById("copy").addEventListener("click", async () => {
  const box = document.getElementById("payload");
  try { await navigator.clipboard.writeText(text()); flash("copied"); }
  catch (e) { box.style.display = "block"; box.value = text(); box.select(); flash("select all and copy"); }
});

leftEl.textContent = TOTAL;
window.addEventListener("resize", () => {
  if (!current || current.finished) return;
  drawWave(waveEl, current.answered ? current.clip.peaks : FLAT, 0);
  if (current.answered) drawSpec(specEl, current.clip.spec);
});
present();
</script>
"""
)
