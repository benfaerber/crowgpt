"""Build pooled BirdNET features from the vendored American Crow label corpus.

Reads corpus.py, which reads the committed labels and the audio in data/ — see
crowtools/README.md for where those labels came from and who they belong to.

Emits the SAME schema as training/recover_and_pool.py — X (3072-dim, the shared
pooling.pool of mean+std+max) and Y (object array of CORE label lists) — so this
corpus drops straight into Phase 4, either on its own or concatenated with the
the archive pooled_embeddings.npz.

BirdNET (TFLite) is single-threaded, so embedding runs one file per worker
process across --jobs cores (default: most of them). Each worker loads its own
analyzer, so no TFLite state is inherited across the fork.

Note on localisation: these labels are per-second, so each feature pools the
single 3s BirdNET window covering the labelled call (std block ≈ 0). The
archive set pools whole clips. Train on this alone for the alarm/song lift, or
be aware of that std/max domain gap when combining the two.

Runs in the BirdNET venv (birdnetlib + numpy<2):
  ../representation/.venv-birdnet/bin/python build_dataset.py --dataset all-public
  ../representation/.venv-birdnet/bin/python build_dataset.py --jobs 30
"""

import argparse
import contextlib
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

from corpus import LOCAL_AUDIO, LabelCorpus

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "crowgpt" / "src"))
from pooling import FEATURE, pool  # noqa: E402  (shared feature definition)

from crowgpt.progress import Run  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
DEVNULL = open(os.devnull, "w")

_ANALYZER = None  # one per worker process (see _worker_init)


def _worker_init():
    global _ANALYZER
    with contextlib.redirect_stdout(DEVNULL):
        _ANALYZER = Analyzer()


def window_for(by_start, second):
    aligned = 3 * (second // 3)
    if aligned in by_start:
        return by_start[aligned]
    if not by_start:
        return None
    nearest = min(by_start, key=lambda w: abs(w - second))
    return by_start[nearest] if abs(nearest - second) <= 3 else None


def _embed_file(item):
    """(path, [(second, labels)]) -> [(pooled_vec, labels)] for that file."""
    path, seglist = item
    try:
        with contextlib.redirect_stdout(DEVNULL):
            rec = Recording(_ANALYZER, path, min_conf=0.1)
            rec.extract_embeddings()
    except Exception as ex:  # noqa: BLE001
        print(f"  fail {Path(path).name}: {ex}", file=sys.stderr)
        return []
    by_start = {int(round(s["start_time"])): np.array(s["embeddings"])
                for s in rec.embeddings}
    out = []
    for second, labels in seglist:
        window = window_for(by_start, second)
        if window is None:
            continue
        vec = pool(window)
        if np.isfinite(vec).all():
            out.append((vec, labels))
    return out


def build(dataset, jobs):
    corpus = LabelCorpus(dataset=dataset)
    try:
        print(f"ingest build: reading {corpus.imported_path}", flush=True)
        by_file = defaultdict(list)
        for seg in corpus.labeled_segments(require_audio=True):
            by_file[str(seg.audio_path)].append((seg.start, sorted(seg.labels)))
    except FileNotFoundError as e:
        sys.exit(str(e))  # a broken checkout is a setup problem, not a crash
    if not by_file:
        sys.exit(f"No labelled segments with audio present for '{dataset}'. Has the "
                 f"audio been fetched into {LOCAL_AUDIO}?\n"
                 f"  python pipelines/ingest/import_crowtools.py --download")

    items = list(by_file.items())
    total = sum(len(v) for v in by_file.values())
    run = Run(f"ingest build — {dataset}", ["embed"])
    print(f"ingest build: {total} labelled segments across {len(items)} files "
          f"— {jobs} worker(s), embedding…", flush=True)

    X, Y, groups = [], [], []
    done = 0
    with run.stage("embed") as stage:
        stage.say(f"{total} segments across {len(items)} files, {jobs} worker(s)")
        for (path, _seglist), pairs in zip(items, _map(items, jobs)):
            file_id = Path(path).stem
            for vec, labels in pairs:
                X.append(vec)
                Y.append(labels)
                groups.append(file_id)  # so CV can keep a recording out of both splits
            done += 1
            if done % 100 == 0:
                stage.update(done, len(items))

    X = np.array(X)
    out_path = OUT / f"pooled_embeddings_crowtools_{dataset}.npz"
    np.savez(out_path, X=X, Y=np.array(Y, dtype=object),
             groups=np.array(groups), feature=FEATURE)

    per_class = Counter(c for labs in Y for c in labs)
    (OUT / f"summary_{dataset}.json").write_text(json.dumps(
        {"feature": FEATURE, "n_segments": int(len(Y)),
         "dim": int(X.shape[1]) if len(X) else 0,
         "per_class_positives": dict(per_class.most_common())}, indent=2))

    run.note(f"wrote {len(Y)} pooled segments -> {out_path}")
    print(f"ingest build: done — wrote {len(Y)} pooled segments -> {out_path}",
          flush=True)
    print("per-class positives:", dict(per_class.most_common()))
    print("\nevaluate with evaluate.py, or concatenate with the archive set "
          "(see README).")


def _map(items, jobs):
    if jobs <= 1:
        _worker_init()
        return map(_embed_file, items)
    ex = ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init)
    return ex.map(_embed_file, items, chunksize=4)


def main():
    default_jobs = max(1, (os.cpu_count() or 2) - 2)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="all-public",
                        choices=["starter", "all-public"])
    parser.add_argument("--jobs", type=int, default=default_jobs,
                        help=f"worker processes (default: {default_jobs})")
    args = parser.parse_args()
    build(args.dataset, args.jobs)


if __name__ == "__main__":
    main()
