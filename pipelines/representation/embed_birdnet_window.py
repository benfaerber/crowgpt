"""BirdNET embeddings of the label corpus, with the window position as a knob.

Two arms of experiment 0025, and the only difference between them is where the
3-second window sits:

  --align grid      [3*(s//3), +3)  — what build_dataset.window_for() does, so
                    a 1 s label lands at an arbitrary offset inside its window
  --align centred   [s+0.5-1.5, +3) — the same model, the same 3 s of context,
                    centred on the labelled second

Scoring them against each other measures the cost of grid jitter *alone*: same
backbone, same window width, same corpus, same folds. If centred wins, the fix
is ten lines in build_dataset.py and it lifts all five shipped heads without
anyone installing TensorFlow.

Runs in the BirdNET venv, on CPU:
  .venv-birdnet/bin/python embed_birdnet_window.py --align centred
  .venv-birdnet/bin/python embed_birdnet_window.py --align grid --check

Audio comes from experiment 0025's excerpt cache rather than the mp3s, so every
arm of the bake-off windows the same decoded samples. Build it first with
`run.py --build-cache`.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path

import numpy as np

from birdnetlib import RecordingBuffer
from birdnetlib.analyzer import Analyzer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from corpus import LabelCorpus  # noqa: E402
from excerpts import DATA, ExcerptCache, segment_keys  # noqa: E402
from features import Features  # noqa: E402
from crowgpt.progress import Run  # noqa: E402

EXPERIMENT = REPO / "experiments" / "0025-is-birdnet-the-bottleneck"
CACHE_DIR = DATA / "experiments" / "0025"
ARMS = EXPERIMENT / "arms"
DEVNULL = open(os.devnull, "w")

#: BirdNET's window. Not a parameter — the model has no other mode, and that
#: fixedness is half of what this experiment is testing.
WINDOW_SEC = 3.0
SR = 48_000

ALIGNMENTS = {
    "grid": "a-birdnet-grid",
    "centred": "b-birdnet-centred",
}


class BirdNetWindows:
    """One 3 s window per labelled segment, embedded, position under control."""

    def __init__(self, align):
        if align not in ALIGNMENTS:
            raise SystemExit(f"--align must be one of {sorted(ALIGNMENTS)}")
        self.align = align
        with contextlib.redirect_stdout(DEVNULL):
            self.analyzer = Analyzer()

    def offset_sec(self, seg):
        """How far the window's start sits from the excerpt's left edge.

        The cache is 9 s centred on the middle of the labelled second, so the
        centred window starts at 4.5 - 1.5 = 3.0 s in. The grid window starts
        wherever BirdNET's fixed lattice put it, which is 0, 1 or 2 seconds
        earlier depending on the label's position modulo 3 — and that jitter is
        the whole point of the comparison.
        """
        half = ExcerptCache(CACHE_DIR).half_width_sec
        centre = (seg.start + seg.end) / 2
        if self.align == "centred":
            return half - WINDOW_SEC / 2
        aligned = WINDOW_SEC * (seg.start // WINDOW_SEC)
        return half - (centre - aligned)

    def embed(self, row, seg):
        """The 1024-d embedding of this segment's window, or None."""
        start = int(round(self.offset_sec(seg) * SR))
        clip = np.asarray(row[start:start + int(WINDOW_SEC * SR)], dtype=np.float32)
        if len(clip) < int(WINDOW_SEC * SR):
            clip = np.pad(clip, (0, int(WINDOW_SEC * SR) - len(clip)))
        try:
            with contextlib.redirect_stdout(DEVNULL):
                rec = RecordingBuffer(self.analyzer, clip, SR, min_conf=0.1)
                rec.extract_embeddings()
        except Exception as ex:  # noqa: BLE001
            print(f"  fail {seg.key}: {ex}", file=sys.stderr)
            return None
        if not rec.embeddings:
            return None
        # Exactly one window in, so exactly one embedding out. If BirdNET ever
        # returns more, averaging them would quietly change what this arm
        # measures, so take the first and say so rather than pool silently.
        return np.asarray(rec.embeddings[0]["embeddings"], dtype=np.float64)


