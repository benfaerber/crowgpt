"""0110 — frozen archive context heads, scored once on described recordings outside the archives.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0110-which-contexts-are-readable-outside-the-archives/run.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import joblib
import numpy as np
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0110-contexts"
ARCHIVE_CACHE = DATA_DIR / "experiments" / "0102-archive-remarks"
ARCHIVE_LABELS = REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json"
EARLIER_SEALED = DATA_DIR / "experiments" / "0106-replication" / "records.json"
COUNT_HEAD = DATA_DIR / "experiments" / "0109-crow-count" / "count_head.joblib"
INTENSITY_SOURCE = REPO / "experiments" / "0105-does-calling-change-when-the-recordist-says-so" / "run.py"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "experiments" / "0102-archive-remarks-semantics"))
from crowgpt.progress import Run  # noqa: E402
import run as exp102  # noqa: E402

CONTEXTS = ("raptor_mobbing", "begging", "roost_gathering", "food_foraging", "flight_contact")
ARCHIVE_CONTEXT = {"owl_mobbing": "raptor_mobbing", "hawk_mobbing": "raptor_mobbing",
                   **{c: c for c in CONTEXTS[1:]}}
MEAN_DIM = 1024
MIN_EVENTS = 15


def _duty(task):
    recording_id, path = task
    spec = util.spec_from_file_location("exp105", INTENSITY_SOURCE)
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    intensity = module.CallingIntensity(Path(path))
    return recording_id, intensity.duty_cycle(0.0, intensity.duration_s)


def head():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced"))


class ArchiveHeads:
    """One head per context, fit once on the witnessed archive recordings of the five contexts."""

    def __init__(self, feature: str, present: str):
        meta = json.loads((ARCHIVE_CACHE / "records.json").read_text())
        features = np.load(ARCHIVE_CACHE / "features.npz")
        committed = {(r["source"], str(r["source_ref"])): r["context"]
                     for r in json.loads(ARCHIVE_LABELS.read_text()) if r["witnessed"]}
        rows = [
            i for i, r in enumerate(meta)
            if r["slug"] == "american-crow" and r["witnessed"] and features[present][i]
            and r["context"] in ARCHIVE_CONTEXT
            and committed.get((r["source"], str(r["source_ref"]))) == r["context"]
        ]
        contexts = np.array([ARCHIVE_CONTEXT[meta[i]["context"]] for i in rows])
        X = features[feature][rows][:, :MEAN_DIM]
        self.trained_on = {c: int((contexts == c).sum()) for c in CONTEXTS}
        self.models = {c: head().fit(X, (contexts == c).astype(int)) for c in CONTEXTS}

    def score(self, context: str, embeddings: np.ndarray) -> np.ndarray:
        return self.models[context].decision_function(embeddings)


class SealedSet:
    """The coded recordings outside the archives, with 0102's features extracted unchanged."""

    def __init__(self, run: Run):
        self.labels = json.loads((HERE / "labels.json").read_text())["labels"]
        self.records = [r for r in self._extract(run) if r["ok"]]

    def _extract(self, run: Run) -> list[dict]:
        cache = CACHE / "records.json"
        if cache.exists():
            with run.stage("extract") as stage:
                stage.update(1, 1, extra="cached")
            return json.loads(cache.read_text())
        earlier = {r["recording_id"]: r for r in json.loads(EARLIER_SEALED.read_text()) if r["ok"]}
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        paths, observers = {}, {}
        for label in self.labels:
            raw, observer = db.execute("SELECT file_path, recordist FROM recordings WHERE id = ?",
                                       (label["recording_id"],)).fetchone()
            observers[label["recording_id"]] = observer
            if label["recording_id"] not in earlier:
                paths[label["recording_id"]] = exp102.resolve_audio_path(raw)
        tasks = [(i, str(p), "american-crow") for i, p in paths.items() if p is not None and p.exists()]
        total = 2 * len(tasks)
        results, duties = {}, {}
        with run.stage("extract") as stage:
            with ProcessPoolExecutor(max_workers=12, initializer=exp102._init_worker) as pool:
                futures = [pool.submit(exp102.process_one, t) for t in tasks]
                for done, future in enumerate(as_completed(futures), 1):
                    result = future.result()
                    results[result["id"]] = result
                    if done % 5 == 0:
                        stage.update(done, total)
            with ProcessPoolExecutor(max_workers=12) as pool:
                futures = [pool.submit(_duty, (t[0], t[1])) for t in tasks if results[t[0]]["ok"]]
                for done, future in enumerate(as_completed(futures), 1):
                    recording_id, duty = future.result()
                    duties[recording_id] = duty
                    if done % 5 == 0 or done == len(futures):
                        stage.update(len(tasks) + done, total)
        records = []
        for label in self.labels:
            recording_id = label["recording_id"]
            base = {**label, "observer": observers[recording_id]}
            if recording_id in earlier:
                e = earlier[recording_id]
                records.append({**base, "ok": True, "mean_clean": e["mean_clean"],
                                "mean_crow": e["mean_crow"], "duty": e["duty"],
                                "duration_s": e["duration_s"]})
                continue
            result = results.get(recording_id)
            if result is None or not result["ok"]:
                records.append({**base, "ok": False})
                continue
            clean, crow = result["emb_clean_crow"], result["emb_crow"]
            records.append({**base, "ok": True,
                            "mean_clean": clean[:MEAN_DIM].tolist() if clean is not None else None,
                            "mean_crow": crow[:MEAN_DIM].tolist() if crow is not None else None,
                            "duty": duties.get(recording_id), "duration_s": result["duration_s"]})
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(records))
        return records

    def with_feature(self, feature: str, field: str) -> list[dict]:
        return [r for r in self.records if r[feature] is not None and r[field] is not None]


