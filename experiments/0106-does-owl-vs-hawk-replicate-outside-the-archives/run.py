"""0106 — the frozen 0102 owl-versus-hawk model, scored once on recordings outside the two archives.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0106-does-owl-vs-hawk-replicate-outside-the-archives/run.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0106-replication"
ARCHIVE_CACHE = DATA_DIR / "experiments" / "0102-archive-remarks"
ARCHIVE_LABELS = REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "experiments" / "0102-archive-remarks-semantics"))
from crowgpt.progress import Run  # noqa: E402
import run as exp102  # noqa: E402

MEAN_DIM = 1024
MIN_EVENTS = 15
RAPTOR_LIMIT = 0.05


def _duty(task):
    recording_id, path = task
    from importlib import util

    spec = util.spec_from_file_location(
        "exp105", REPO / "experiments" / "0105-does-calling-change-when-the-recordist-says-so" / "run.py")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    intensity = module.CallingIntensity(Path(path))
    return recording_id, intensity.duty_cycle(0.0, intensity.duration_s)


def head():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced"))


class ArchiveModel:
    """0102's mean-only owl-versus-hawk head, fit once on every strict archive recording."""

    def __init__(self):
        meta = json.loads((ARCHIVE_CACHE / "records.json").read_text())
        features = np.load(ARCHIVE_CACHE / "features.npz")
        committed = {(r["source"], str(r["source_ref"])): r["context"]
                     for r in json.loads(ARCHIVE_LABELS.read_text()) if r["witnessed"]}
        rows = [
            i for i, r in enumerate(meta)
            if r["slug"] == "american-crow" and r["witnessed"] and features["has_clean"][i]
            and r["context"] in ("owl_mobbing", "hawk_mobbing")
            and committed.get((r["source"], str(r["source_ref"]))) == r["context"]
            and not r["pred_vocal"] and r["max_raptor_conf"] < RAPTOR_LIMIT
        ]
        y = np.array([meta[i]["context"] == "owl_mobbing" for i in rows]).astype(int)
        self.trained_on = {"n": len(rows), "owl": int(y.sum()), "hawk": int((1 - y).sum())}
        self.model = head().fit(features["emb_clean"][rows][:, :MEAN_DIM], y)

    def score(self, embeddings: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(embeddings)[:, 1]


class SealedSet:
    """The labelled recordings outside the archives, with 0102's features extracted unchanged."""

    def __init__(self, run: Run):
        self.labels = json.loads((HERE / "labels.json").read_text())["labels"]
        self.records = self._extract(run)

    def _paths(self) -> dict:
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        out = {}
        for label in self.labels:
            raw, observer = db.execute(
                "SELECT file_path, recordist FROM recordings WHERE id = ?", (label["recording_id"],)).fetchone()
            out[label["recording_id"]] = (exp102.resolve_audio_path(raw), observer)
        return out

    def _extract(self, run: Run) -> list[dict]:
        cache = CACHE / "records.json"
        paths = self._paths()
        if cache.exists():
            with run.stage("extract") as stage:
                stage.update(1, 1, extra="cached")
            return json.loads(cache.read_text())
        tasks = [(i, str(p), "american-crow") for i, (p, _) in paths.items() if p is not None]
        results = {}
        with run.stage("extract") as stage, ProcessPoolExecutor(
                max_workers=12, initializer=exp102._init_worker) as pool:
            futures = [pool.submit(exp102.process_one, t) for t in tasks]
            for done, future in enumerate(as_completed(futures), 1):
                result = future.result()
                results[result["id"]] = result
                if done % 5 == 0 or done == len(tasks):
                    stage.update(done, len(tasks))
        duties = {}
        with run.stage("duty") as stage, ProcessPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(_duty, (i, t[1])) for i, t in zip([t[0] for t in tasks], tasks)]
            for done, future in enumerate(as_completed(futures), 1):
                recording_id, duty = future.result()
                duties[recording_id] = duty
                stage.update(done, len(tasks))
        records = []
        for label in self.labels:
            result = results.get(label["recording_id"])
            if result is None or not result["ok"]:
                records.append({**label, "ok": False})
                continue
            clean = result["emb_clean_crow"]
            crow = result["emb_crow"]
            records.append({
                **label, "ok": True,
                "observer": paths[label["recording_id"]][1],
                "duration_s": result["duration_s"],
                "max_raptor_conf": result["max_raptor_conf"],
                "n_crow_segs": result["n_crow_segs"],
                "n_clean_crow_segs": result["n_clean_crow_segs"],
                "mean_clean": clean[:MEAN_DIM].tolist() if clean is not None else None,
                "mean_crow": crow[:MEAN_DIM].tolist() if crow is not None else None,
                "duty": duties.get(label["recording_id"]),
            })
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(records))
        return records

    def strict(self) -> list[dict]:
        return [r for r in self.records
                if r["ok"] and r["mean_clean"] is not None and r["max_raptor_conf"] < RAPTOR_LIMIT]

    def non_strict(self) -> list[dict]:
        return [r for r in self.records if r["ok"] and r["mean_crow"] is not None]


