"""0112 step 4: score every representation on the declared tests, once.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0112-does-crowgpt-hear-what-birdnet-misses/evaluate.py
"""

from __future__ import annotations

import json
import sys
import warnings
from collections import defaultdict
from importlib import util
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sets  # noqa: E402
from scoring import GroupedOvR, head  # noqa: E402

sys.path.insert(0, str(sets.REPO / "crowgpt" / "src"))
sys.path.insert(0, str(sets.REPO / "pipelines" / "training"))
from crowgpt.progress import Run  # noqa: E402

PRIMARY_LAYER = 3
N_LAYERS = 6
COUNT_HEAD = sets.DATA_DIR / "experiments" / "0109-crow-count" / "count_head.joblib"


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp110 = load_module("exp110_eval", sets.EXP110 / "run.py")
exp103 = load_module("exp103_eval", sets.EXP103 / "eval_dev.py")
exp104 = load_module("exp104_eval", sets.EXP104 / "eval.py")
exp109 = load_module("exp109_eval", sets.REPO / "experiments" / "0109-can-the-number-of-crows-be-heard" / "run.py")


class Representations:
    """Span id -> vector, for CrowGPT (any block) and Perch. BirdNET window vectors come from the scan."""

    def __init__(self):
        crowgpt = np.load(sets.CACHE / "crowgpt.npz")
        self.crowgpt = dict(zip(crowgpt["ids"].tolist(), crowgpt["layers"]))
        perch = np.load(sets.CACHE / "perch.npz")
        self.perch = dict(zip(perch["ids"].tolist(), perch["embeddings"]))

    def names(self) -> list[str]:
        return ["birdnet", "perch", *[f"crowgpt_b{i + 1}" for i in range(N_LAYERS)]]

    def span(self, name: str, span_id: str) -> np.ndarray | None:
        if name == "perch":
            row = self.perch.get(span_id)
        else:
            row = self.crowgpt.get(span_id)
            row = None if row is None else row[int(name.split("_b")[1]) - 1]
        return None if row is None else row.astype(np.float32)

    def window_mean(self, name: str, table: sets.WindowTable, mask: np.ndarray) -> np.ndarray | None:
        if name == "birdnet":
            return table.embedding[mask].mean(0) if mask.any() else None
        rows = [self.span(name, f"{table.key}@{float(s):.2f}") for s in table.start[mask]]
        rows = [r for r in rows if r is not None]
        return np.mean(rows, axis=0) if rows else None


