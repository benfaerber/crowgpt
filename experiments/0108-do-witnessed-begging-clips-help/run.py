"""0108 — score the shipped head's protocol with and without the witnessed begging clips.

Reads the caches `extract.py` wrote. The protocol is the README's, fixed before
this file existed; nothing here chooses between arms after seeing a number.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0108-do-witnessed-begging-clips-help/run.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from joblib import Parallel, delayed
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0108-begging"
CORPUS_DB = DATA_DIR / "corvid.db"
CROWTOOLS_LABELS = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import pooling  # noqa: E402
import train_head  # noqa: E402
from crowgpt.progress import Run  # noqa: E402
from heads import MultiLabelHead  # noqa: E402

LIBRARY_SOURCE = {"library-1": "macaulay", "library-2": "xeno_canto"}
TARGET = "begging"
CLASSES = train_head.SHIPPED_CORE
GUARD_CLASSES = [c for c in CLASSES if c != TARGET]
CROW_GATE = 0.25
HEAD_GATE = 0.5
CAP_PER_RECORDING = 8
SEEDS = list(range(10))
RULES = ("all_crow_windows", "head_says_begging")
PRIMARY_RULE = "all_crow_windows"
MIN_GAIN = 0.005
MIN_POSITIVE_SEEDS = 8
GUARD_MEAN_DROP = 0.005
GUARD_CLASS_DROP = 0.010
JOBS = 20


def classifier():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(max_iter=5000, class_weight="balanced"))


def norm(name):
    return (name or "").strip().lower()


class EvalSet:
    """The 2,654 rows the shipped head was trained on, with a recordist where one is known."""

    def __init__(self):
        feats = train_head.load("birdnet", "pooled")
        self.X = np.asarray(feats.X, dtype=np.float32)
        self.Y = [set(y) for y in feats.Y]
        self.groups = np.asarray(feats.groups)
        self.recordists = self._recordists()

    def _recordists(self):
        libraries = json.loads(CROWTOOLS_LABELS.read_text())["libraries"]
        con = sqlite3.connect(f"file:{CORPUS_DB}?mode=ro", uri=True)
        known = {}
        for group in set(self.groups.tolist()):
            prefix, _, ref = group.partition(":")
            if prefix != "ct":
                continue
            row = con.execute(
                "SELECT recordist FROM recordings WHERE source = ? AND source_ref = ?",
                (LIBRARY_SOURCE.get(libraries.get(ref)), ref)).fetchone()
            if row and row[0]:
                known[group] = norm(row[0])
        con.close()
        return known

    def binary(self, cls):
        return np.array([1 if cls in y else 0 for y in self.Y])

    def test_recordists(self, test):
        return {self.recordists[g] for g in set(self.groups[test].tolist())
                if g in self.recordists}


class Additions:
    """Weakly labelled begging windows from clips crow-tools has not reviewed."""

    def __init__(self):
        manifest = json.loads((CACHE / "clips.json").read_text())
        self.clips = {str(c["id"]): c for c in manifest["clips"]}
        self.failed = manifest["failed"]
        d = np.load(CACHE / "clip_windows.npz")
        self.key, self.start, self.crow = d["key"], d["start"], d["crow_conf"]
        self.X = np.stack([pooling.pool(e) for e in d["emb"]]).astype(np.float32)
        self.new = np.array([not self.clips[k]["already_reviewed"] for k in self.key])
        self.recordist = np.array([norm(self.clips[k]["recordist"]) for k in self.key])

    def candidates(self, excluded_recordists=()):
        ok = self.new & (self.crow >= CROW_GATE)
        if excluded_recordists:
            ok &= ~np.isin(self.recordist, list(excluded_recordists))
        return np.where(ok)[0]

    def capped(self, rows):
        """At most CAP_PER_RECORDING rows per clip, evenly spaced in time."""
        by_clip = defaultdict(list)
        for i in rows:
            by_clip[self.key[i]].append(i)
        keep = []
        for members in by_clip.values():
            members.sort(key=lambda i: self.start[i])
            if len(members) > CAP_PER_RECORDING:
                picks = np.linspace(0, len(members) - 1, CAP_PER_RECORDING).round().astype(int)
                members = [members[p] for p in picks]
            keep.extend(members)
        return np.array(sorted(keep), dtype=int)

    def select(self, rule, selector=None, excluded_recordists=()):
        rows = self.candidates(excluded_recordists)
        if rule == "head_says_begging" and len(rows):
            rows = rows[selector.predict_proba(self.X[rows])[:, 1] >= HEAD_GATE]
        return self.capped(rows)

    def overlap_report(self):
        clips = list(self.clips.values())
        embedded = set(self.key.tolist())
        fresh = [c for c in clips if not c["already_reviewed"]]
        with_crow = {self.key[i] for i in self.candidates()}
        return {
            "witnessed_begging_clips": len(clips),
            "already_in_crowtools": sum(c["already_reviewed"] for c in clips),
            "new_clips": len(fresh),
            "new_clips_embedded": sum(str(c["id"]) in embedded for c in fresh),
            "new_clips_with_a_crow_window": len(with_crow),
            "new_clip_recordists": len({norm(c["recordist"]) for c in fresh}),
            "failed_to_embed": self.failed,
        }


def score_fold(E, A, cls, train, test, rules):
    """Out-of-fold P(cls) on the test rows for the baseline and each rule."""
    y = E.binary(cls)
    added_label = 1 if cls == TARGET else 0
    base = classifier().fit(E.X[train], y[train])
    out = {"baseline": base.predict_proba(E.X[test])[:, 1], "n_added": {}}
    selector = base if cls == TARGET else classifier().fit(E.X[train],
                                                           E.binary(TARGET)[train])
    excluded = E.test_recordists(test)
    for rule in rules:
        rows = A.select(rule, selector, excluded)
        out["n_added"][rule] = int(len(rows))
        if not len(rows):
            out[rule] = out["baseline"]
            continue
        X = np.concatenate([E.X[train], A.X[rows]])
        yy = np.concatenate([y[train], np.full(len(rows), added_label)])
        out[rule] = classifier().fit(X, yy).predict_proba(E.X[test])[:, 1]
    return test, out


class Protocol:
    """Recording-grouped 5-fold, the shipped head's scoring, with additions on the train side."""

    def __init__(self, E, A):
        self.E, self.A = E, A

    def jobs(self, cls, seed):
        y = self.E.binary(cls)
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
        return [(cls, seed, train, test) for train, test in cv.split(self.E.X, y, self.E.groups)]

    def run(self, plan, stage):
        jobs = [j for cls, seed in plan for j in self.jobs(cls, seed)]
        done = Parallel(n_jobs=JOBS, return_as="generator")(
            delayed(score_fold)(self.E, self.A, cls, train, test, RULES)
            for cls, seed, train, test in jobs)
        folds = defaultdict(list)
        for k, ((cls, seed, _, _), result) in enumerate(zip(jobs, done), 1):
            folds[(cls, seed)].append(result)
            stage.update(k, len(jobs))
        return {key: self._score(key[0], parts) for key, parts in folds.items()}

    def _score(self, cls, parts):
        y = self.E.binary(cls)
        arms = {}
        for arm in ("baseline", *RULES):
            proba = np.zeros(len(y))
            for test, out in parts:
                proba[test] = out[arm]
            arms[arm] = {"auc": float(roc_auc_score(y, proba)),
                         "ap": float(average_precision_score(y, proba))}
        arms["n_added_per_fold"] = {r: [out["n_added"][r] for _, out in parts] for r in RULES}
        return arms


