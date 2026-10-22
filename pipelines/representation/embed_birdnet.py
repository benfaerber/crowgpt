"""Phase 3 diagnostic: BirdNET (bird-specific) embeddings vs. everything else.

If a model trained on bird calls ALSO plateaus around ~0.7 AUC, the ceiling is
the labels, not the representation. If it jumps well past, the representation was
the bottleneck. Same separability harness as the classical / AST runs.

Runs in the isolated .venv-birdnet (tflite + librosa, numpy<2):
  .venv-birdnet/bin/python embed_birdnet.py
"""

import contextlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    adjusted_rand_score,
    f1_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "corvid.db"
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
CACHE = OUT / "birdnet_features.npz"
MIN_PER_CLASS = 8
DEVNULL = open(os.devnull, "w")


def load_rows():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT call_type, file_path FROM recordings "
        "WHERE downloaded = 1 AND file_path IS NOT NULL"
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        ct = (r["call_type"] or "").strip().lower()
        if not ct or "," in ct or ct in {"uncertain", "unknown"}:
            continue
        p = Path(r["file_path"])
        if p.exists():
            out.append((ct, p))
    return out


def embed_all():
    if CACHE.exists():
        d = np.load(CACHE, allow_pickle=True)
        return d["X"], d["y"].astype(str)
    rows = load_rows()
    with contextlib.redirect_stdout(DEVNULL):
        analyzer = Analyzer()
    X, y = [], []
    for i, (ct, p) in enumerate(rows):
        try:
            with contextlib.redirect_stdout(DEVNULL):
                rec = Recording(analyzer, str(p), min_conf=0.1)
                rec.extract_embeddings()
            segs = rec.embeddings
            if not segs:
                continue
            vec = np.mean([s["embeddings"] for s in segs], axis=0)  # clip = mean of 3s segs
            if np.isfinite(vec).all():
                X.append(vec)
                y.append(ct)
        except Exception as ex:  # noqa: BLE001
            print(f"  fail {p.name}: {ex}", file=sys.stderr)
        if (i + 1) % 20 == 0:
            print(f"  embedded {i + 1}/{len(rows)}", file=sys.stderr, flush=True)
    X, y = np.array(X), np.array(y)
    keep = {c for c in set(y) if (y == c).sum() >= MIN_PER_CLASS}
    m = np.array([c in keep for c in y])
    X, y = X[m], y[m]
    np.savez(CACHE, X=X, y=y)
    return X, y


def evaluate(X, y):
    classes = sorted(set(y))
    Xs = StandardScaler().fit_transform(X)
    n_splits = min(5, min((y == c).sum() for c in classes))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    out = {"embedder": "BirdNET", "n_clips": int(len(y)), "dim": int(X.shape[1]),
           "classes": {c: int((y == c).sum()) for c in classes}}
    for name, clf in [
        ("knn", KNeighborsClassifier(n_neighbors=5)),
        ("logreg", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ]:
        pred = cross_val_predict(clf, Xs, y, cv=cv)
        out[name] = {"accuracy": round(float(accuracy_score(y, pred)), 3),
                     "macro_f1": round(float(f1_score(y, pred, average="macro")), 3)}
    out["baseline_majority_acc"] = round(
        float(max((y == c).sum() for c in classes) / len(y)), 3)
    km = KMeans(n_clusters=len(classes), n_init=10, random_state=0).fit(Xs)
    out["silhouette_true_labels"] = round(float(silhouette_score(Xs, y)), 3)
    out["kmeans_ari"] = round(float(adjusted_rand_score(y, km.labels_)), 3)
    ovr = {}
    for c in classes:
        yb = (y == c).astype(int)
        proba = cross_val_predict(
            LogisticRegression(max_iter=3000, class_weight="balanced"),
            Xs, yb, cv=cv, method="predict_proba")[:, 1]
        ovr[c] = round(float(roc_auc_score(yb, proba)), 3)
    out["one_vs_rest_auc"] = ovr
    return out


def main():
    X, y = embed_all()
    out = evaluate(X, y)
    (OUT / "birdnet_metrics.json").write_text(json.dumps(out, indent=2))
    print("\n=== BirdNET embeddings — separability ===")
    print("classes:", out["classes"])
    print(f"majority baseline acc: {out['baseline_majority_acc']}")
    print(f"kNN     acc={out['knn']['accuracy']} macroF1={out['knn']['macro_f1']}")
    print(f"logreg  acc={out['logreg']['accuracy']} macroF1={out['logreg']['macro_f1']}")
    print(f"silhouette: {out['silhouette_true_labels']}  kmeans ARI: {out['kmeans_ari']}")
    print("one-vs-rest AUC:", out["one_vs_rest_auc"])


if __name__ == "__main__":
    main()