class SingleCaw:
    """PRIMARY and secondary 1: 0103's dev caws, its evaluator, a new representation."""

    def __init__(self, reps: Representations):
        self.reps = reps
        recs = json.loads((sets.CAW_CACHE / "recordings.json").read_text())
        caws = json.loads((sets.CAW_CACHE / "caws.json").read_text())
        self.birdnet = np.load(sets.CAW_CACHE / "features.npz")["caw_birdnet_1024d"]
        rec_by_id = {r["id"]: r for r in recs}
        dev = [i for i, c in enumerate(caws) if c["split"] == "dev"]
        present = [i for i in dev if all(reps.span(n, f"caw{i}") is not None for n in ("perch", "crowgpt_b4"))]
        self.index = np.array(present)
        self.dropped = len(dev) - len(present)
        self.y = np.array([1 if caws[i]["context"] == "owl_mobbing" else 0 for i in present])
        self.rid = np.array([caws[i]["rec_id"] for i in present])
        self.groups = np.array([exp103.group_key(rec_by_id[caws[i]["rec_id"]]) for i in present])
        caw_recs = [rec_by_id[r] for r in sorted(set(self.rid.tolist()))]
        self.dm = np.isin(self.rid, list(set(exp103.match_density_1to1(caw_recs))))

    def X(self, name: str) -> np.ndarray:
        if name == "birdnet":
            return self.birdnet[self.index]
        return np.stack([self.reps.span(name, f"caw{i}") for i in self.index])

    def run(self, stage) -> dict:
        out = {"dev_caws_scored": int(len(self.y)), "dev_caws_dropped_no_audio": self.dropped}
        out["PRIMARY_crowgpt_b4"] = exp103.eval_caw_cv(self.X("crowgpt_b4"), self.y, self.rid, self.groups,
                                                       C=0.1, n_perm=400, seed=42)
        stage.update(1, 6)
        out["birdnet_isolated_C0.05_as_0103"] = exp103.eval_caw_cv(self.X("birdnet"), self.y, self.rid, self.groups,
                                                                   C=0.05, n_perm=0)
        out["perch_isolated"] = exp103.eval_caw_cv(self.X("perch"), self.y, self.rid, self.groups,
                                                   C=0.1, n_perm=200, seed=44)
        stage.update(2, 6)
        out["exploratory_crowgpt_blocks"] = {
            f"b{i + 1}": exp103.eval_caw_cv(self.X(f"crowgpt_b{i + 1}"), self.y, self.rid, self.groups,
                                            C=0.1, n_perm=0)["primary_weighted_per_caw_auc"]
            for i in range(N_LAYERS)}
        stage.update(3, 6)
        dm = self.dm
        out["S1_density_matched"] = {
            name: exp103.eval_caw_cv(self.X(name)[dm], self.y[dm], self.rid[dm], self.groups[dm],
                                     C=0.05 if name == "birdnet" else 0.1, n_perm=200, seed=43)
            for name in ("crowgpt_b4", "birdnet", "perch")}
        stage.update(6, 6)
        return out


class ArchiveContexts:
    """Secondary 2: the 423 archive recordings, clean-window means, five contexts."""

    def __init__(self, reps: Representations):
        self.reps = reps
        recordings = [r for r in sets.ArchiveSet().recordings if sets.WindowTable.exists(r.key)]
        self.features = {n: [] for n in reps.names()}
        self.recordings = []
        for r in recordings:
            table = sets.WindowTable(r.key)
            mask = table.clean()
            vectors = {n: reps.window_mean(n, table, mask) for n in reps.names()}
            if any(v is None for v in vectors.values()):
                continue
            self.recordings.append(r)
            for n, v in vectors.items():
                self.features[n].append(v)
        self.features = {n: np.array(v) for n, v in self.features.items()}
        self.labels = np.array([r.label for r in self.recordings])
        self.groups = np.array([r.group for r in self.recordings])
        self.ovr = GroupedOvR(self.labels, self.groups)

    def run(self, stage) -> dict:
        out = {"recordings": len(self.recordings), "recordists": len(set(self.groups)),
               "per_context": {c: int((self.labels == c).sum()) for c in sets.CONTEXTS}}
        scores = {}
        for k, n in enumerate(self.reps.names()):
            scores[n] = self.ovr.scores(self.features[n])
            out[n] = self.ovr.report(scores[n])
            stage.update(k + 1, len(self.reps.names()))
        out["crowgpt_b4_minus_birdnet"] = self.ovr.paired(scores["crowgpt_b4"], scores["birdnet"])
        out["perch_minus_birdnet"] = self.ovr.paired(scores["perch"], scores["birdnet"])
        out["exploratory_owl_vs_hawk_strict"] = self.owl_hawk()
        return out

    def owl_hawk(self) -> dict:
        keep = np.array([r.extra["fine_context"] in ("owl_mobbing", "hawk_mobbing") and not r.extra["pred_vocal"]
                         and r.extra["max_raptor_conf"] < 0.05 for r in self.recordings])
        y = np.array([r.extra["fine_context"] == "owl_mobbing" for r in self.recordings])[keep].astype(int)
        groups = self.groups[keep]
        out = {"n": int(keep.sum()), "owl": int(y.sum())}
        for n in ("birdnet", "perch", "crowgpt_b4"):
            X = self.features[n][keep]
            scores = np.zeros(len(y))
            for train, test in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X, y, groups):
                scores[test] = head().fit(X[train], y[train]).decision_function(X[test])
            out[n] = round(float(roc_auc_score(y, scores)), 4)
        return out

    def frozen_heads(self, name: str) -> dict:
        return {c: head().fit(self.features[name], (self.labels == c).astype(int)) for c in sets.CONTEXTS}


