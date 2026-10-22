"""Phase 4: train the original call-type classifier on BirdNET embeddings.

RETIRED as the served head 2026-08-09. The flat models/calltype_clf.joblib
this writes was the whole detector once, then its successors arrived —
train_american_crow.py and finally train_head.py, which writes the
models/american-crow/ bundle the analyzer actually serves. Nothing reads the
flat file any more; this stays as the Phase 4 record, not a tool.

Features are clip-level mean+std+max pooling (see pooling.py) over clean,
single-label recordings. The pooled representation beat mean-only across the
board in the clean regime (macro-F1 0.44 -> 0.48; song 0.62 -> 0.65, flight
0.90 -> 0.91) — std/max encode the temporal spread that mean throws away.

At n~130 the right model is a regularized linear classifier, not a deep net.
Evaluate honestly with stratified CV, fit the final model on all data, save it.
Runs in the BirdNET venv (sklearn + joblib):

  ../representation/.venv-birdnet/bin/python train.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pooling import FEATURE

HERE = Path(__file__).resolve().parent
# Pooled (mean+std+max) embeddings for every downloaded clip, multi-label.
# recover_and_pool.py builds this cache; we train on the CLEAN single-label
# subset — mixing compound clips into a class dilutes it (see the experiment).
POOLED = HERE / "results" / "pooled_embeddings.npz"
MODELS = HERE / "models"
MODELS.mkdir(exist_ok=True)
MIN_PER_CLASS = 8


def load():
    d = np.load(POOLED, allow_pickle=True)
    X, Y = d["X"], [set(l) for l in d["Y"]]
    single = np.array([len(s) == 1 for s in Y])
    X = X[single]
    y = np.array([next(iter(s)) for s, keep in zip(Y, single) if keep])
    strong = {c for c in set(y) if (y == c).sum() >= MIN_PER_CLASS}
    m = np.array([c in strong for c in y])
    return X[m], y[m]


def build_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced", C=1.0),
    )


def main():
    X, y = load()
    classes = sorted(set(y))
    counts = {c: int((y == c).sum()) for c in classes}
    print(f"{len(y)} clips, {X.shape[1]}-dim pooled features, classes: {counts}\n")

    n_splits = min(5, min(counts.values()))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    pred = cross_val_predict(build_model(), X, y, cv=cv)

    print("=== cross-validated performance ===")
    print(classification_report(y, pred, digits=3, zero_division=0))
    macro_f1 = f1_score(y, pred, average="macro")

    # Per-class one-vs-rest AUC — how reliably the model knows each call type.
    # This drives the reliability badges in the demo.
    proba = cross_val_predict(build_model(), X, y, cv=cv, method="predict_proba")
    order = list(build_model().fit(X, y).classes_)
    per_class_auc = {
        c: round(float(roc_auc_score((y == c).astype(int), proba[:, order.index(c)])), 3)
        for c in classes
    }
    print("per-class AUC (reliability):", per_class_auc)
    print(f"macro-F1: {macro_f1:.3f}\n")

    model = build_model().fit(X, y)
    joblib.dump(
        {"model": model, "classes": list(model.classes_),
         "feature": FEATURE, "dim": int(X.shape[1])},
        MODELS / "calltype_clf.joblib",
    )
    (MODELS / "metrics.json").write_text(json.dumps({
        "n": int(len(y)), "feature": FEATURE, "classes": counts,
        "cv_macro_f1": round(float(macro_f1), 3),
        "per_class_auc": per_class_auc,
    }, indent=2))
    print(f"saved model -> {MODELS / 'calltype_clf.joblib'}")


if __name__ == "__main__":
    main()
