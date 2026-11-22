"""0113 — one crow's graded calling, by context, with the crowd removed by construction.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0113-does-one-crow-call-differently-by-context/run.py
"""

from __future__ import annotations

import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import joblib
import librosa
import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"
sys.path.insert(0, str(EXP112))
import sets  # noqa: E402
from scoring import CONTEXTS, GroupedOvR, head  # noqa: E402

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402

COUNT_DIR = sets.DATA_DIR / "experiments" / "0109-crow-count"
CACHE = sets.DATA_DIR / "experiments" / "0113-single-bird"
SR = 22050
MAX_AUDIO_S = 300.0
PRECISION = 0.90
MIN_CAWS = 3
TIMING = ("caw_rate", "gap_median", "gap_cv")


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp103 = load_module("exp103_caws", sets.EXP103 / "extract_caws.py")
exp109 = load_module("exp109_0113", REPO / "experiments" / "0109-can-the-number-of-crows-be-heard" / "run.py")


class OneCrowCut:
    """The threshold on P(several), fixed from 0109's own out-of-fold scores before any archive window."""

    def __init__(self):
        from corpus import LabelCorpus

        saved = np.load(COUNT_DIR / "segments.npz")
        segments = [s for s in LabelCorpus().labeled_segments() if s.flags.get("crowCount") in (1, 2, 4)]
        data = object.__new__(exp109.CountedSegments)
        data.segments = [s for s, p in zip(segments, saved["present"]) if p]
        data.X = saved["X"]
        data.count = np.array([s.flags["crowCount"] for s in data.segments])
        data.several = (data.count > 1).astype(int)
        data.groups = data._groups()
        data.flags = {f: np.array([bool(s.flags.get(f)) for s in data.segments]) for f in exp109.CALL_TYPES}
        scores = exp109.CountExperiment(data).out_of_fold(data.X, data.several)
        order = np.argsort(scores)
        one = 1 - data.several[order]
        precision = np.cumsum(one) / np.arange(1, len(one) + 1)
        passing = np.flatnonzero(precision >= PRECISION)
        last = passing.max()
        self.threshold = float(scores[order][last + 1]) if last + 1 < len(order) else 1.0
        below = scores < self.threshold
        self.report = {"threshold_p_several": round(self.threshold, 4),
                       "segments_below": int(below.sum()), "segments": int(len(scores)),
                       "one_crow_precision_below": round(float((1 - data.several[below]).mean()), 4),
                       "one_crow_recall": round(float(below[data.several == 0].mean()), 4)}


def describe(task):
    """One recording: caws in its single-bird windows and in all its pure windows, graded."""
    key, path, single, pure = task
    try:
        y, sr = librosa.load(path, sr=SR, mono=True, duration=MAX_AUDIO_S)
    except Exception as error:  # noqa: BLE001
        return key, None, str(error)[:200]
    out = {}
    for name, starts in (("single", single), ("pure", pure)):
        windows = [(s, s + sets.WINDOW_S) for s in starts if s + sets.WINDOW_S <= len(y) / sr]
        caws, rates, gaps, cvs = [], [], [], []
        for window in windows:
            found = exp103.segment_caws_in_windows(y, sr, [window], max_caws=10_000)
            rates.append(len(found) / sets.WINDOW_S)
            onsets = np.array([c["onset"] for c in found])
            if len(onsets) >= 2:
                intervals = np.diff(onsets)
                gaps.append(float(np.median(intervals)))
                cvs.append(float(np.std(intervals) / max(np.mean(intervals), 1e-6)))
            for c in found:
                caws.append(exp103.extract_caw_44d(y[int(round(c["onset"] * sr)):int(round(c["offset"] * sr))], sr))
        if len(caws) < MIN_CAWS:
            out[name] = None
            continue
        timing = [np.mean(rates), np.mean(gaps) if gaps else 0.0, np.mean(cvs) if cvs else 0.0]
        out[name] = {"vector": np.concatenate([np.mean(caws, axis=0), timing]).astype(np.float32).tolist(),
                     "caws": len(caws), "windows": len(windows)}
    return key, out, None


