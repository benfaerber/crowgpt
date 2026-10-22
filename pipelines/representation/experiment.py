"""Phase 3 representation experiment.

Question: do the archives' call-type labels (call / flight call / alarm call / song)
form separable acoustic clusters? If an off-the-shelf feature space already
carries crow call-type structure, the representation approach is viable and the
Phase 0 acoustic-separability assumption holds.

First-pass features are classical (log-mel MFCCs + deltas + spectral summaries),
pooled over the *loud* frames only — matching the loud/public-call scope. Audio
is decoded with ffmpeg and features computed with numpy/scipy (no librosa/numba,
which conflicts with NumPy 2.x here). A pretrained embedder (BirdNET / PANNs) is
the documented upgrade path.

Run:  python3 experiment.py
Reads the shared corpus at cawtalker/data/corvid.db; writes results/ here.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.fftpack import dct
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.manifold import TSNE
from sklearn.metrics import (
    accuracy_score,
    adjusted_rand_score,
    confusion_matrix,
    f1_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "corvid.db"
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)

SR = 22050
N_FFT = 2048
HOP = 512
N_MELS = 40
N_MFCC = 20
LOUD_PERCENTILE = 60
MAX_SECONDS = 60
MIN_PER_CLASS = 8

_FREQS = np.fft.rfftfreq(N_FFT, 1 / SR)


def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + f / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (m / 2595.0) - 1.0)


def mel_filterbank() -> np.ndarray:
    mels = np.linspace(hz_to_mel(0), hz_to_mel(SR / 2), N_MELS + 2)
    bins = np.floor((N_FFT + 1) * mel_to_hz(mels) / SR).astype(int)
    fb = np.zeros((N_MELS, N_FFT // 2 + 1))
    for i in range(1, N_MELS + 1):
        lo, ctr, hi = bins[i - 1], bins[i], bins[i + 1]
        for j in range(lo, ctr):
            if ctr > lo:
                fb[i - 1, j] = (j - lo) / (ctr - lo)
        for j in range(ctr, hi):
            if hi > ctr:
                fb[i - 1, j] = (hi - j) / (hi - ctr)
    return fb


_MEL_FB = mel_filterbank()


def decode(path: Path) -> np.ndarray | None:
    cmd = [
        "ffmpeg", "-v", "quiet", "-i", str(path),
        "-f", "f32le", "-ac", "1", "-ar", str(SR), "-t", str(MAX_SECONDS), "-",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    y = np.frombuffer(raw, dtype=np.float32).copy()
    return y if y.size >= SR * 0.5 else None


def features_from_samples(y: np.ndarray | None) -> np.ndarray | None:
    if y is None or y.size < SR * 0.05:
        return None
    min_len = N_FFT + 3 * HOP  # ensure >= 4 frames, so short call events work too
    if len(y) < min_len:
        y = np.pad(y, (0, min_len - len(y)))
    n = 1 + (len(y) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    raw_frames = y[idx]
    win = raw_frames * np.hanning(N_FFT)[None, :]
    ps = np.abs(np.fft.rfft(win, axis=1)) ** 2  # (n, F)

    mel = ps @ _MEL_FB.T  # (n, N_MELS)
    logmel = np.log(mel + 1e-8)
    mfcc = dct(logmel, type=2, axis=1, norm="ortho")[:, :N_MFCC]  # (n, N_MFCC)
    delta = np.diff(mfcc, axis=0, prepend=mfcc[:1])

    energy = ps.sum(1)
    mask = energy >= np.percentile(energy, LOUD_PERCENTILE)
    if mask.sum() < 3:
        mask = np.ones(n, dtype=bool)

    denom = ps.sum(1) + 1e-12
    centroid = (ps * _FREQS).sum(1) / denom
    bandwidth = np.sqrt((ps * (_FREQS - centroid[:, None]) ** 2).sum(1) / denom)
    zcr = np.mean(np.abs(np.diff(np.sign(raw_frames), axis=1)) > 0, axis=1)

    sel, dsel = mfcc[mask], delta[mask]
    return np.concatenate(
        [
            sel.mean(0), sel.std(0),
            dsel.mean(0), dsel.std(0),
            [
                centroid[mask].mean(), centroid[mask].std(),
                bandwidth[mask].mean(), bandwidth[mask].std(),
                zcr[mask].mean(), zcr[mask].std(),
            ],
        ]
    )


def extract(path: Path) -> np.ndarray | None:
    return features_from_samples(decode(path))


def load_rows() -> list[tuple[str, Path]]:
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
        path = Path(r["file_path"])
        if path.exists():
            out.append((ct, path))
    return out


def build_dataset():
    rows = load_rows()
    feats, labels, failed = [], [], 0
    for ct, path in rows:
        f = extract(path)
        if f is None or not np.isfinite(f).all():
            failed += 1
            continue
        feats.append(f)
        labels.append(ct)
    X, y = np.array(feats), np.array(labels)
    keep = {c for c in set(y) if (y == c).sum() >= MIN_PER_CLASS}
    m = np.array([c in keep for c in y])
    return X[m], y[m], sorted(keep), failed, len(rows)


def separability(X, y, classes):
    Xs = StandardScaler().fit_transform(X)
    n_splits = min(5, min((y == c).sum() for c in classes))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
    results = {}
    for name, clf in [
        ("knn", KNeighborsClassifier(n_neighbors=5)),
        ("logreg", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ]:
        pred = cross_val_predict(clf, Xs, y, cv=cv)
        results[name] = {
            "accuracy": round(float(accuracy_score(y, pred)), 3),
            "macro_f1": round(float(f1_score(y, pred, average="macro")), 3),
            "confusion": confusion_matrix(y, pred, labels=classes).tolist(),
        }
    results["baseline_majority_acc"] = round(
        float(max((y == c).sum() for c in classes) / len(y)), 3
    )
    km = KMeans(n_clusters=len(classes), n_init=10, random_state=0).fit(Xs)
    results["silhouette_true_labels"] = round(float(silhouette_score(Xs, y)), 3)
    results["kmeans_ari"] = round(float(adjusted_rand_score(y, km.labels_)), 3)
    return results, Xs


def plot(Xs, y, classes, title):
    pca = PCA(n_components=2).fit_transform(Xs)
    perp = min(30, max(5, len(y) // 4))
    tsne = TSNE(n_components=2, perplexity=perp, init="pca", random_state=0).fit_transform(Xs)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    cmap = plt.get_cmap("tab10")
    for proj, ax, name in [(pca, axes[0], "PCA"), (tsne, axes[1], "t-SNE")]:
        for i, c in enumerate(classes):
            m = y == c
            ax.scatter(proj[m, 0], proj[m, 1], s=30, alpha=0.75,
                       color=cmap(i), label=f"{c} (n={int(m.sum())})", edgecolors="none")
        ax.set_title(name)
        ax.set_xticks([])
        ax.set_yticks([])
    axes[0].legend(loc="best", fontsize=8, framealpha=0.9)
    fig.suptitle(title, fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "clusters.png", dpi=130)
    plt.close(fig)


def main():
    if not DB.exists():
        sys.exit(f"No corpus DB at {DB} — the corpus must be populated first.")
    X, y, classes, failed, total = build_dataset()
    counts = {c: int((y == c).sum()) for c in classes}
    print(f"loaded {total} clean-labeled clips, {failed} failed to decode/extract")
    print(f"classes kept (>= {MIN_PER_CLASS}): {counts}")
    if len(classes) < 2:
        sys.exit("Need at least 2 classes with enough samples; download more.")

    metrics, Xs = separability(X, y, classes)
    metrics.update(classes=counts, n_clips=int(len(y)),
                   n_features=int(X.shape[1]), decode_failures=failed)

    plot(Xs, y, classes,
         "Crow call-type separability (American Crow, archive corpus) — MFCC features")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print("\n=== SEPARABILITY ===")
    print(f"majority baseline acc: {metrics['baseline_majority_acc']}")
    print(f"kNN     acc={metrics['knn']['accuracy']} macroF1={metrics['knn']['macro_f1']}")
    print(f"logreg  acc={metrics['logreg']['accuracy']} macroF1={metrics['logreg']['macro_f1']}")
    print(f"silhouette (true labels): {metrics['silhouette_true_labels']}")
    print(f"kmeans ARI vs labels:     {metrics['kmeans_ari']}")
    print(f"\nwrote {OUT/'clusters.png'} and {OUT/'metrics.json'}")


if __name__ == "__main__":
    main()