class FieldCheck:
    """Human-labelled field spans, scored by heads fitted on all their rows. Exploratory."""

    CALL_TYPES = ("alarm call", "begging", "call", "flight call", "song")

    def __init__(self):
        meta = json.loads((CACHE / "field_labels.json").read_text())
        d = np.load(CACHE / "field_windows.npz")
        by_capture = defaultdict(list)
        for key, start, emb in zip(d["key"], d["start"], d["emb"]):
            by_capture[str(key)].append((float(start), emb))
        self.totals = meta["human_label_totals"]
        self.X, self.y, self.captures = [], [], []
        for lab in meta["labels"]:
            if lab["call_type"] not in self.CALL_TYPES:
                continue
            embs = [e for s, e in by_capture.get(str(lab["capture_id"]), [])
                    if s < lab["end"] and s + 3.0 > lab["start"]]
            if embs:
                self.X.append(pooling.pool(embs))
                self.y.append(1 if lab["call_type"] == TARGET else 0)
                self.captures.append(lab["capture_id"])
        self.X, self.y = np.array(self.X, dtype=np.float32), np.array(self.y)

    def score(self, models):
        out = {"human_label_totals": self.totals, "scored_spans": int(len(self.y)),
               "begging_spans": int(self.y.sum()),
               "begging_captures": sorted({int(c) for c, y in zip(self.captures, self.y) if y}),
               "captures": len(set(self.captures))}
        if 0 < self.y.sum() < len(self.y):
            for name, model in models.items():
                p = model.predict_proba(self.X)[:, 1]
                out[name] = {"auc": round(float(roc_auc_score(self.y, p)), 4),
                             "median_p_on_begging": round(float(np.median(p[self.y == 1])), 4),
                             "median_p_on_other": round(float(np.median(p[self.y == 0])), 4),
                             "begging_above_0.5": int((p[self.y == 1] >= 0.5).sum()),
                             "other_above_0.5": int((p[self.y == 0] >= 0.5).sum())}
        return out


