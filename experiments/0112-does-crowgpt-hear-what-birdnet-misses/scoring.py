"""Shared scoring for 0112-0114: recordist-grouped one-vs-rest over the five contexts."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CONTEXTS = ("raptor_mobbing", "begging", "roost_gathering", "food_foraging", "flight_contact")


def head(C: float = 0.05):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000, class_weight="balanced"))


class GroupedOvR:
    """Five-context one-vs-rest, recordist-grouped 5-fold, with recordist-bootstrap intervals."""

    def __init__(self, labels: np.ndarray, groups: np.ndarray, classes=CONTEXTS, C: float = 0.05):
        self.labels, self.groups, self.classes, self.C = labels, groups, classes, C
        y = np.array([classes.index(c) for c in labels])
        self.folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(labels, y, groups))

    def scores(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros((len(X), len(self.classes)))
        for train, test in self.folds:
            for k, c in enumerate(self.classes):
                out[test, k] = head(self.C).fit(X[train], (self.labels[train] == c).astype(int)).decision_function(X[test])
        return out

    def macro(self, scores: np.ndarray, rows=None) -> float | None:
        rows = np.arange(len(self.labels)) if rows is None else rows
        aucs = []
        for k, c in enumerate(self.classes):
            y = (self.labels[rows] == c).astype(int)
            if y.sum() == 0 or y.sum() == len(y):
                return None
            aucs.append(roc_auc_score(y, scores[rows, k]))
        return float(np.mean(aucs))

    def resamples(self, n: int = 2000):
        members = defaultdict(list)
        for i, g in enumerate(self.groups):
            members[g].append(i)
        keys = list(members)
        rng = np.random.default_rng(0)
        for _ in range(n):
            yield np.concatenate([members[keys[j]] for j in rng.integers(0, len(keys), len(keys))])

    def report(self, scores: np.ndarray) -> dict:
        boot = [v for v in (self.macro(scores, r) for r in self.resamples()) if v is not None]
        per = {c: round(float(roc_auc_score((self.labels == c).astype(int), scores[:, k])), 4)
               for k, c in enumerate(self.classes)}
        return {"macro_auc": round(self.macro(scores), 4),
                "ci95": [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)],
                "per_context": per}

    def paired(self, a: np.ndarray, b: np.ndarray) -> dict:
        diffs = []
        for r in self.resamples():
            ma, mb = self.macro(a, r), self.macro(b, r)
            if ma is not None and mb is not None:
                diffs.append(ma - mb)
        return {"difference": round(self.macro(a) - self.macro(b), 4),
                "ci95": [round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)]}

    def permutation(self, X: np.ndarray, observed: float, n: int = 400, seed: int = 0, on_step=None) -> dict:
        """Each recordist's majority label shuffled across recordists; folds held fixed."""
        names = np.array(sorted(set(self.groups)))
        majority = []
        for g in names:
            values, counts = np.unique(self.labels[self.groups == g], return_counts=True)
            majority.append(values[np.argmax(counts)])
        majority = np.array(majority)
        rng = np.random.default_rng(seed)
        original, null = self.labels, []
        try:
            for k in range(n):
                mapping = dict(zip(names, rng.permutation(majority)))
                self.labels = np.array([mapping[g] for g in self.groups])
                value = self.macro(self.scores(X))
                if value is not None:
                    null.append(value)
                if on_step and (k + 1) % 20 == 0:
                    on_step(k + 1, n)
        finally:
            self.labels = original
        return {"perm_p": round((sum(v >= observed for v in null) + 1) / (len(null) + 1), 4),
                "perm_mean": round(float(np.mean(null)), 4), "perm_n": len(null)}