class Recordings:
    """Archive recordings with their single-bird and pure windows, graded features and BirdNET means."""

    def __init__(self, cut: OneCrowCut, run: Run):
        self.count_head = joblib.load(COUNT_DIR / "count_head.joblib")
        self.cut = cut
        self.rows = []
        for r in sets.ArchiveSet().recordings:
            if not sets.WindowTable.exists(r.key):
                continue
            table = sets.WindowTable(r.key)
            pure = table.pure()
            if not pure.any():
                continue
            several = self.count_head.predict_proba(table.embedding[pure])[:, 1]
            single = np.zeros(len(pure), bool)
            single[np.flatnonzero(pure)] = several < cut.threshold
            self.rows.append({"recording": r, "single": table.start[single].tolist(), "pure": table.start[pure].tolist(),
                              "birdnet_single": table.embedding[single].mean(0) if single.any() else None,
                              "birdnet_pure": table.embedding[pure].mean(0),
                              "count_single": float(several[several < cut.threshold].mean())
                              if (several < cut.threshold).any() else None,
                              "count_pure": float(several.mean())})
        self.graded = self._graded(run)

    def _graded(self, run: Run) -> dict:
        cache = CACHE / "graded.json"
        if cache.exists():
            return json.loads(cache.read_text())
        tasks = [(row["recording"].key, str(row["recording"].path), row["single"], row["pure"]) for row in self.rows]
        graded = {}
        with run.stage("describe") as stage, ProcessPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(describe, t) for t in tasks]
            for done, future in enumerate(as_completed(futures), 1):
                key, out, _ = future.result()
                graded[key] = out
                if done % 10 == 0 or done == len(tasks):
                    stage.update(done, len(tasks))
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(graded))
        return graded

    def table(self, which: str, require_single: bool = True):
        rows = [row for row in self.rows if (self.graded.get(row["recording"].key) or {}).get(which)
                and (not require_single or (self.graded[row["recording"].key] or {}).get("single"))]
        X = np.array([self.graded[row["recording"].key][which]["vector"] for row in rows])
        labels = np.array([row["recording"].label for row in rows])
        groups = np.array([row["recording"].group for row in rows])
        return rows, X, labels, groups


