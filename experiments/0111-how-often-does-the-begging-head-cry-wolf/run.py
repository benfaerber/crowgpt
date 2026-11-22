"""0111 — the frozen recording-level begging head against ordinary recordings.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0111-how-often-does-the-begging-head-cry-wolf/run.py
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0111-begging-false-alarms"
SEGMENT_CACHE = DATA_DIR / "experiments" / "0109-crow-count" / "segments.npz"
SEALED_CACHE = DATA_DIR / "experiments" / "0110-contexts" / "records.json"
CONTEXT_EXPERIMENT = REPO / "experiments" / "0110-which-contexts-are-readable-outside-the-archives"
CROWTOOLS_LABELS = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"
FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"
LIBRARY_SOURCE = {"library-1": "macaulay", "library-2": "xeno_canto"}
CALL_TYPES = ("mob", "alert", "scold", "rattle", "softSong", "grief")
WINTER, SUMMER = ("11", "12", "01", "02"), ("06", "07")
DRAW = 400
ARCHIVE_RECALL = 0.90

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402

_spec = util.spec_from_file_location("exp110", CONTEXT_EXPERIMENT / "run.py")
exp110 = util.module_from_spec(_spec)
sys.modules["exp110"] = exp110
_spec.loader.exec_module(exp110)
exp102 = exp110.exp102


def wilson(hits: int, n: int) -> dict:
    if n == 0:
        return {"hits": 0, "n": 0}
    z, p = 1.96, hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {"hits": hits, "n": n, "rate": round(p, 4),
            "ci95": [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]}


class FrozenBeggingHead:
    """0110's begging head, plus a threshold taken from its own training recordings."""

    def __init__(self):
        self.model = exp110.ArchiveHeads("emb_clean", "has_clean").models["begging"]
        meta = json.loads((exp110.ARCHIVE_CACHE / "records.json").read_text())
        features = np.load(exp110.ARCHIVE_CACHE / "features.npz")
        committed = {(r["source"], str(r["source_ref"])): r["context"]
                     for r in json.loads(exp110.ARCHIVE_LABELS.read_text()) if r["witnessed"]}
        rows = [
            i for i, r in enumerate(meta)
            if r["slug"] == "american-crow" and r["witnessed"] and features["has_clean"][i]
            and r["context"] in exp110.ARCHIVE_CONTEXT
            and committed.get((r["source"], str(r["source_ref"]))) == r["context"]
        ]
        X = features["emb_clean"][rows][:, :exp110.MEAN_DIM]
        y = np.array([meta[i]["context"] == "begging" for i in rows]).astype(int)
        recordists = np.array([(meta[i]["recordist"] or f"row:{i}").strip().lower() for i in rows])
        self.training_files = {(meta[i]["source"], str(meta[i]["source_ref"])) for i in rows}
        self.begging_recordists = set(recordists[y == 1])
        held_out = np.zeros(len(y))
        for train, test in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X, y, recordists):
            held_out[test] = exp110.head().fit(X[train], y[train]).decision_function(X[test])
        self.threshold = float(np.quantile(held_out[y == 1], 1 - ARCHIVE_RECALL))
        self.archive = {"recordings": len(y), "begging": int(y.sum()),
                        "held_out_false_alarms_at_T": wilson(int((held_out[y == 0] >= self.threshold).sum()),
                                                             int((1 - y).sum()))}

    def score(self, embeddings) -> np.ndarray:
        return self.model.decision_function(np.asarray(embeddings, dtype=np.float32))


class Firing:
    """How often a set of scores crosses each of the two thresholds."""

    def __init__(self, head: FrozenBeggingHead):
        self.cuts = {"at_T": head.threshold, "at_zero": 0.0}

    def rates(self, scores) -> dict:
        scores = np.asarray(scores)
        return {name: wilson(int((scores >= cut).sum()), len(scores)) for name, cut in self.cuts.items()}


class HandLabelledFiles:
    """Files of hand-reviewed segments, one mean embedding each, split by the begging flag."""

    def __init__(self, head: FrozenBeggingHead):
        from corpus import LabelCorpus

        segments = [s for s in LabelCorpus().labeled_segments() if s.flags.get("crowCount") in (1, 2, 4)]
        saved = np.load(SEGMENT_CACHE)
        segments = [s for s, present in zip(segments, saved["present"]) if present]
        libraries = json.loads(CROWTOOLS_LABELS.read_text())["libraries"]
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        windows, flags = defaultdict(list), defaultdict(Counter)
        for segment, embedding in zip(segments, saved["X"]):
            windows[segment.file_id].append(embedding)
            flags[segment.file_id].update(f for f in CALL_TYPES + ("begging",) if segment.flags.get(f))
        self.rows = []
        for file_id, stack in windows.items():
            source = LIBRARY_SOURCE.get(libraries.get(file_id))
            if (source, file_id) in head.training_files:
                continue
            row = db.execute("SELECT recordist FROM recordings WHERE source = ? AND source_ref = ?",
                             (source, file_id)).fetchone()
            recordist = (row[0] or "").strip().lower() if row else ""
            others = [f for f in CALL_TYPES if flags[file_id][f]]
            self.rows.append({
                "begging": flags[file_id]["begging"] > 0,
                "call_type": max(others, key=lambda f: flags[file_id][f]) if others else "none",
                "training_recordist": recordist in head.begging_recordists,
                "score": float(head.score([np.mean(stack, axis=0)])[0]),
            })

    def report(self, firing: Firing) -> dict:
        quiet = [r for r in self.rows if not r["begging"]]
        begging = [r for r in self.rows if r["begging"]]
        return {
            "false_alarms": firing.rates([r["score"] for r in quiet]),
            "recall": firing.rates([r["score"] for r in begging]),
            "recall_without_training_recordists": firing.rates(
                [r["score"] for r in begging if not r["training_recordist"]]),
            "false_alarms_by_call_type": {
                call_type: firing.rates([r["score"] for r in quiet if r["call_type"] == call_type])["at_T"]
                for call_type in CALL_TYPES + ("none",) if any(r["call_type"] == call_type for r in quiet)},
        }


