"""0109 — one crow against several, scored inside each call type.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0109-can-the-number-of-crows-be-heard/run.py
"""

from __future__ import annotations

import contextlib
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0109-crow-count"
CROWTOOLS_LABELS = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"
INTENSITY_SOURCE = REPO / "experiments" / "0105-does-calling-change-when-the-recordist-says-so" / "run.py"
LIBRARY_SOURCE = {"library-1": "macaulay", "library-2": "xeno_canto"}

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402

CALL_TYPES = ("mob", "alert", "scold", "rattle", "softSong", "begging", "grief")
WINDOW_S = 3
MIN_SIDE = 30

_ANALYZER = None
_INTENSITY = None


def _init_worker():
    global _ANALYZER, _INTENSITY
    from birdnetlib.analyzer import Analyzer

    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()
    spec = util.spec_from_file_location("exp105", INTENSITY_SOURCE)
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _INTENSITY = module.CallingIntensity


def _measure_file(task):
    file_id, path, seconds = task
    from birdnetlib import Recording

    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            recording = Recording(_ANALYZER, path, min_conf=0.1)
            recording.extract_embeddings()
        intensity = _INTENSITY(Path(path))
    except Exception as error:  # noqa: BLE001
        return file_id, None, str(error)
    by_start = {int(round(w["start_time"])): np.asarray(w["embeddings"], dtype=np.float32)
                for w in recording.embeddings}
    rows = []
    for second in seconds:
        start = WINDOW_S * (second // WINDOW_S)
        window = by_start.get(start)
        if window is None or not np.isfinite(window).all():
            rows.append(None)
            continue
        rows.append((window, intensity.duty_cycle(start, start + WINDOW_S)))
    return file_id, rows, None


def head():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced"))


class CountedSegments:
    """Hand-labelled segments with a crow count, each with its window embedding and duty cycle."""

    def __init__(self, run: Run):
        from corpus import LabelCorpus

        self.segments = [s for s in LabelCorpus().labeled_segments()
                         if s.flags.get("crowCount") in (1, 2, 4)]
        embeddings, duties = self._measure(run)
        keep = np.array([e is not None for e in embeddings])
        self.segments = [s for s, k in zip(self.segments, keep) if k]
        self.X = np.array([e for e in embeddings if e is not None], dtype=np.float32)
        self.duty = np.array([d for d, k in zip(duties, keep) if k], dtype=float)
        self.count = np.array([s.flags["crowCount"] for s in self.segments])
        self.several = (self.count > 1).astype(int)
        self.groups = self._groups()
        self.flags = {f: np.array([bool(s.flags.get(f)) for s in self.segments]) for f in CALL_TYPES}

    def _measure(self, run: Run):
        cache = CACHE / "segments.npz"
        if cache.exists():
            saved = np.load(cache)
            with run.stage("embed") as stage:
                stage.update(1, 1, extra="cached")
            present = saved["present"]
            embeddings = iter(saved["X"])
            duties = iter(saved["duty"])
            return ([next(embeddings) if p else None for p in present],
                    [next(duties) if p else None for p in present])
        by_file = defaultdict(list)
        for index, s in enumerate(self.segments):
            by_file[(s.file_id, str(s.audio_path))].append((index, int(s.start)))
        tasks = [(file_id, path, [second for _, second in rows]) for (file_id, path), rows in by_file.items()]
        index_of = {file_id: [i for i, _ in rows] for (file_id, _), rows in by_file.items()}
        embeddings = [None] * len(self.segments)
        duties = [None] * len(self.segments)
        with run.stage("embed") as stage, ProcessPoolExecutor(max_workers=12, initializer=_init_worker) as pool:
            futures = [pool.submit(_measure_file, t) for t in tasks]
            for done, future in enumerate(as_completed(futures), 1):
                file_id, rows, _ = future.result()
                for index, row in zip(index_of[file_id], rows or []):
                    if row is not None:
                        embeddings[index], duties[index] = row
                if done % 20 == 0 or done == len(tasks):
                    stage.update(done, len(tasks))
        present = np.array([e is not None for e in embeddings])
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez(cache, present=present,
                 X=np.array([e for e in embeddings if e is not None], dtype=np.float32),
                 duty=np.array([d for d in duties if d is not None], dtype=float))
        return embeddings, duties

    def _groups(self) -> np.ndarray:
        libraries = json.loads(CROWTOOLS_LABELS.read_text())["libraries"]
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        recordist = {}
        for file_id in {s.file_id for s in self.segments}:
            row = db.execute("SELECT recordist FROM recordings WHERE source = ? AND source_ref = ?",
                             (LIBRARY_SOURCE.get(libraries.get(file_id)), file_id)).fetchone()
            recordist[file_id] = (row[0] or "").strip().lower() if row else ""
        return np.array([recordist[s.file_id] or f"file:{s.file_id}" for s in self.segments])


class GroupedScore:
    """An AUC with an interval from resampling whole groups."""

    def __init__(self, y, scores, groups, resamples: int = 2000):
        self.y, self.scores, self.groups, self.resamples = y, scores, groups, resamples

    def auc(self, mask=None) -> float | None:
        y, s = (self.y, self.scores) if mask is None else (self.y[mask], self.scores[mask])
        if min(y.sum(), len(y) - y.sum()) < 2:
            return None
        return float(roc_auc_score(y, s))

    def report(self, statistic) -> dict:
        members = defaultdict(list)
        for index, group in enumerate(self.groups):
            members[group].append(index)
        names = list(members)
        rng = np.random.default_rng(0)
        boot = []
        for _ in range(self.resamples):
            picked = np.concatenate([members[names[i]] for i in rng.integers(0, len(names), len(names))])
            value = statistic(GroupedScore(self.y[picked], self.scores[picked], self.groups[picked]), picked)
            if value is not None:
                boot.append(value)
        point = statistic(self, np.arange(len(self.y)))
        return {"auc": round(point, 4),
                "ci95": [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]}


class CountExperiment:
    def __init__(self, data: CountedSegments):
        self.data = data
        self.strata = [f for f in CALL_TYPES
                       if min(data.several[data.flags[f]].sum(),
                              (1 - data.several[data.flags[f]]).sum()) >= MIN_SIDE]

    def out_of_fold(self, X, y, train_mask=None) -> np.ndarray:
        scores = np.full(len(y), np.nan)
        folds = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
        for train, test in folds.split(X, y, self.data.groups):
            if train_mask is not None:
                train = train[train_mask[train]]
            scores[test] = head().fit(X[train], y[train]).predict_proba(X[test])[:, 1]
        return scores

    def within_type(self, scores: np.ndarray, y=None, keep=None) -> dict:
        d = self.data
        y = d.several if y is None else y
        keep = np.ones(len(y), bool) if keep is None else keep
        out = {}
        for flag in self.strata:
            mask = d.flags[flag] & keep
            scored = GroupedScore(y[mask], scores[mask], d.groups[mask])
            out[flag] = {"one": int((1 - y[mask]).sum()), "several": int(y[mask].sum()),
                         **scored.report(lambda g, _: g.auc())}
        flags = {f: d.flags[f] & keep for f in self.strata}

        def mean_auc(g, picked):
            values = [g.auc(flags[f][picked]) for f in self.strata]
            return None if any(v is None for v in values) else float(np.mean(values))

        out["mean"] = GroupedScore(y[keep], scores[keep], d.groups[keep]).report(
            lambda g, picked: mean_auc(g, np.flatnonzero(keep)[picked]))
        return out

    def run(self) -> dict:
        d = self.data
        embedding = self.out_of_fold(d.X, d.several)
        report = {
            "segments": len(d.several), "one": int((1 - d.several).sum()), "several": int(d.several.sum()),
            "groups": len(set(d.groups)), "strata": self.strata,
            "primary_embedding_within_type": self.within_type(embedding),
            "secondary_duty_within_type": self.within_type(d.duty),
            "secondary_embedding_ignoring_type": GroupedScore(d.several, embedding, d.groups).report(
                lambda g, _: g.auc()),
        }
        mob_many = d.flags["mob"] & (d.count > 1)
        four = (d.count[mob_many] == 4).astype(int)
        ordered = np.full(len(d.count), np.nan)
        folds = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
        X, groups = d.X[mob_many], d.groups[mob_many]
        local = np.zeros(len(four))
        for train, test in folds.split(X, four, groups):
            local[test] = head().fit(X[train], four[train]).predict_proba(X[test])[:, 1]
        ordered[mob_many] = local
        report["secondary_two_against_four_within_mob"] = {
            "two": int((1 - four).sum()), "four": int(four.sum()),
            **GroupedScore(four, local, groups).report(lambda g, _: g.auc())}
        transfer = head().fit(d.X[~d.flags["mob"]], d.several[~d.flags["mob"]])
        mob = d.flags["mob"]
        report["secondary_trained_off_mob_tested_on_mob"] = GroupedScore(
            d.several[mob], transfer.predict_proba(d.X[mob])[:, 1], d.groups[mob]).report(lambda g, _: g.auc())
        return report


def main():
    run = Run("0109 crow count head", ["embed", "score"])
    data = CountedSegments(run)
    with run.stage("score") as stage:
        report = CountExperiment(data).run()
        CACHE.mkdir(parents=True, exist_ok=True)
        joblib.dump(head().fit(data.X, data.several), CACHE / "count_head.joblib")
        stage.update(1, 1)
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    run.note(f"within-type AUC {report['primary_embedding_within_type']['mean']['auc']}")


if __name__ == "__main__":
    main()
