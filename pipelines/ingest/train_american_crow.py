"""Retrain the American Crow call-type head on the clean vendored labels.

The vendored corpus has no flight-call class, so combine its human-reviewed
alarm/begging/call/song (2528 segments) with the archive pooled set (which
carries flight call). Writes pipelines/training/models/american-crow/, which the
demo loads over the weak archive-only head at models/calltype_clf.joblib.

Caveat: its segments are single-3s-window pooled (std block ~0) while the archive set
is whole-clip, so the combined std/max block partly encodes source and the grouped
AUCs below are optimistic. The real win is 2221 clean alarm/song examples vs the
old ~130 clips — spot-check on demo audio.

  ../representation/.venv-birdnet/bin/python train_american_crow.py
"""

import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
CROWTOOLS = HERE / "results" / "pooled_embeddings_crowtools_all-public.npz"
ARCHIVE = HERE.parent / "training" / "results" / "pooled_embeddings.npz"
OUT = HERE.parent / "training" / "models" / "american-crow"

import sys  # noqa: E402

sys.path.insert(0, str(HERE.parent / "training"))
# The one home of the class list. A copy here trained a head on one list
# while the pooling stage built Y against another the day they diverged.
import pooling  # noqa: E402
from recover_and_pool import CORE  # noqa: E402
MIN_PER_CLASS = 8


def load(path, prefix):
    d = np.load(path, allow_pickle=True)
    Y = [set(s) for s in d["Y"]]
    if "groups" in d.files:
        groups = np.array([f"{prefix}:{g}" for g in d["groups"]])
    else:  # one vector per clip -> each row is its own group
        groups = np.array([f"{prefix}:{i}" for i in range(len(Y))])
    return d["X"], Y, groups


def grouped_auc(X, Y, groups, cls):
    yb = np.array([1 if cls in s else 0 for s in Y])
    pos = int(yb.sum())
    n_groups_pos = len(set(groups[yb == 1]))
    if pos < MIN_PER_CLASS or pos == len(yb) or n_groups_pos < 3:
        return None
    n_splits = min(5, n_groups_pos, len(set(groups[yb == 0])))
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=0)
    clf = make_pipeline(StandardScaler(),
                        LogisticRegression(max_iter=5000, class_weight="balanced"))
    try:
        proba = cross_val_predict(clf, X, yb, cv=cv, groups=groups,
                                  method="predict_proba")[:, 1]
    except ValueError:
        return None
    return round(float(roc_auc_score(yb, proba)), 3)


def main():
    if not CROWTOOLS.exists():
        raise SystemExit(f"Missing {CROWTOOLS} — run build_dataset.py first.")
    Xc, Yc, Gc = load(CROWTOOLS, "ct")
    Xx, Yx, Gx = load(ARCHIVE, "xc")
    X = np.concatenate([Xc, Xx])
    Y = Yc + Yx
    G = np.concatenate([Gc, Gx])
    print(f"combined {len(Yc)} reviewed + {len(Yx)} archive = {len(Y)} examples")

    auc = {c: grouped_auc(X, Y, G, c) for c in CORE}

    # Ship a multiclass logreg on the clean single-label subset.
    single = [(x, next(iter(s))) for x, s in zip(X, Y) if len(s) == 1]
    Xs = np.array([x for x, _ in single])
    ys = np.array([c for _, c in single])
    strong = {c for c in set(ys) if (ys == c).sum() >= MIN_PER_CLASS}
    keep = np.array([c in strong for c in ys])
    Xs, ys = Xs[keep], ys[keep]
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced")).fit(Xs, ys)

    OUT.mkdir(parents=True, exist_ok=True)
    # `feature` and `dim` are what analyzer/birdnet.py checks at load, so a head
    # trained on one backbone cannot be silently served by another.
    joblib.dump({"model": model, "classes": list(model.classes_),
                 "feature": pooling.FEATURE, "backbone": pooling.BACKBONE,
                 "dim": int(X.shape[1])},
                OUT / "calltype_clf.joblib")
    # `source` names crow-tools deliberately: a shipped model should say whose
    # labels trained it, and that is the one place the credit has to travel.
    (OUT / "metrics.json").write_text(json.dumps({
        "n": int(len(X)), "n_single_label": int(len(ys)),
        "source": "crow-tools (clean) + archive weak tags (flight call)",
        "classes": dict(Counter(ys)), "per_class_auc": auc,
    }, indent=2))

    print("classes:", list(model.classes_))
    print("grouped one-vs-rest AUC:", auc)
    print("saved ->", OUT / "calltype_clf.joblib")


if __name__ == "__main__":
    main()