class Extraction:
    """0102's feature extraction over arbitrary audio paths, cached by name."""

    def __init__(self, run: Run):
        self.run = run

    def clean_means(self, name: str, paths: dict, stage) -> dict:
        cache = CACHE / f"{name}.json"
        if cache.exists():
            return {int(k): v for k, v in json.loads(cache.read_text()).items()}
        tasks = [(key, str(path), "american-crow") for key, path in paths.items() if path.exists()]
        out = {}
        with ProcessPoolExecutor(max_workers=12, initializer=exp102._init_worker) as pool:
            futures = [pool.submit(exp102.process_one, t) for t in tasks]
            for done, future in enumerate(as_completed(futures), 1):
                result = future.result()
                clean = result.get("emb_clean_crow") if result["ok"] else None
                out[result["id"]] = clean[:exp110.MEAN_DIM].tolist() if clean is not None else None
                if done % 10 == 0 or done == len(tasks):
                    stage(done, len(tasks))
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
        return out


class SeasonalDraw:
    """Random recordings from the rest of the corpus in the months when young are absent, and present."""

    def __init__(self):
        coded = {r["recording_id"] for r in json.loads((CONTEXT_EXPERIMENT / "labels.json").read_text())["labels"]}
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        rows = db.execute(
            "SELECT id, date, file_path FROM recordings WHERE source NOT IN ('macaulay', 'xeno_canto') "
            "AND species LIKE '%American Crow%' AND downloaded = 1 ORDER BY id").fetchall()
        self.paths = {}
        self.season = {}
        for season, months in (("winter", WINTER), ("summer", SUMMER)):
            pool = [(i, path) for i, date, path in rows if (date or "")[5:7] in months and i not in coded]
            for i, path in random.Random(0).sample(pool, DRAW):
                self.paths[i] = exp102.resolve_audio_path(path)
                self.season[i] = season

    def report(self, means: dict, head: FrozenBeggingHead, firing: Firing) -> dict:
        out = {}
        for season in ("winter", "summer"):
            usable = [means[i] for i, s in self.season.items() if s == season and means.get(i) is not None]
            out[season] = {"drawn": DRAW, "with_clean_crow_window": len(usable),
                           **firing.rates(head.score(usable))}
        return out


class KeptCaptures:
    """Ben's kept field captures and the call types a person has put on them."""

    def __init__(self):
        db = sqlite3.connect(f"file:{FIELD_DB}?mode=ro", uri=True)
        self.rows = db.execute(
            "SELECT c.id, substr(c.recorded_at, 1, 10), c.juvenile_count, "
            "(SELECT group_concat(DISTINCT l.call_type) FROM labels l WHERE l.capture_id = c.id), "
            "(SELECT m.storage_ref FROM media m WHERE m.capture_id = c.id AND m.kind = 'audio' LIMIT 1) "
            "FROM captures c WHERE c.keep = 1 ORDER BY c.id").fetchall()
        self.paths = {r[0]: FIELD_DB.parent / "media" / r[4] for r in self.rows if r[4]}

    def report(self, means: dict, head: FrozenBeggingHead) -> list[dict]:
        out = []
        for capture_id, day, juveniles, labels, _ in self.rows:
            mean = means.get(capture_id)
            score = float(head.score([mean])[0]) if mean is not None else None
            out.append({"capture": capture_id, "date": day, "juveniles_noted": juveniles,
                        "human_labels": sorted(labels.split(",")) if labels else [],
                        "score": round(score, 3) if score is not None else None,
                        "fires_at_T": bool(score >= head.threshold) if score is not None else None})
        return out


def sealed_begging_recall(head: FrozenBeggingHead, firing: Firing) -> dict:
    by_event = defaultdict(list)
    for record in json.loads(SEALED_CACHE.read_text()):
        if record["ok"] and record["context"] == "begging" and record["mean_clean"] is not None:
            by_event[record["event"]].append(float(head.score([record["mean_clean"]])[0]))
    return firing.rates([np.mean(v) for v in by_event.values()])


def main():
    run = Run("0111 begging head false alarms", ["extract", "score"])
    head = FrozenBeggingHead()
    firing = Firing(head)
    draw, captures = SeasonalDraw(), KeptCaptures()
    extraction = Extraction(run)
    total = len(draw.paths) + len(captures.paths)
    with run.stage("extract") as stage:
        seasonal = extraction.clean_means("seasonal", draw.paths, lambda i, n: stage.update(i, total))
        kept = extraction.clean_means("kept", captures.paths,
                                      lambda i, n: stage.update(len(draw.paths) + i, total))
        stage.update(total, total)
    with run.stage("score") as stage:
        report = {
            "threshold_T": round(head.threshold, 4),
            "archive": head.archive,
            "A_hand_labelled": HandLabelledFiles(head).report(firing),
            "B_seasonal": draw.report(seasonal, head, firing),
            "recall_on_0110_begging_events": sealed_begging_recall(head, firing),
            "C_kept_captures": captures.report(kept, head),
        }
        stage.update(1, 1)
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "C_kept_captures"}, indent=1))
    for row in report["C_kept_captures"]:
        print(row)
    run.note(f"winter false alarms {report['B_seasonal']['winter']['at_T'].get('rate')}")


if __name__ == "__main__":
    main()
