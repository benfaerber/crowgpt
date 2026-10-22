"""Recording-grouped probes over a frozen embedding, shared by every arm.

Experiment 0025 compares embedding backbones, so the scoring has to be the one
thing that does *not* vary between arms. This module is that constant.

`GroupedProbe.ovr_auc` is deliberately logic-identical to
`pipelines/ingest/evaluate.one_vs_rest_auc` — the same thin-class guards, the
same `StratifiedGroupKFold`, the same balanced logreg, the same swallow of
sklearn's ValueError. That is not tidiness. Every published number in Phase 4
came out of that function, and an arm scored by anything else is not comparable
to the incumbent no matter how carefully it was embedded. `reproduces()` makes
the claim checkable rather than asserted: it re-scores the committed crow-tools
cache and refuses to return unless it lands on experiment 0012's AUCs.

sklearn and numpy only, so it imports in the BirdNET venv (numpy<2, no torch)
and the Perch venv (numpy>=2, TensorFlow) alike. Nothing here may grow a
dependency that only one of them can satisfy.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, f1_score,
                             roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# The guards from ingest/evaluate.py, named so the reason survives the copy.
MIN_POSITIVES = 8
MIN_GROUPS = 3
MAX_SPLITS = 5

# What 0012 measured on the committed cache. The self-check target.
INCUMBENT_CORE_AUC = {
    "alarm call": 0.942,
    "begging": 0.916,
    "call": 0.961,
    "song": 0.913,
}


def _classifier():
    """The head every arm is scored with — the shipped one, unchanged.

    A linear probe on frozen features, so the comparison is about the
    representation rather than about who got the better classifier.
    """
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced"),
    )


class GroupedProbe:
    """One feature matrix, scored so no recording spans the train/test split.

    `Y` is multi-label (a sequence of label sets), matching the npz schema
    build_dataset.py writes. `groups` is the recording id per row — the whole
    point, since segments from one recording share a mic, a background and
    usually a bird, and an ungrouped split scores all three.
    """

    def __init__(self, X, Y, groups, *, name=""):
        self.X = np.asarray(X)
        self.Y = [set(labels) for labels in Y]
        self.groups = np.asarray(groups)
        self.name = name
        if not (len(self.X) == len(self.Y) == len(self.groups)):
            raise ValueError(
                f"{name or 'probe'}: {len(self.X)} rows, {len(self.Y)} label sets, "
                f"{len(self.groups)} groups — these must agree"
            )

    def __len__(self):
        return len(self.Y)

    @property
    def n_recordings(self):
        return len(set(self.groups.tolist()))

    def binary(self, cls):
        return np.array([1 if cls in s else 0 for s in self.Y])

    def _cv_proba(self, yb, seed):
        """Out-of-fold P(positive), or None when the class is too thin to score.

        Returns None rather than a number in three cases, all of which mean
        "this corpus cannot answer that question": too few positives, positives
        from too few recordings (an AUC there is a recording classifier), or
        sklearn refusing the split outright.
        """
        pos = int(yb.sum())
        n_groups_pos = len(set(self.groups[yb == 1].tolist()))
        if pos < MIN_POSITIVES or pos == len(yb) or n_groups_pos < MIN_GROUPS:
            return None, pos
        n_splits = min(MAX_SPLITS, n_groups_pos,
                       len(set(self.groups[yb == 0].tolist())))
        cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True,
                                  random_state=seed)
        try:
            proba = cross_val_predict(_classifier(), self.X, yb, cv=cv,
                                      groups=self.groups,
                                      method="predict_proba")[:, 1]
        except ValueError:
            return None, pos
        return proba, pos

    def ovr_auc(self, cls, *, seed=0):
        """Grouped one-vs-rest AUC for one class, and its positive count."""
        proba, pos = self._cv_proba(self.binary(cls), seed)
        if proba is None:
            return None, pos
        return round(float(roc_auc_score(self.binary(cls), proba)), 3), pos

    def ovr_ap(self, cls, *, seed=0):
        """Average precision — what AUC hides when a class is rare.

        0012 established that the decision-relevant number is precision at a
        recall rather than cluster geometry, and AP is the summary of that
        curve. Reported beside AUC, never instead of it.
        """
        proba, pos = self._cv_proba(self.binary(cls), seed)
        if proba is None:
            return None, pos
        return round(float(average_precision_score(self.binary(cls), proba)), 3), pos

    def core_auc(self, classes, *, seed=0):
        return {cls: self.ovr_auc(cls, seed=seed)[0] for cls in classes}

    def multiclass(self, classes, *, seed=0):
        """Macro-F1 over the single-label rows, on recording-grouped folds.

        Multi-label rows are dropped rather than resolved: a segment tagged both
        alarm and call has no single right answer, and picking one would grade
        the model on a coin flip. train.py:38-46 drops them the same way.
        """
        keep = np.array([len(s & set(classes)) == 1 for s in self.Y])
        if keep.sum() < MIN_POSITIVES:
            return None
        X = self.X[keep]
        y = np.array([next(iter(s & set(classes)))
                      for s, k in zip(self.Y, keep) if k])
        groups = self.groups[keep]

        present = [c for c in classes if (y == c).sum() >= MIN_POSITIVES]
        strong = np.isin(y, present)
        X, y, groups = X[strong], y[strong], groups[strong]
        n_splits = min(MAX_SPLITS,
                       min(len(set(groups[y == c].tolist())) for c in present))
        if n_splits < 2:
            return None
        cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True,
                                  random_state=seed)
        try:
            pred = cross_val_predict(_classifier(), X, y, cv=cv, groups=groups)
        except ValueError:
            return None
        return {
            "macro_f1": round(float(f1_score(y, pred, average="macro")), 3),
            "per_class_f1": {
                c: round(float(f1_score(y, pred, labels=[c], average="macro")), 3)
                for c in present
            },
            "n": int(len(y)),
            "classes": present,
            "y_true": y.tolist(),
            "y_pred": pred.tolist(),
        }


class WithinRecordingProbe:
    """One pair of labels, scored only where a recording carries both.

    0012's best-designed probe, and the reason it is worth the extra class:
    `mob` vs `alert` across the whole corpus is partly a recording classifier,
    because most recordings hold only one of them. Restricting to the
    recordings holding both makes recording identity provably useless, so what
    is left is the acoustic difference or nothing.

    Thin by construction — 0012 got n=138 over 41 recordings — so this reports
    the spread over several seeds and the caller is expected to refuse a
    verdict when two arms' spreads overlap.
    """

    def __init__(self, X, segments, groups, *, positive, negative):
        self.positive = positive
        self.negative = negative
        X = np.asarray(X)
        groups = np.asarray(groups)

        pos = np.array([bool(s.flags.get(positive)) for s in segments])
        neg = np.array([bool(s.flags.get(negative)) for s in segments])
        exclusive = pos ^ neg

        both = {g for g in set(groups.tolist())
                if pos[(groups == g) & exclusive].any()
                and neg[(groups == g) & exclusive].any()}
        keep = exclusive & np.isin(groups, list(both))

        self.X = X[keep]
        self.y = pos[keep].astype(int)
        self.groups = groups[keep]
        self.recordings = len(both)

    def auc(self, *, seeds=range(5)):
        """AUC per seed, sorted. The spread is the finding, not the best one."""
        if len(self.y) < MIN_POSITIVES or self.recordings < MIN_GROUPS:
            return {"auc": None, "n": int(len(self.y)),
                    "recordings": self.recordings, "seeds": []}
        probe = GroupedProbe(self.X, [{"pos"} if v else {"neg"} for v in self.y],
                             self.groups)
        scores = []
        for seed in seeds:
            auc, _ = probe.ovr_auc("pos", seed=seed)
            if auc is not None:
                scores.append(auc)
        return {
            "auc": max(scores) if scores else None,
            "spread": [min(scores), max(scores)] if scores else None,
            "seeds": sorted(scores),
            "n": int(len(self.y)),
            "n_positive": int(self.y.sum()),
            "recordings": self.recordings,
        }


def reproduces(X, Y, groups, *, expected=None, tol=0.002):
    """Refuse to proceed unless this harness lands on 0012's published numbers.

    The whole experiment rests on arms being comparable to an incumbent that
    was measured a year of commits ago by a different function. This is the
    only thing standing between "we reproduced it" and "we assumed it".
    """
    expected = expected or INCUMBENT_CORE_AUC
    probe = GroupedProbe(X, Y, groups, name="self-check")
    got = probe.core_auc(sorted(expected))
    drift = {
        cls: (want, got.get(cls))
        for cls, want in expected.items()
        if got.get(cls) is None or abs(got[cls] - want) > tol
    }
    if drift:
        lines = "\n".join(f"  {c:<12} expected {w}, got {g}"
                          for c, (w, g) in sorted(drift.items()))
        raise SystemExit(
            "Harness self-check FAILED — this does not reproduce experiment 0012:\n"
            f"{lines}\n\n"
            "Every arm is scored against those numbers, so nothing downstream is\n"
            "comparable until this passes. Either probe.py has drifted from\n"
            "pipelines/ingest/evaluate.one_vs_rest_auc, or the cached corpus has\n"
            "changed under it. Do not 'fix' this by loosening tol."
        )
    return got