class Events:
    """Recording values averaged within an upload, with observer-level resampling."""

    def __init__(self, records: list[dict], values: dict[str, np.ndarray], field: str):
        grouped = defaultdict(lambda: defaultdict(list))
        self.label, self.observer = {}, {}
        for index, record in enumerate(records):
            event = record["event"]
            self.label[event] = record[field]
            self.observer[event] = record["observer"] or f"event:{event}"
            for name, column in values.items():
                grouped[name][event].append(float(column[index]))
        self.names = list(self.label)
        self.values = {name: np.array([np.mean(grouped[name][e]) for e in self.names]) for name in values}
        self.labels = np.array([self.label[e] for e in self.names])
        self.observers = np.array([self.observer[e] for e in self.names])

    def resamples(self, n: int = 5000):
        members = defaultdict(list)
        for index, observer in enumerate(self.observers):
            members[observer].append(index)
        keys = list(members)
        rng = np.random.default_rng(0)
        for _ in range(n):
            yield np.concatenate([members[keys[i]] for i in rng.integers(0, len(keys), len(keys))])

    def auc(self, y: np.ndarray, scores: np.ndarray) -> dict:
        positive, negative = int(y.sum()), int((1 - y).sum())
        out = {"events": positive, "other_events": negative,
               "interpretable": min(positive, negative) >= MIN_EVENTS}
        if min(positive, negative) < 2:
            return out
        out["auc"] = round(float(roc_auc_score(y, scores)), 4)
        out["p"] = float(mannwhitneyu(scores[y == 1], scores[y == 0], alternative="two-sided").pvalue)
        boot = [roc_auc_score(y[i], scores[i]) for i in self.resamples() if 0 < y[i].sum() < len(i)]
        out["ci95"] = [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]
        return out

    def residual(self, scores: np.ndarray, covariate: np.ndarray) -> np.ndarray:
        slope, intercept = np.polyfit(covariate, scores, 1)
        return scores - (slope * covariate + intercept)