class CrowdInsideType:
    """Secondary 3: 0109's one-against-several task with the window representation swapped."""

    def __init__(self, reps: Representations):
        self.reps = reps
        catalogue = sets.SpanCatalogue()
        saved = np.load(sets.DATA_DIR / "experiments" / "0109-crow-count" / "segments.npz")
        present = saved["present"]
        from corpus import LabelCorpus

        segments = [s for s in LabelCorpus().labeled_segments() if s.flags.get("crowCount") in (1, 2, 4)]
        assert len(segments) == len(present) == len(catalogue.segment_span)
        birdnet = iter(saved["X"])
        duty = iter(saved["duty"])
        rows = []
        for seg, span_id, p in zip(segments, catalogue.segment_span, present):
            if not p:
                continue
            b, d = next(birdnet), next(duty)
            others = {n: reps.span(n, span_id) for n in ("perch", "crowgpt_b4")}
            if all(v is not None for v in others.values()):
                rows.append((seg, b, d, others))
        self.dropped = int(present.sum()) - len(rows)
        data = object.__new__(exp109.CountedSegments)
        data.segments = [r[0] for r in rows]
        data.X = np.array([r[1] for r in rows], dtype=np.float32)
        data.duty = np.array([r[2] for r in rows], dtype=float)
        data.count = np.array([s.flags["crowCount"] for s in data.segments])
        data.several = (data.count > 1).astype(int)
        data.groups = data._groups()
        data.flags = {f: np.array([bool(s.flags.get(f)) for s in data.segments]) for f in exp109.CALL_TYPES}
        self.data = data
        self.features = {"birdnet": data.X, **{n: np.stack([r[3][n] for r in rows]) for n in ("perch", "crowgpt_b4")}}

    def run(self) -> dict:
        experiment = exp109.CountExperiment(self.data)
        out = {"segments": len(self.data.several), "dropped_no_span": self.dropped}
        for n, X in self.features.items():
            within = experiment.within_type(experiment.out_of_fold(X, self.data.several))
            out[n] = {"mean": within["mean"], **{k: v["auc"] for k, v in within.items() if k != "mean"}}
        return out


class Posture:
    """Secondary 4: 0104's strict perched owl vs hawk and perched vs flying within hawk."""

    def __init__(self, reps: Representations):
        self.reps = reps
        self.clipset = exp104.ClipSet()

    def features(self, name: str) -> dict[str, np.ndarray]:
        out = {}
        for c in self.clipset.clips:
            key = f"v{c.key}"
            if sets.WindowTable.exists(key):
                table = sets.WindowTable(key)
                v = self.reps.window_mean(name, table, table.pure())
                if v is not None:
                    out[c.key] = v
        return out

    def run(self) -> dict:
        cs = self.clipset
        cells = {
            "perched_owl_vs_perched_hawk_strict": (
                cs.cap_per_channel(cs.cell("owl", "perched", strict=True)),
                cs.cap_per_channel(cs.cell("hawk", "perched", strict=True))),
            "within_hawk_perched_vs_flying_nonstrict": (
                cs.cap_per_channel(cs.cell("hawk", "perched", strict=False)),
                cs.cap_per_channel(cs.cell("hawk", "flying", strict=False))),
        }
        test = exp104.GroupedTest(C=0.05)
        out = {}
        for name in ("birdnet", "perch", "crowgpt_b4"):
            vectors = self.features(name)
            out[name] = {}
            for cell, (pos, neg) in cells.items():
                pos = [c for c in pos if c.key in vectors]
                neg = [c for c in neg if c.key in vectors]
                X = np.stack([vectors[c.key] for c in pos + neg])
                y = np.array([1] * len(pos) + [0] * len(neg))
                groups = np.array([c.channel for c in pos + neg])
                out[name][cell] = test.run(X, y, groups, permute=True)
        return out


