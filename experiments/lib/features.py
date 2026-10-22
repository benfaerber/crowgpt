"""The feature cache one arm writes and the scorer reads.

Same schema as pipelines/ingest/build_dataset.py — `X`, `Y` as an object array
of CORE label lists, `groups` as the recording id, `feature` as the provenance
string — plus one addition that matters: **`keys`**.

build_dataset.py writes rows in corpus order and nothing else, so joining a
cached row back to its segment means reconstructing that order and hoping. 0012
had to write a 40-line `align()` that rebuilds the contiguous runs and then
verifies every row's labels, because a silent misalignment would attribute one
call's flags to another's audio and every number would be noise wearing a
decimal point.

Experiment 0025 compares five feature matrices row-for-row. Reconstructing that
join five times, once per backbone, in three interpreters, is exactly the shape
of mistake that produces a confident wrong answer — so each arm records the
segment key of every row and `read()` refuses a cache whose keys disagree with
the corpus it is being scored against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class Features:
    """One arm's embedding of the corpus, with its rows nailed to segment keys."""

    def __init__(self, X, Y, groups, keys, feature, meta=None):
        self.X = np.asarray(X)
        self.Y = [sorted(labels) for labels in Y]
        self.groups = np.asarray(groups)
        self.keys = list(keys)
        self.feature = feature
        self.meta = meta or {}
        n = len(self.keys)
        if not (len(self.X) == len(self.Y) == len(self.groups) == n):
            raise ValueError(
                f"{feature}: {len(self.X)} rows, {len(self.Y)} label sets, "
                f"{len(self.groups)} groups, {n} keys — these must agree"
            )

    def __len__(self):
        return len(self.keys)

    @property
    def dim(self):
        return int(self.X.shape[1]) if len(self.X) else 0

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            X=self.X,
            Y=np.array(self.Y, dtype=object),
            groups=self.groups,
            keys=np.array(self.keys),
            feature=self.feature,
            meta=np.array(_dumps(self.meta)),
        )
        return path

    @classmethod
    def read(cls, path, *, expect_keys=None):
        """Load an arm's cache, refusing one whose rows are not what we think.

        `expect_keys` is the canonical row set. Passing it turns a whole class
        of silent misjoins into a loud failure at load, which is the entire
        reason `keys` is in the schema.
        """
        path = Path(path)
        d = np.load(path, allow_pickle=True)
        if "keys" not in d.files:
            raise SystemExit(
                f"{path} predates the keyed schema — it has no `keys` array, so its "
                f"rows cannot be joined to segments except by reconstructing corpus "
                f"order. Rebuild it with the arm that wrote it."
            )
        features = cls(
            d["X"], d["Y"], d["groups"], [str(k) for k in d["keys"]],
            str(d["feature"]), _loads(str(d["meta"])) if "meta" in d.files else {},
        )
        if expect_keys is not None and features.keys != list(expect_keys):
            raise SystemExit(
                f"{path}: {len(features.keys)} rows against the corpus's "
                f"{len(expect_keys)} — and the keys differ, so these are not the "
                f"same segments in a different order.\n"
                f"  only here:   {sorted(set(features.keys) - set(expect_keys))[:4]}\n"
                f"  only corpus: {sorted(set(expect_keys) - set(features.keys))[:4]}\n"
                f"Scoring two arms on different rows compares nothing. Rebuild this "
                f"arm against the current corpus."
            )
        return features

    def restricted_to(self, keys):
        """This arm's rows in the given key order, dropping the rest.

        The corpus loses recordings as audio moves, and an arm cached before
        that drift holds rows the others cannot match. Aligning down to a shared
        key set is the honest fix; reordering silently is not.
        """
        index = {k: i for i, k in enumerate(self.keys)}
        missing = [k for k in keys if k not in index]
        if missing:
            raise SystemExit(
                f"{self.feature} is missing {len(missing)} of the {len(keys)} "
                f"requested rows (e.g. {missing[:4]}). It was built against a "
                f"different corpus state — rebuild it."
            )
        rows = [index[k] for k in keys]
        return Features(self.X[rows], [self.Y[i] for i in rows],
                        self.groups[rows], list(keys), self.feature, self.meta)


def concatenated(left, right, *, feature=None):
    """Two arms' features side by side, on rows they agree about.

    This is arm G — the test of whether a rival *adds* information rather than
    replacing it, which is a different question from which one wins alone.
    """
    if left.keys != right.keys:
        raise SystemExit(
            f"cannot concatenate {left.feature} with {right.feature}: their rows "
            f"are not the same segments. Restrict both to a shared key set first."
        )
    return Features(
        np.hstack([left.X, right.X]), left.Y, left.groups, left.keys,
        feature or f"{left.feature}+{right.feature}",
        {"parts": [left.feature, right.feature], "dims": [left.dim, right.dim]},
    )


def _dumps(obj):
    import json
    return json.dumps(obj, sort_keys=True)


def _loads(text):
    import json
    try:
        return json.loads(text)
    except ValueError:
        return {}
