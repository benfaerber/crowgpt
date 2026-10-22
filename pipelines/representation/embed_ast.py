"""Phase 3 upgrade: learned audio embeddings (AST) vs. classical features.

Uses the Audio Spectrogram Transformer (AudioSet-pretrained, pure torch/HF) to
embed each clip, then runs the *same* separability harness as the classical run
for an apples-to-apples comparison. Runs on the GPU.

Run:  python3 embed_ast.py
"""

import json
import subprocess

import numpy as np
import torch
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
from transformers import ASTFeatureExtractor, ASTModel

import experiment as e

MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"
AST_SR = 16000
WINDOW_S = 10.0  # AST's receptive field ~10.24s; feed the loudest window
OUT = e.OUT
CACHE = OUT / "ast_features.npz"


def decode16k(path):
    cmd = ["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "f32le",
           "-ac", "1", "-ar", str(AST_SR), "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=90).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def loudest_window(y):
    win = int(WINDOW_S * AST_SR)
    if len(y) <= win:
        return y
    hop = AST_SR  # 1s hops
    best, best_e = 0, -1.0
    for start in range(0, len(y) - win + 1, hop):
        e_ = float((y[start:start + win] ** 2).mean())
        if e_ > best_e:
            best_e, best = e_, start
    return y[best:best + win]


def embed_all():
    if CACHE.exists():
        d = np.load(CACHE, allow_pickle=True)
        return d["X"], d["y"].astype(str)
    rows = e.load_rows()
    fe = ASTFeatureExtractor.from_pretrained(MODEL)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ASTModel.from_pretrained(MODEL).to(device).eval()

    waves, labels = [], []
    for ct, path in rows:
        try:
            y = decode16k(path)
        except Exception:
            continue
        if y.size < AST_SR // 2:
            continue
        waves.append(loudest_window(y))
        labels.append(ct)

    embs = []
    batch = 8
    for i in range(0, len(waves), batch):
        chunk = waves[i:i + batch]
        inputs = fe(chunk, sampling_rate=AST_SR, return_tensors="pt")
        with torch.no_grad():
            out = model(inputs["input_values"].to(device))
        embs.append(out.pooler_output.cpu().numpy())
        print(f"  embedded {min(i + batch, len(waves))}/{len(waves)}", flush=True)
    X = np.concatenate(embs)
    y = np.array(labels)
    keep = {c for c in set(y) if (y == c).sum() >= e.MIN_PER_CLASS}
    m = np.array([c in keep for c in y])
    X, y = X[m], y[m]
    np.savez(CACHE, X=X, y=y)
    return X, y


def evaluate(X, y):
    classes = sorted(set(y))
    Xs = StandardScaler().fit_transform(X)
    n_splits = min(5, min((y == c).sum() for c in classes))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    out = {"embedder": "AST", "n_clips": int(len(y)), "dim": int(X.shape[1]),
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
    print(f"device: {'cuda' if torch.cuda.is_available() else 'cpu'}", flush=True)
    X, y = embed_all()
    out = evaluate(X, y)
    (OUT / "ast_metrics.json").write_text(json.dumps(out, indent=2))
    print("\n=== AST embeddings — separability ===")
    print("classes:", out["classes"])
    print(f"majority baseline acc: {out['baseline_majority_acc']}")
    print(f"kNN     acc={out['knn']['accuracy']} macroF1={out['knn']['macro_f1']}")
    print(f"logreg  acc={out['logreg']['accuracy']} macroF1={out['logreg']['macro_f1']}")
    print(f"silhouette: {out['silhouette_true_labels']}  kmeans ARI: {out['kmeans_ari']}")
    print("one-vs-rest AUC:", out["one_vs_rest_auc"])


if __name__ == "__main__":
    main()