class Residualised(GroupedOvR):
    """GroupedOvR with a covariate regressed out of every feature, inside each training fold."""

    def __init__(self, labels, groups, covariate, C):
        super().__init__(labels, groups, C=C)
        self.covariate = covariate

    def scores(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros((len(X), len(self.classes)))
        z = np.column_stack([np.ones(len(X)), self.covariate])
        for train, test in self.folds:
            beta, *_ = np.linalg.lstsq(z[train], X[train], rcond=None)
            Xr = X - z @ beta
            for k, c in enumerate(self.classes):
                out[test, k] = head(self.C).fit(Xr[train], (self.labels[train] == c).astype(int)).decision_function(Xr[test])
        return out


class SingleBirdExperiment:
    def __init__(self, recordings: Recordings):
        self.recs = recordings

    def primary(self, stage) -> dict:
        rows, X, labels, groups = self.recs.table("single")
        ovr = GroupedOvR(labels, groups, C=0.1)
        report = ovr.report(ovr.scores(X))
        report.update(ovr.permutation(X, report["macro_auc"], n=400, seed=0, on_step=stage.update))
        report.update({"recordings": len(rows), "recordists": len(set(groups)),
                       "per_context_n": {c: int((labels == c).sum()) for c in CONTEXTS},
                       "single_caws_median": float(np.median([self.recs.graded[r["recording"].key]["single"]["caws"]
                                                              for r in rows]))})
        return report

    def survives(self) -> dict:
        rows, X, labels, groups = self.recs.table("pure")
        ovr = GroupedOvR(labels, groups, C=0.1)
        return {"recordings": len(rows), **ovr.report(ovr.scores(X))}

    def owl_hawk(self) -> dict:
        rows, X, _, groups = self.recs.table("single")
        fine = np.array([r["recording"].extra["fine_context"] for r in rows])
        keep = np.isin(fine, ["owl_mobbing", "hawk_mobbing"])
        y, X, groups = (fine[keep] == "owl_mobbing").astype(int), X[keep], groups[keep]
        scores = np.zeros(len(y))
        for train, test in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X, y, groups):
            scores[test] = head(0.1).fit(X[train], y[train]).decision_function(X[test])
        return {"owl": int(y.sum()), "hawk": int((1 - y).sum()), "auc": round(float(roc_auc_score(y, scores)), 4)}

    def birdnet(self) -> dict:
        rows = [r for r in self.recs.rows if r["birdnet_single"] is not None]
        labels = np.array([r["recording"].label for r in rows])
        groups = np.array([r["recording"].group for r in rows])
        ovr = GroupedOvR(labels, groups, C=0.05)
        out = {"recordings": len(rows)}
        for which in ("single", "pure"):
            out[which] = ovr.report(ovr.scores(np.array([r[f"birdnet_{which}"] for r in rows])))
        return out

    def residual(self) -> dict:
        rows, X, labels, groups = self.recs.table("single")
        count = np.array([r["count_single"] for r in rows])
        out = {"graded_single": Residualised(labels, groups, count, 0.1).report(
            Residualised(labels, groups, count, 0.1).scores(X))}
        brows = [r for r in self.recs.rows if r["birdnet_single"] is not None]
        bl = np.array([r["recording"].label for r in brows])
        bg = np.array([r["recording"].group for r in brows])
        bc = np.array([r["count_single"] for r in brows])
        model = Residualised(bl, bg, bc, 0.05)
        out["birdnet_single"] = model.report(model.scores(np.array([r["birdnet_single"] for r in brows])))
        return out

    def movement(self) -> dict:
        rows, X, labels, groups = self.recs.table("single")
        columns = {"caw_duration": 0, "median_pitch": 3, "caw_rate": 44, "gap_median": 45}
        out = {}
        for context in CONTEXTS:
            inside = labels == context
            out[context] = {}
            for name, col in columns.items():
                values = X[:, col]
                pooled = np.std(values) or 1.0
                point = (values[inside].mean() - values[~inside].mean()) / pooled
                boot = []
                for r in GroupedOvR(labels, groups).resamples(1000):
                    a, b = values[r][labels[r] == context], values[r][labels[r] != context]
                    if len(a) and len(b):
                        boot.append((a.mean() - b.mean()) / pooled)
                out[context][name] = {"smd": round(float(point), 3),
                                      "ci95": [round(float(np.percentile(boot, 2.5)), 3),
                                               round(float(np.percentile(boot, 97.5)), 3)]}
        return out


def main():
    run = Run("0113 single-bird graded calling", ["cut", "describe", "primary", "secondary"])
    with run.stage("cut") as stage:
        cut = OneCrowCut()
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "cut.json").write_text(json.dumps(cut.report, indent=2))
        stage.update(1, 1, extra=f"T={cut.threshold:.3f}")
    recordings = Recordings(cut, run)
    experiment = SingleBirdExperiment(recordings)
    report = {"one_crow_cut": cut.report,
              "windows": {"pure": int(sum(len(r["pure"]) for r in recordings.rows)),
                          "single": int(sum(len(r["single"]) for r in recordings.rows))}}
    with run.stage("primary") as stage:
        report["PRIMARY_graded_single_bird"] = experiment.primary(stage)
    with run.stage("secondary") as stage:
        report["S1_graded_all_pure_windows"] = experiment.survives()
        stage.update(1, 5)
        report["S2_owl_vs_hawk_single_bird"] = experiment.owl_hawk()
        stage.update(2, 5)
        report["S3_birdnet_single_vs_pure"] = experiment.birdnet()
        stage.update(3, 5)
        report["S4_count_removed"] = experiment.residual()
        stage.update(4, 5)
        report["S5_feature_movement"] = experiment.movement()
        stage.update(5, 5)
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    p = report["PRIMARY_graded_single_bird"]
    run.note(f"primary macro AUC {p['macro_auc']} p={p['perm_p']}")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