def holm(reports: dict) -> None:
    family = sorted((c for c, r in reports.items() if r["interpretable"]), key=lambda c: reports[c]["p"])
    running = 0.0
    for rank, context in enumerate(family):
        running = max(running, min(1.0, (len(family) - rank) * reports[context]["p"]))
        reports[context]["p_holm"] = round(running, 5)
    for report in reports.values():
        if "p" in report:
            report["p"] = round(report["p"], 5)


def context_family(sealed: SealedSet, heads: ArchiveHeads, feature: str, count_head) -> dict:
    records = [r for r in sealed.with_feature(feature, "context") if r["context"] in CONTEXTS]
    X = np.array([r[feature] for r in records])
    crow = np.array([r["mean_crow"] for r in records])
    values = {c: heads.score(c, X) for c in CONTEXTS}
    values["duty"] = np.array([r["duty"] for r in records])
    if count_head is not None:
        values["count"] = count_head.decision_function(crow)
    events = Events(records, values, "context")
    primary, crowd = {}, {}
    for context in CONTEXTS:
        y = (events.labels == context).astype(int)
        primary[context] = events.auc(y, events.values[context])
        if min(y.sum(), len(y) - y.sum()) < 2:
            continue
        crowd[context] = {"duty_alone": events.auc(y, events.values["duty"]).get("auc")}
        if count_head is not None:
            crowd[context]["count_alone"] = events.auc(y, events.values["count"]).get("auc")
            after = events.auc(y, events.residual(events.values[context], events.values["count"]))
            crowd[context]["head_with_count_removed"] = {k: after.get(k) for k in ("auc", "ci95")}
    holm(primary)
    return {"recordings": len(records), "events": len(events.names),
            "observers": len(set(events.observers)), "trained_on": heads.trained_on,
            "contexts": primary, "crowd": crowd}


def count_transfer(sealed: SealedSet, count_head) -> dict:
    records = sealed.with_feature("mean_crow", "count_stated")
    scores = count_head.decision_function(np.array([r["mean_crow"] for r in records]))
    events = Events(records, {"count": scores, "duty": np.array([r["duty"] for r in records])}, "count_stated")
    stated = events.labels.astype(int)
    rho, p = spearmanr(stated, events.values["count"])
    boot = [spearmanr(stated[i], events.values["count"][i])[0] for i in events.resamples(2000)]
    one_against_more = events.auc((stated > 1).astype(int), events.values["count"])
    duty_rho, duty_p = spearmanr(stated, events.values["duty"])
    return {"events": {str(k): int((stated == k).sum()) for k in (1, 2, 3)},
            "spearman": round(float(rho), 4), "p": round(float(p), 5),
            "ci95": [round(float(np.nanpercentile(boot, 2.5)), 4), round(float(np.nanpercentile(boot, 97.5)), 4)],
            "one_against_more": {k: one_against_more.get(k) for k in ("auc", "ci95", "events", "other_events")},
            "duty_spearman": round(float(duty_rho), 4), "duty_p": round(float(duty_p), 5)}


def main():
    run = Run("0110 contexts outside the archives", ["extract", "score"])
    sealed = SealedSet(run)
    with run.stage("score") as stage:
        count_head = joblib.load(COUNT_HEAD) if COUNT_HEAD.exists() else None
        report = {
            "coded_recordings": len(sealed.labels),
            "extracted_ok": len(sealed.records),
            "primary_clean_windows": context_family(
                sealed, ArchiveHeads("emb_clean", "has_clean"), "mean_clean", count_head),
            "secondary_all_crow_windows": context_family(
                sealed, ArchiveHeads("emb_crow", "has_crow"), "mean_crow", count_head),
            "count_head_transfer": count_transfer(sealed, count_head) if count_head is not None else None,
        }
        stage.update(1, 1)
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    run.note("scored once")


if __name__ == "__main__":
    main()