class EventScores:
    """Recording scores averaged within an event, and the statistics over events."""

    def __init__(self, records: list[dict], scores: np.ndarray):
        grouped = defaultdict(list)
        for record, score in zip(records, scores):
            grouped[(record["event"], record["context"])].append(float(score))
        self.y = np.array([context == "owl_mobbing" for (_, context) in grouped]).astype(int)
        self.scores = np.array([np.mean(v) for v in grouped.values()])
        self.recordings = len(records)

    def report(self, resamples: int = 5000) -> dict:
        owl, hawk = int(self.y.sum()), int((1 - self.y).sum())
        out = {"recordings": self.recordings, "owl_events": owl, "hawk_events": hawk,
               "interpretable": min(owl, hawk) >= MIN_EVENTS}
        if min(owl, hawk) < 2:
            return out
        out["auc"] = round(float(roc_auc_score(self.y, self.scores)), 4)
        out["p_two_sided"] = round(float(mannwhitneyu(
            self.scores[self.y == 1], self.scores[self.y == 0], alternative="two-sided").pvalue), 4)
        rng = np.random.default_rng(0)
        boot = []
        for _ in range(resamples):
            picked = rng.integers(0, len(self.y), len(self.y))
            if 0 < self.y[picked].sum() < len(picked):
                boot.append(roc_auc_score(self.y[picked], self.scores[picked]))
        out["ci95"] = [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]
        return out


def in_domain(records: list[dict]) -> dict | None:
    events = {(r["event"], r["context"]) for r in records}
    counts = [sum(1 for _, c in events if c == k) for k in ("owl_mobbing", "hawk_mobbing")]
    if min(counts) < 30:
        return {"skipped": f"needs 30 events a class, has {counts[0]} owl and {counts[1]} hawk"}
    X = np.array([r["mean_clean"] for r in records])
    y = np.array([r["context"] == "owl_mobbing" for r in records]).astype(int)
    groups = np.array([r["observer"] or r["event"] for r in records])
    scores = np.zeros(len(y))
    for train, test in StratifiedGroupKFold(n_splits=5).split(X, y, groups):
        scores[test] = head().fit(X[train], y[train]).predict_proba(X[test])[:, 1]
    return EventScores(records, scores).report()


def main():
    run = Run("0106 replication outside the archives", ["extract", "duty", "score"])
    sealed = SealedSet(run)
    with run.stage("score") as stage:
        model = ArchiveModel()
        strict, loose = sealed.strict(), sealed.non_strict()
        report = {
            "trained_on": model.trained_on,
            "labelled_recordings": len(sealed.labels),
            "extracted_ok": sum(1 for r in sealed.records if r["ok"]),
            "primary_frozen_model_strict": EventScores(
                strict, model.score(np.array([r["mean_clean"] for r in strict]))).report(),
            "secondary_duty_alone_strict": EventScores(
                strict, np.array([r["duty"] for r in strict])).report(),
            "secondary_frozen_model_non_strict": EventScores(
                loose, model.score(np.array([r["mean_crow"] for r in loose]))).report(),
            "secondary_in_domain": in_domain(strict),
            "strict_medians": {
                c: {"duty": round(float(np.median([r["duty"] for r in strict if r["context"] == c])), 4),
                    "duration_s": round(float(np.median([r["duration_s"] for r in strict if r["context"] == c])), 1)}
                for c in ("owl_mobbing", "hawk_mobbing")},
        }
        stage.update(1, 1)
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    run.note(f"frozen model AUC {report['primary_frozen_model_strict'].get('auc')}")


if __name__ == "__main__":
    main()
