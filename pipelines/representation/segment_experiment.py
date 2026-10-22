"""Phase 3 follow-up: does per-call segmentation beat whole-clip features?

Whole-clip pooling was the biggest suspected confound. Here we detect individual
vocalization events (energy envelope) and classify *those*, with clip-grouped
CV so events from the same recording never leak across the train/test split.

Run:  python3 segment_experiment.py
"""

import json

import numpy as np
from scipy.ndimage import binary_closing, binary_opening
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

import experiment as e

OUT = e.OUT
SR = e.SR
E_FRAME, E_HOP = 1024, 256
MAX_EVENTS = 15


def detect_events(y):
    n = 1 + (len(y) - E_FRAME) // E_HOP
    if n < 4:
        return []
    idx = np.arange(E_FRAME)[None, :] + E_HOP * np.arange(n)[:, None]
    env = np.sqrt((y[idx] ** 2).mean(1) + 1e-12)
    env = np.convolve(env, np.ones(5) / 5, "same")
    above = env >= np.percentile(env, 70)
    above = binary_closing(above, structure=np.ones(9))  # bridge short gaps
    above = binary_opening(above, structure=np.ones(3))  # drop blips
    events, i = [], 0
    while i < len(above):
        if not above[i]:
            i += 1
            continue
        j = i
        while j < len(above) and above[j]:
            j += 1
        start, end = i * E_HOP, min(len(y), j * E_HOP + E_FRAME)
        dur = (end - start) / SR
        if 0.12 <= dur <= 2.5:
            events.append((start, end, float(env[i:j].max())))
        i = j
    events.sort(key=lambda t: -t[2])  # keep the loudest events
    return [(s, en) for s, en, _ in events[:MAX_EVENTS]]


def build():
    rows = e.load_rows()
    X, y, groups = [], [], []
    n_events = []
    for clip_id, (ct, path) in enumerate(rows):
        sig = e.decode(path)
        if sig is None:
            continue
        evs = detect_events(sig)
        n_events.append(len(evs))
        for s, en in evs:
            f = e.features_from_samples(sig[s:en])
            if f is not None and np.isfinite(f).all():
                X.append(f)
                y.append(ct)
                groups.append(clip_id)
    X, y, groups = np.array(X), np.array(y), np.array(groups)
    keep = {c for c in set(y) if (y == c).sum() >= 10}
    m = np.array([c in keep for c in y])
    return X[m], y[m], groups[m], sorted(keep), int(np.mean(n_events) if n_events else 0)


def main():
    X, y, groups, classes, avg_events = build()
    Xs = StandardScaler().fit_transform(X)
    n_splits = min(5, len(set(groups[np.isin(y, classes)])))
    cv = GroupKFold(n_splits=min(5, n_splits))

    out = {
        "n_events": int(len(y)),
        "avg_events_per_clip": avg_events,
        "classes": {c: int((y == c).sum()) for c in classes},
    }

    pred = cross_val_predict(
        LogisticRegression(max_iter=3000, class_weight="balanced"),
        Xs, y, cv=cv, groups=groups,
    )
    out["multiclass"] = {
        "accuracy": round(float(accuracy_score(y, pred)), 3),
        "macro_f1": round(float(f1_score(y, pred, average="macro")), 3),
        "baseline_majority_acc": round(
            float(max((y == c).sum() for c in classes) / len(y)), 3
        ),
    }

    ovr = {}
    for c in classes:
        yb = (y == c).astype(int)
        proba = cross_val_predict(
            LogisticRegression(max_iter=3000, class_weight="balanced"),
            Xs, yb, cv=cv, groups=groups, method="predict_proba",
        )[:, 1]
        ovr[c] = round(float(roc_auc_score(yb, proba)), 3)
    out["one_vs_rest_auc"] = ovr

    (OUT / "segment_metrics.json").write_text(json.dumps(out, indent=2))
    print(f"events: {out['n_events']} (avg {avg_events}/clip)  classes: {out['classes']}")
    print(f"multiclass (clip-grouped CV): acc={out['multiclass']['accuracy']} "
          f"macroF1={out['multiclass']['macro_f1']} "
          f"(baseline {out['multiclass']['baseline_majority_acc']})")
    print("one-vs-rest AUC:")
    for c, a in sorted(ovr.items(), key=lambda kv: -kv[1]):
        print(f"  {c:<12} {a}")


if __name__ == "__main__":
    main()
