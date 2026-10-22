"""Call-type head types, in an importable module because they get pickled.

`joblib.dump` stores a class by *reference* — module path plus name — so a head
defined inside a training script unpickles only in a process that happens to
define the same class in `__main__`. The analyzer imports nothing from the
training scripts, so such a head loads fine in the venv that wrote it and raises
`AttributeError: Can't get attribute 'MultiLabelHead'` the moment the inference
worker tries. That failure looks like a corrupt file rather than a missing
import, which is why this module exists rather than the class living beside the
code that fits it.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class MultiLabelHead:
    """One independent logistic regression per call type.

    The shipped alternative is a multiclass softmax, which cannot report a
    co-occurrence: its probabilities sum to one, so "begging AND a caw" is not
    something it can say however clear the audio. Worse, it never saw one —
    every trainer drops segments carrying two labels, discarding 241 of
    crow-tools' 2,494 rows including 23 `begging + call`.

    Here each class is fitted against its own binary target built from the full
    label set, so a segment tagged both is a positive for both and teaches both.

    `predict_proba` returns per-class probabilities that do **not** sum to one.
    Callers must not argmax them and call it a confidence — the whole point is
    that two can be high at once.
    """

    def __init__(self, classes):
        self.classes = list(classes)
        self.models = {}

    def fit(self, X, Y):
        """`Y` is a sequence of label *sets*, not a single label per row."""
        for cls in self.classes:
            y = np.array([1 if cls in labels else 0 for labels in Y])
            if len(set(y.tolist())) < 2:
                continue
            self.models[cls] = make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=5000, class_weight="balanced"),
            ).fit(X, y)
        self.classes = [c for c in self.classes if c in self.models]
        return self

    def predict_proba(self, X):
        return np.column_stack([self.models[c].predict_proba(X)[:, 1]
                                for c in self.classes])

    @property
    def n_features_in_(self):
        """So the analyzer's load-time width check can read this like a pipeline."""
        for model in self.models.values():
            return int(model.named_steps["standardscaler"].n_features_in_)
        return None