class Experiment:
    def __init__(self):
        self.E, self.A = EvalSet(), Additions()
        self.report = {"overlap": self.A.overlap_report()}

    def cross_validate(self, run):
        plan = [(TARGET, s) for s in SEEDS] + [(c, 0) for c in GUARD_CLASSES]
        with run.stage("cross_validate") as stage:
            scores = Protocol(self.E, self.A).run(plan, stage)
        self.report["begging_by_seed"] = {str(s): scores[(TARGET, s)] for s in SEEDS}
        self.report["guard_seed0"] = {c: scores[(c, 0)] for c in GUARD_CLASSES}
        self.report["verdicts"] = {rule: self._verdict(rule, scores) for rule in RULES}

    def _verdict(self, rule, scores):
        gains = [scores[(TARGET, s)][rule]["auc"] - scores[(TARGET, s)]["baseline"]["auc"]
                 for s in SEEDS]
        drops = {c: scores[(c, 0)]["baseline"]["auc"] - scores[(c, 0)][rule]["auc"]
                 for c in GUARD_CLASSES}
        helps = gains[0] >= MIN_GAIN and sum(g > 0 for g in gains) >= MIN_POSITIVE_SEEDS
        guard_ok = (float(np.mean(list(drops.values()))) <= GUARD_MEAN_DROP
                    and max(drops.values()) <= GUARD_CLASS_DROP)
        return {"primary": rule == PRIMARY_RULE,
                "baseline_auc_seed0": round(scores[(TARGET, 0)]["baseline"]["auc"], 4),
                "candidate_auc_seed0": round(scores[(TARGET, 0)][rule]["auc"], 4),
                "gain_seed0": round(gains[0], 4),
                "gain_mean_10_seeds": round(float(np.mean(gains)), 4),
                "gain_min_max": [round(min(gains), 4), round(max(gains), 4)],
                "seeds_positive": int(sum(g > 0 for g in gains)),
                "ap_seed0": [round(scores[(TARGET, 0)]["baseline"]["ap"], 4),
                             round(scores[(TARGET, 0)][rule]["ap"], 4)],
                "guard_drops_seed0": {c: round(d, 4) for c, d in drops.items()},
                "guard_mean_drop": round(float(np.mean(list(drops.values()))), 4),
                "helps": bool(helps), "guard_ok": bool(guard_ok),
                "passes": bool(helps and guard_ok)}

    def final_heads(self, run):
        with run.stage("final_heads") as stage:
            E, A = self.E, self.A
            base = classifier().fit(E.X, E.binary(TARGET))
            models, rows_by_rule = {"baseline": base}, {}
            for k, rule in enumerate(RULES, 1):
                rows = A.select(rule, base)
                rows_by_rule[rule] = rows
                X = np.concatenate([E.X, A.X[rows]])
                Y = E.Y + [{TARGET}] * len(rows)
                head = MultiLabelHead(CLASSES).fit(X, Y)
                joblib.dump({"model": head, "classes": head.classes,
                             "feature": pooling.FEATURE, "backbone": pooling.BACKBONE,
                             "dim": pooling.POOLED_DIM, "multi_label": True,
                             "experiment": "0108", "rule": rule,
                             "added_rows": int(len(rows))},
                            CACHE / f"calltype_clf_candidate_{rule}.joblib")
                models[rule] = head.models[TARGET]
                stage.update(k, len(RULES))
            self.report["added_rows_full_fit"] = {
                r: {"rows": int(len(v)), "clips": len({A.key[i] for i in v})}
                for r, v in rows_by_rule.items()}
            self.report["field_check"] = FieldCheck().score(models)
            self.report["window_diagnostic"] = self._window_diagnostic(base)
            self.rows_by_rule = rows_by_rule

    def _window_diagnostic(self, base):
        A = self.A
        new = np.where(A.new)[0]
        p = base.predict_proba(A.X[new])[:, 1]
        crow = A.crow[new] >= CROW_GATE
        return {"windows_in_new_clips": int(len(new)),
                "crow_windows": int(crow.sum()),
                "crow_windows_head_says_begging": int((crow & (p >= HEAD_GATE)).sum()),
                "non_crow_windows_head_says_begging": int((~crow & (p >= HEAD_GATE)).sum())}

    def audit_list(self, run):
        """Clips the candidate is least sure about, scored by a head that never saw them."""
        with run.stage("audit_list") as stage:
            E, A = self.E, self.A
            rows = self.rows_by_rule[PRIMARY_RULE]
            clip_of = A.key[rows]
            y = E.binary(TARGET)
            scores = defaultdict(list)
            splits = list(GroupKFold(n_splits=5).split(rows, groups=clip_of))
            for k, (train, test) in enumerate(splits, 1):
                X = np.concatenate([E.X, A.X[rows[train]]])
                yy = np.concatenate([y, np.ones(len(train), dtype=int)])
                p = classifier().fit(X, yy).predict_proba(A.X[rows[test]])[:, 1]
                for clip, value in zip(clip_of[test], p):
                    scores[clip].append(float(value))
                stage.update(k, len(splits))
            ranked = sorted(scores, key=lambda c: np.mean(scores[c]))
            self.report["audit_least_sure_20"] = [
                {"recording_id": int(c), "source": A.clips[c]["source"],
                 "source_ref": A.clips[c]["source_ref"],
                 "mean_p_begging": round(float(np.mean(scores[c])), 3),
                 "windows": len(scores[c])} for c in ranked[:20]]

    def save(self):
        self.report["eval_rows"] = int(len(self.E.Y))
        self.report["eval_begging_rows"] = int(self.E.binary(TARGET).sum())
        self.report["eval_recordings_with_known_recordist"] = len(self.E.recordists)
        self.report["eval_recordings"] = len(set(self.E.groups.tolist()))
        self.report["class_counts"] = dict(Counter(c for y in self.E.Y for c in y))
        (HERE / "metrics.json").write_text(json.dumps(self.report, indent=2))


def main():
    run = Run("0108 witnessed begging clips", ["cross_validate", "final_heads", "audit_list"])
    exp = Experiment()
    print(json.dumps(exp.report["overlap"], indent=1))
    exp.cross_validate(run)
    for rule, verdict in exp.report["verdicts"].items():
        print(rule, json.dumps(verdict))
    exp.final_heads(run)
    exp.audit_list(run)
    exp.save()
    print("field:", json.dumps(exp.report["field_check"]))
    print("windows:", exp.report["window_diagnostic"], exp.report["added_rows_full_fit"])
    run.note("wrote metrics.json")


if __name__ == "__main__":
    main()
