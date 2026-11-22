"""Per-window BirdNET embeddings for the witnessed begging clips and the field labels.

The shipped head's training rows are single 3 s windows run through
`pooling.pool`, so that is what has to be extracted here — experiment 0102's
cache holds one vector per whole clip, which is a different kind of feature.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0108-do-witnessed-begging-clips-help/extract.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
OUT_DIR = DATA_DIR / "experiments" / "0108-begging"
CORPUS_DB = DATA_DIR / "corvid.db"
LABELS_0102 = REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json"
CROWTOOLS_LABELS = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(REPO / "experiments" / "0102-archive-remarks-semantics"))

import media  # noqa: E402
import run as exp102  # noqa: E402
from crowgpt.progress import Run  # noqa: E402

LIBRARY_SOURCE = {"library-1": "macaulay", "library-2": "xeno_canto"}
MIN_CONF = 0.05
_ANALYZER = None
_DEVNULL = None


def _init_worker():
    global _ANALYZER, _DEVNULL
    from birdnetlib.analyzer import Analyzer

    _DEVNULL = open(os.devnull, "w")
    with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
        _ANALYZER = Analyzer()


def _embed(task):
    key, path = task
    from birdnetlib import Recording

    try:
        with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
            rec = Recording(_ANALYZER, path, min_conf=MIN_CONF)
            rec.analyze()
            rec.extract_embeddings()
    except Exception as ex:  # noqa: BLE001
        return key, None, str(ex)
    crow = {}
    for det in rec.detections or []:
        if exp102._is_corvid(det.get("common_name", ""), det.get("scientific_name", "")):
            start = round(float(det["start_time"]), 2)
            crow[start] = max(crow.get(start, 0.0), float(det["confidence"]))
    windows = []
    for seg in rec.embeddings or []:
        emb = np.asarray(seg["embeddings"], dtype=np.float32)
        if np.isfinite(emb).all():
            start = round(float(seg["start_time"]), 2)
            windows.append((start, crow.get(start, 0.0), emb))
    return key, windows, None


class WindowStore:
    """One row per 3 s window: which recording, when, how sure of a crow, the embedding."""

    def __init__(self):
        self.keys, self.starts, self.crow, self.embs = [], [], [], []
        self.failed = {}

    def add(self, key, windows):
        for start, conf, emb in windows:
            self.keys.append(key)
            self.starts.append(start)
            self.crow.append(conf)
            self.embs.append(emb)

    def save(self, path, **extra):
        np.savez(
            path,
            key=np.array(self.keys),
            start=np.array(self.starts, dtype=np.float32),
            crow_conf=np.array(self.crow, dtype=np.float32),
            emb=np.stack(self.embs) if self.embs else np.zeros((0, 1024), np.float32),
            **extra,
        )


class BeggingClips:
    """The witnessed begging recordings, and which of them crow-tools already holds."""

    def __init__(self):
        rows = json.loads(LABELS_0102.read_text())
        self.rows = [r for r in rows
                     if r["slug"] == "american-crow" and r["context"] == "begging"
                     and r["witnessed"]]
        libraries = json.loads(CROWTOOLS_LABELS.read_text())["libraries"]
        self.reviewed = {(LIBRARY_SOURCE.get(lib), ref) for ref, lib in libraries.items()}

    def already_reviewed(self, row):
        return (row["source"], str(row["source_ref"])) in self.reviewed

    def tasks(self):
        con = sqlite3.connect(f"file:{CORPUS_DB}?mode=ro", uri=True)
        out = []
        for r in self.rows:
            found = con.execute("SELECT file_path FROM recordings WHERE id = ?",
                                (r["id"],)).fetchone()
            path = exp102.resolve_audio_path(found[0]) if found and found[0] else None
            if path:
                out.append((str(r["id"]), str(path)))
        con.close()
        return out

    def manifest(self):
        return [{"id": r["id"], "source": r["source"], "source_ref": str(r["source_ref"]),
                 "recordist": r.get("recordist"), "date": r.get("date"),
                 "already_reviewed": self.already_reviewed(r)} for r in self.rows]


class FieldLabels:
    """Human call-type labels in the field database that carry a span."""

    def __init__(self):
        con = sqlite3.connect(f"file:{media.field_db()}?mode=ro", uri=True)
        self.rows = con.execute(
            "SELECT id, capture_id, start_sec, end_sec, call_type FROM labels "
            "WHERE label_source = 'human' AND start_sec IS NOT NULL "
            "AND end_sec IS NOT NULL ORDER BY id").fetchall()
        self.total = con.execute(
            "SELECT call_type, COUNT(*) FROM labels WHERE label_source = 'human' "
            "GROUP BY 1").fetchall()
        con.close()

    def tasks(self):
        out = []
        for capture in sorted({r[1] for r in self.rows}):
            try:
                out.append((str(capture), str(media.audio_for(capture))))
            except SystemExit:
                continue
        return out

    def manifest(self):
        return [{"label_id": r[0], "capture_id": r[1], "start": r[2], "end": r[3],
                 "call_type": r[4]} for r in self.rows]


def embed_all(tasks, stage, workers):
    store = WindowStore()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
        futures = [pool.submit(_embed, t) for t in tasks]
        for done, fut in enumerate(as_completed(futures), 1):
            key, windows, error = fut.result()
            if windows is None:
                store.failed[key] = error
            else:
                store.add(key, windows)
            stage.update(done, len(tasks))
    return store


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run = Run("0108 begging window extraction", ["archive_clips", "field_labels"])
    clips, field = BeggingClips(), FieldLabels()

    with run.stage("archive_clips") as stage:
        store = embed_all(clips.tasks(), stage, workers=16)
        store.save(OUT_DIR / "clip_windows.npz")
    (OUT_DIR / "clips.json").write_text(json.dumps(
        {"clips": clips.manifest(), "failed": store.failed}, indent=1))

    with run.stage("field_labels") as stage:
        fstore = embed_all(field.tasks(), stage, workers=8)
        fstore.save(OUT_DIR / "field_windows.npz")
    (OUT_DIR / "field_labels.json").write_text(json.dumps(
        {"labels": field.manifest(), "human_label_totals": field.total,
         "failed": fstore.failed}, indent=1))

    run.note(f"{len(set(store.keys))} clips, {len(store.keys)} windows; "
             f"{len(set(fstore.keys))} field captures")
    print(f"clips embedded {len(set(store.keys))}/{len(clips.rows)}, "
          f"windows {len(store.keys)}, failed {len(store.failed)}")
    print(f"field captures {len(set(fstore.keys))}, spans {len(field.rows)}, "
          f"human totals {field.total}")


if __name__ == "__main__":
    main()