def build(align, limit=None):
    corpus = LabelCorpus(dataset="all-public")
    segments = {s.key: s for s in corpus.labeled_segments(require_audio=True)}
    cache = ExcerptCache(CACHE_DIR)
    data, cached_keys = cache.load()
    index = {k: i for i, k in enumerate(cached_keys)}

    keys = [k for k in segment_keys(corpus) if k in index]
    if limit:
        keys = keys[:limit]
    arm = ALIGNMENTS[align]
    run = Run(f"0025 ARM {arm.upper()}",
              ["load BirdNET", f"embed {len(keys)} segments", "write npz"])
    print(f"{arm}: embedding {len(keys)} segments ({align}-aligned 3 s windows)")

    with run.stage("load BirdNET"):
        embedder = BirdNetWindows(align)
    X, Y, groups, kept = [], [], [], []
    with run.stage(f"embed {len(keys)} segments") as stage:
        stage.say(f"{align}-aligned 3 s windows")
        for n, key in enumerate(keys, 1):
            seg = segments[key]
            vec = embedder.embed(data[index[key]], seg)
            if vec is None or not np.isfinite(vec).all():
                continue
            X.append(vec)
            Y.append(sorted(seg.labels))
            groups.append(seg.file_id)
            kept.append(key)
            if n % 100 == 0:
                stage.update(n, len(keys))

    with run.stage("write npz"):
        feats = Features(np.array(X), Y, np.array(groups), kept,
                         f"birdnet_{align}_3s",
                         {"backbone": "birdnet", "window_sec": WINDOW_SEC,
                          "align": align, "sr": SR})
        out = feats.write(ARMS / f"{arm}.npz")
    run.note(f"wrote {len(feats)} rows x {feats.dim}-d -> {out.name}")
    print(f"wrote {len(feats)} rows x {feats.dim}-d -> {out}")
    return feats


def check():
    """Embed one segment each way and prove the windows actually differ.

    Cheap, and it catches the failure that would otherwise be invisible: if
    `offset_sec` were wrong in the same way for both alignments, the two arms
    would be identical and the experiment would report a confident null about a
    comparison it never made.
    """
    corpus = LabelCorpus(dataset="all-public")
    segments = {s.key: s for s in corpus.labeled_segments(require_audio=True)}
    cache = ExcerptCache(CACHE_DIR)
    data, cached_keys = cache.load()
    index = {k: i for i, k in enumerate(cached_keys)}

    keys = [k for k in segment_keys(corpus) if k in index]
    grid, centred = BirdNetWindows("grid"), BirdNetWindows("centred")

    print("Where the label sits inside BirdNET's window, by start % 3:\n")
    print(f"{'segment':<24}{'start':>6}{'%3':>4}{'grid off':>10}"
          f"{'centred':>9}{'cosine':>9}  label sits")
    where = {0: "at the START", 1: "in the MIDDLE", 2: "at the END"}
    for residue in (0, 1, 2):
        for key in [k for k in keys if segments[k].start % 3 == residue][:2]:
            seg = segments[key]
            row = data[index[key]]
            a, b = grid.embed(row, seg), centred.embed(row, seg)
            cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
            print(f"{key:<24}{seg.start:>6}{seg.start % 3:>4}"
                  f"{grid.offset_sec(seg):>10.2f}{centred.offset_sec(seg):>9.2f}"
                  f"{cos:>9.3f}  {where[residue]}")

    counts = {r: sum(1 for k in keys if segments[k].start % 3 == r)
              for r in (0, 1, 2)}
    same = counts[1]
    print(f"\nstart%3 distribution: {counts}")
    print(f"Only start%3==1 already centres the label, so the two arms window "
          f"identical\naudio for {same}/{len(keys)} segments ({same / len(keys):.0%}) "
          f"and differ by one second\nfor the rest. That bounds the effect size "
          f"before a single AUC is computed: a\nfull third of the corpus cannot "
          f"move, whatever the alignment is worth.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--align", choices=sorted(ALIGNMENTS), default="centred")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--check", action="store_true",
                        help="prove the two alignments window different audio")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        build(args.align, args.limit)


if __name__ == "__main__":
    main()