class Outside:
    """Secondary 5: archive heads per representation, frozen, scored on 0110's coded recordings."""

    def __init__(self, reps: Representations, archive: ArchiveContexts):
        self.reps, self.archive = reps, archive
        self.count_head = joblib.load(COUNT_HEAD)

    def run(self) -> dict:
        recordings = [r for r in sets.OutsideSet().recordings
                      if r.label in sets.CONTEXTS and sets.WindowTable.exists(r.key)]
        out = {}
        for name in ("birdnet", "perch", "crowgpt_b4"):
            heads = self.archive.frozen_heads(name)
            records, X, crowd = [], [], []
            for r in recordings:
                table = sets.WindowTable(r.key)
                v = self.reps.window_mean(name, table, table.clean())
                crow = self.reps.window_mean("birdnet", table, table.corvid >= 0.25)
                if v is None or crow is None:
                    continue
                records.append({"event": r.extra["event"], "observer": r.group, "context": r.label})
                X.append(v)
                crowd.append(crow)
            X = np.array(X)
            values = {c: heads[c].decision_function(X) for c in sets.CONTEXTS}
            values["count"] = self.count_head.decision_function(np.array(crowd))
            events = exp110.Events(records, values, "context")
            primary, removed = {}, {}
            for c in sets.CONTEXTS:
                y = (events.labels == c).astype(int)
                primary[c] = events.auc(y, events.values[c])
                after = events.auc(y, events.residual(events.values[c], events.values["count"]))
                removed[c] = {k: after.get(k) for k in ("auc", "ci95")}
            exp110.holm(primary)
            out[name] = {"recordings": len(records), "events": len(events.names), "contexts": primary,
                         "count_removed": removed}
        return out


def holm_family(report: dict) -> dict:
    """Holm over the p values secondaries 4 and 5 quote, per representation."""
    out = {}
    for name in ("birdnet", "perch", "crowgpt_b4"):
        ps = {f"S4:{cell}": r.get("perm_p") for cell, r in report["S4_posture"][name].items()}
        ps.update({f"S5:{c}": r.get("p") for c, r in report["S5_outside"][name]["contexts"].items()})
        ps = {k: v for k, v in ps.items() if v is not None}
        ordered = sorted(ps, key=ps.get)
        running, adjusted = 0.0, {}
        for rank, k in enumerate(ordered):
            running = max(running, min(1.0, (len(ordered) - rank) * ps[k]))
            adjusted[k] = round(running, 5)
        out[name] = adjusted
    return out


def main():
    run = Run("0112 representation evaluation", ["single_caw", "archive", "crowd", "posture", "outside"])
    reps = Representations()
    report = {"primary_layer": "temporal block 4 of 6"}
    with run.stage("single_caw") as stage:
        report["single_caw"] = SingleCaw(reps).run(stage)
    with run.stage("archive") as stage:
        archive = ArchiveContexts(reps)
        report["S2_archive_contexts"] = archive.run(stage)
    with run.stage("crowd") as stage:
        report["S3_crowd_inside_type"] = CrowdInsideType(reps).run()
        stage.update(1, 1)
    with run.stage("posture") as stage:
        report["S4_posture"] = Posture(reps).run()
        stage.update(1, 1)
    with run.stage("outside") as stage:
        report["S5_outside"] = Outside(reps, archive).run()
        report["S4_S5_holm"] = holm_family(report)
        stage.update(1, 1)
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    p = report["single_caw"]["PRIMARY_crowgpt_b4"]
    run.note(f"primary w-AUC {p['primary_weighted_per_caw_auc']} p={p['perm_p']}")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
