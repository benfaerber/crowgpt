#!/usr/bin/env python3
"""Build the two feature caches 0036 needs that do not exist yet.

Arms A, B, C, E1 and E3 all reuse the cached crow-tools features. Two arms
cannot:

  D  — the field-transfer smoke test needs Ben's own labelled spans embedded,
       and nothing has ever embedded them. Two poolings are written, not one:
       `X_span` pools every 3s BirdNET window the label covers (std != 0) and
       `X_win` pools the single window nearest the span's midpoint (std == 0).
       That split matters because 0025's preflight found the std block alone
       separates the two training corpora — crow-tools rows pool one window,
       archive rows pool whole clips. Scoring both says whether a transfer failure
       is about the domain or merely about the pooling.

  E2 — the explicit-negative arm needs crow-tools' `crowCount == 0` garbage
       segments, which corpus.labeled_segments() drops on purpose because they
       carry no CORE label. 587 exist, 578 have audio.

And it rebuilds the call-type features themselves, KEYED, because the shipped
cache can no longer be trusted to join. `pooled_embeddings_crowtools_all-public.npz`
stores only (X, Y, groups), so recovering a row's raw flags means matching cached
rows to corpus segments BY POSITION within a file — which is what 0012 did, and
which was sound when it ran. It is not sound now: the cache holds 2,494 rows
while only 2,339 segments still have audio, across 98 files whose counts
disagree, and within at least one file the label order is a permutation of the
cached order. A positional join there would hand one call's flags to another
call's audio and every number downstream would be noise wearing a decimal point.

So this writes `crowtools_keyed.npz` with the segment key on every row and the
flags beside it. The join stops being an assumption. The cost is that n falls
from 2,494 to ~2,339 — the rows whose audio is actually present, which is the
same 2,339 experiment 0025 used, so these numbers sit next to 0025's rather than
0012's.

Runs in the BirdNET venv (birdnetlib + numpy<2):
  ../../pipelines/representation/.venv-birdnet/bin/python prepare.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
DEVNULL = open(os.devnull, "w")

FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"
FIELD_MEDIA = REPO / "fieldserver" / "instance" / "media"

sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
sys.path.insert(0, str(REPO / "pipelines" / "training"))
from corpus import LabelCorpus  # noqa: E402
from pooling import FEATURE, pool  # noqa: E402

_ANALYZER = None


def progress(msg):
    print(msg, flush=True)


def _worker_init():
    global _ANALYZER
    with contextlib.redirect_stdout(DEVNULL):
        _ANALYZER = Analyzer()


def _windows(path):
    """{aligned_start_second: 1024-d vector} for one file, or None on failure."""
    try:
        with contextlib.redirect_stdout(DEVNULL):
            rec = Recording(_ANALYZER, str(path), min_conf=0.1)
            rec.extract_embeddings()
    except Exception as ex:  # noqa: BLE001
        print(f"  fail {Path(path).name}: {ex}", file=sys.stderr)
        return None
    return {int(round(s["start_time"])): np.array(s["embeddings"])
            for s in rec.embeddings}


# --------------------------------------------------------------------------
# Arm D — Ben's own labelled spans
# --------------------------------------------------------------------------

def field_rows():
    """Every human field label whose audio is on disk, with its span."""
    con = sqlite3.connect(FIELD_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT l.id, l.capture_id, l.call_type, l.start_sec, l.end_sec, "
        "       l.species, c.keep, m.storage_ref "
        "FROM labels l "
        "JOIN media m ON m.id = l.media_id "
        "JOIN captures c ON c.id = l.capture_id "
        "WHERE l.label_source = 'human' "
        "ORDER BY l.capture_id, l.start_sec"
    ).fetchall()
    con.close()

    by_file = defaultdict(list)
    dropped = 0
    for r in rows:
        path = FIELD_MEDIA / r["storage_ref"]
        if not path.exists() or r["start_sec"] is None:
            dropped += 1
            continue
        by_file[str(path)].append(dict(r))
    return by_file, dropped


def _embed_field(item):
    path, labels = item
    by_start = _windows(path)
    if not by_start:
        return []
    starts = sorted(by_start)
    out = []
    for lab in labels:
        s, e = float(lab["start_sec"]), float(lab["end_sec"])
        covered = [by_start[w] for w in starts if w < e and (w + 3.0) > s]
        if not covered:
            continue
        mid = (s + e) / 2.0
        nearest = min(starts, key=lambda w: abs((w + 1.5) - mid))
        out.append((lab, pool(covered), pool(by_start[nearest])))
    return out


def build_field(jobs):
    by_file, dropped = field_rows()
    if not by_file:
        progress("0036 prepare: no field labels with audio — arm D cannot run")
        return
    total = sum(len(v) for v in by_file.values())
    progress(f"0036 prepare: {total} field labels across {len(by_file)} captures "
             f"({dropped} dropped for missing audio/span) — embedding…")

    items = list(by_file.items())
    X_span, X_win, meta = [], [], []
    for pairs in _map(items, jobs, _embed_field):
        for lab, v_span, v_win in pairs:
            X_span.append(v_span)
            X_win.append(v_win)
            meta.append(lab)

    if not meta:
        progress("0036 prepare: every field label failed to embed — arm D skipped")
        return

    np.savez(
        OUT / "field_labels.npz",
        X_span=np.array(X_span), X_win=np.array(X_win),
        y=np.array([m["call_type"] for m in meta]),
        groups=np.array([str(m["capture_id"]) for m in meta]),
        keep=np.array([int(m["keep"] or 0) for m in meta]),
        label_id=np.array([int(m["id"]) for m in meta]),
        duration=np.array([float(m["end_sec"]) - float(m["start_sec"]) for m in meta]),
        feature=FEATURE,
    )
    kept = sum(1 for m in meta if m["keep"])
    progress(f"0036 prepare: wrote {len(meta)} field rows "
             f"({kept} on kept captures) -> results/field_labels.npz")


# --------------------------------------------------------------------------
# Arm E2 — crow-tools' deliberately-collected garbage
# --------------------------------------------------------------------------

def garbage_rows():
    """Reviewed segments with no CORE label and crowCount == 0, audio present."""
    corpus = LabelCorpus(dataset="all-public")
    index = corpus.audio_index()
    by_file = defaultdict(list)
    for key, flags in corpus.labels().items():
        if not flags.get("reviewed") or corpus.core_labels(flags):
            continue
        if flags.get("crowCount") != 0:
            continue
        file_id, start, _end = key.rsplit("-", 2)
        found = index.get(file_id)
        if found is None:
            continue
        by_file[str(found[1])].append((int(start), flags))
    return by_file


def _embed_garbage(item):
    path, seglist = item
    by_start = _windows(path)
    if not by_start:
        return []
    starts = sorted(by_start)
    out = []
    for second, flags in seglist:
        aligned = 3 * (second // 3)
        if aligned not in by_start:
            nearest = min(starts, key=lambda w: abs(w - second))
            if abs(nearest - second) > 3:
                continue
            aligned = nearest
        vec = pool(by_start[aligned])
        if np.isfinite(vec).all():
            out.append((vec, Path(path).stem, flags))
    return out


def build_garbage(jobs):
    by_file = garbage_rows()
    if not by_file:
        progress("0036 prepare: no garbage segments with audio — arm E2 skipped")
        return
    total = sum(len(v) for v in by_file.values())
    progress(f"0036 prepare: {total} crowCount=0 segments across {len(by_file)} "
             f"files — embedding…")

    items = list(by_file.items())
    X, groups, quality = [], [], []
    done = 0
    for pairs in _map(items, jobs, _embed_garbage):
        for vec, file_id, flags in pairs:
            X.append(vec)
            groups.append(file_id)
            quality.append(int(flags.get("quality") or 0))
        done += 1
        if done % 100 == 0:
            progress(f"0036 prepare: garbage {done}/{len(items)} files")

    np.savez(OUT / "garbage.npz", X=np.array(X), groups=np.array(groups),
             quality=np.array(quality), feature=FEATURE)
    progress(f"0036 prepare: wrote {len(X)} garbage rows -> results/garbage.npz")


# --------------------------------------------------------------------------
# The call-type corpus, rebuilt with a key on every row
# --------------------------------------------------------------------------

def _embed_calls(item):
    path, seglist = item
    by_start = _windows(path)
    if not by_start:
        return []
    starts = sorted(by_start)
    out = []
    for second, labels, flags in seglist:
        aligned = 3 * (second // 3)
        if aligned not in by_start:
            nearest = min(starts, key=lambda w: abs(w - second))
            if abs(nearest - second) > 3:
                continue
            aligned = nearest
        vec = pool(by_start[aligned])
        if np.isfinite(vec).all():
            out.append((vec, Path(path).stem, second, sorted(labels), flags))
    return out


def build_calls(jobs):
    corpus = LabelCorpus(dataset="all-public")
    by_file = defaultdict(list)
    for seg in corpus.labeled_segments(require_audio=True):
        by_file[str(seg.audio_path)].append((seg.start, seg.labels, seg.flags))
    if not by_file:
        progress("0036 prepare: no labelled segments with audio — cannot continue")
        return
    total = sum(len(v) for v in by_file.values())
    progress(f"0036 prepare: {total} labelled segments across {len(by_file)} files "
             f"— re-embedding with keys…")

    items = list(by_file.items())
    X, groups, starts, labels, flags = [], [], [], [], []
    done = 0
    for pairs in _map(items, jobs, _embed_calls):
        for vec, file_id, second, labs, flg in pairs:
            X.append(vec)
            groups.append(file_id)
            starts.append(second)
            labels.append(labs)
            flags.append(flg)
        done += 1
        if done % 200 == 0:
            progress(f"0036 prepare: calls {done}/{len(items)} files")

    np.savez(OUT / "crowtools_keyed.npz",
             X=np.array(X), groups=np.array(groups), starts=np.array(starts),
             labels=np.array(labels, dtype=object), feature=FEATURE)
    (OUT / "crowtools_flags.json").write_text(json.dumps(
        [{"key": f"{g}-{s}", "flags": f} for g, s, f in zip(groups, starts, flags)]))
    progress(f"0036 prepare: wrote {len(X)} keyed call rows over "
             f"{len(set(groups))} recordings -> results/crowtools_keyed.npz")


def _map(items, jobs, fn):
    if jobs <= 1:
        _worker_init()
        return map(fn, items)
    ex = ProcessPoolExecutor(max_workers=jobs, initializer=_worker_init)
    return ex.map(fn, items, chunksize=2)


def main():
    jobs = max(1, (os.cpu_count() or 2) - 2)
    progress(f"0036 prepare: starting, {jobs} workers")
    if not (OUT / "field_labels.npz").exists():
        build_field(jobs)
    if not (OUT / "garbage.npz").exists():
        build_garbage(jobs)
    build_calls(jobs)
    progress("0036 prepare: done")


if __name__ == "__main__":
    main()
