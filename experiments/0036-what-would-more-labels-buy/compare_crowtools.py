#!/usr/bin/env python3
"""Cawtalker against crow-tools on the one axis where they can actually be compared.

Their reported numbers and ours normally cannot be set side by side: they report
accuracy and balanced accuracy on a segment-level 88/12 split, we report AUC and
AP on recording-grouped 5-fold, and neither metric converts into the other.

But the *labels are the same labels*. Cawtalker vendored crow-tools' corpus, so
the task, the classes and the ground truth are identical and only three things
differ — the backbone (BirdNET 3072-d pooled vs AVES 768-d mean-pooled), the head
(logreg vs a 240K multi-task MLP), and the split. That makes two clean questions:

  1. BACKBONE+HEAD, protocol held fixed. Run our features through *their* exact
     protocol — segment-level 88/12, seed 18202, balanced accuracy — and put the
     result next to their RESULTS.txt. Any difference is ours vs theirs, because
     the evaluation is now identical.

  2. WHAT THEIR SPLIT IS WORTH, features held fixed. Same features, same head,
     same rows; only the split changes, segment-level against recording-grouped.
     That converts "their numbers are inflated" from an assertion into a number.

Metrics reproduce theirs exactly (classifier/model.py compute_composite_score):
balanced accuracy for the binaries is the mean of the two per-class recalls, and
the multi-class task score is the macro recall over classes that have examples.
Verified against their own file: alert (93.37+77.63)/2 = 85.50, matching.

    ../../pipelines/representation/.venv-birdnet/bin/python compare_crowtools.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import recall_score
from sklearn.model_selection import StratifiedGroupKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
RESULTS = HERE / "comparison.json"

# crow-tools' own constants — classifier/dataset.py
THEIR_SPLIT_FRACTION = 0.88
THEIR_SEED = 18202

FLAGS = ["alert", "begging", "softSong", "rattle", "mob"]

# classifier/RESULTS.txt, transcribed. Their validation set is 468 samples drawn
# from 3,894 labels; ours is a different subset (see `caveats` in the output).
THEIRS = {
    "alert":    {"accuracy": 0.9081, "neg_recall": 0.9337, "pos_recall": 0.7763,
                 "balanced": 0.8550, "n_pos": 76, "n_val": 468},
    "begging":  {"accuracy": 0.9615, "neg_recall": 0.9811, "pos_recall": 0.7778,
                 "balanced": 0.8794, "n_pos": 45, "n_val": 468},
    "softSong": {"accuracy": 0.9402, "neg_recall": 0.9718, "pos_recall": 0.7821,
                 "balanced": 0.8769, "n_pos": 78, "n_val": 468},
    "rattle":   {"accuracy": 0.9551, "neg_recall": 0.9694, "pos_recall": 0.8816,
                 "balanced": 0.9255, "n_pos": 76, "n_val": 468},
    "mob":      {"accuracy": 0.8868, "neg_recall": 0.9500, "pos_recall": 0.6136,
                 "balanced": 0.7818, "n_pos": 88, "n_val": 468},
}


def clf():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )


def load_pool():
    """Every embedded segment, call-bearing and garbage alike, with its 5 flags.

    crow-tools trains on all 3,894 reviewed labels including the 1,245 with
    crowCount=0, which are negatives for every call-type flag. Matching that pool
    matters: scoring only the call-bearing rows would raise every prevalence and
    flatter both sides. A segment with no CORE label has all six FLAG_TO_CORE
    flags false by construction, so the garbage rows are known negatives without
    needing their flag dicts re-read.
    """
    keyed = np.load(OUT / "crowtools_keyed.npz", allow_pickle=True)
    flags_by_key = {r["key"]: r["flags"]
                    for r in json.loads((OUT / "crowtools_flags.json").read_text())}
    X = [keyed["X"]]
    groups = [keyed["groups"]]
    y = {f: [np.array([1 if flags_by_key[f"{g}-{s}"].get(f) else 0
                       for g, s in zip(keyed["groups"], keyed["starts"])])]
         for f in FLAGS}
    asked = {f: [np.array([f in flags_by_key[f"{g}-{s}"]
                           for g, s in zip(keyed["groups"], keyed["starts"])])]
             for f in FLAGS}

    garbage = OUT / "garbage.npz"
    if garbage.exists():
        g = np.load(garbage, allow_pickle=True)
        X.append(g["X"])
        groups.append(g["groups"])
        n = len(g["X"])
        for f in FLAGS:
            y[f].append(np.zeros(n, dtype=int))
            asked[f].append(np.ones(n, dtype=bool))

    return (np.vstack(X), np.concatenate(groups),
            {f: np.concatenate(v) for f, v in y.items()},
            {f: np.concatenate(v) for f, v in asked.items()})


def report(y_true, y_pred):
    """Their metric set, computed their way."""
    neg = recall_score(y_true, y_pred, pos_label=0, zero_division=0)
    pos = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    return {"accuracy": float((y_pred == y_true).mean()),
            "neg_recall": float(neg), "pos_recall": float(pos),
            "balanced": float((neg + pos) / 2)}


def their_protocol(X, y, seed=THEIR_SEED):
    """Segment-level 88/12, the way classifier/dataset.py splits — recording ignored."""
    idx = np.arange(len(y))
    tr, te = train_test_split(idx, train_size=THEIR_SPLIT_FRACTION,
                              random_state=seed, shuffle=True)
    if len(set(y[tr])) < 2:
        return None
    pred = clf().fit(X[tr], y[tr]).predict(X[te])
    out = report(y[te], pred)
    out["n_val"] = int(len(te))
    out["n_pos_val"] = int(y[te].sum())
    return out


def our_protocol(X, y, groups, folds=5, seed=0):
    """Recording-grouped 5-fold — a recording never spans the split."""
    if y.sum() < folds or len(set(groups)) < folds:
        return None
    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    pred = np.zeros(len(y), dtype=int)
    for tr, te in cv.split(X, y, groups):
        if len(set(y[tr])) < 2:
            return None
        pred[te] = clf().fit(X[tr], y[tr]).predict(X[te])
    out = report(y, pred)
    out["n_val"] = int(len(y))
    out["n_pos_val"] = int(y.sum())
    return out


def main():
    X, groups, Y, ASKED = load_pool()
    print(f"pool: {len(X)} segments over {len(set(groups))} recordings", flush=True)

    result = {
        "pool": {"n_segments": int(len(X)),
                 "n_recordings": int(len(set(groups))),
                 "backbone": "birdnet_pooled_mean_std_max (3072-d)",
                 "head": "logistic regression, class_weight=balanced"},
        "their_setup": {"backbone": "AVES aves-base-bio, 768-d mean-pooled, 8 kHz",
                        "head": "240K-param MLP, 8 heads on a shared 237-d trunk",
                        "split": "segment-level 88/12, seed 18202",
                        "n_labels": 3894, "n_val": 468},
        "caveats": [
            "Their RESULTS.txt was produced on 3,894 labels; the committed "
            "all-public dataset now holds 3,162 and only 2,910 of those are "
            "embedded here (2,338 call-bearing with audio + 572 garbage). The "
            "rows are therefore not identical and prevalences differ slightly.",
            "Their numbers come from the same 12% used for checkpoint selection "
            "and for Optuna's objective across 60 trials, with the random seed "
            "itself a searched hyperparameter. Ours is a plain fit with no "
            "selection against the validation set at all, so the comparison is "
            "generous to them on top of the split.",
            "Their head is multi-task and oversamples positives by duplication "
            "(rattle x4, alert x3, mob x1); ours is a single-task logreg with "
            "class_weight=balanced. Head and backbone are not separated here.",
        ],
        "flags": {},
    }

    for flag in FLAGS:
        asked = ASKED[flag]
        Xa, ya, ga = X[asked], Y[flag][asked], groups[asked]
        theirs = THEIRS[flag]

        same_protocol = their_protocol(Xa, ya)
        grouped = our_protocol(Xa, ya, ga)
        if same_protocol is None or grouped is None:
            continue

        result["flags"][flag] = {
            "n_asked": int(asked.sum()),
            "n_positive": int(ya.sum()),
            "prevalence": float(ya.mean()),
            "crowtools_reported": theirs,
            "ours_their_protocol": same_protocol,
            "ours_grouped_protocol": grouped,
            "backbone_delta_balanced": float(same_protocol["balanced"]
                                             - theirs["balanced"]),
            "leakage_cost_balanced": float(same_protocol["balanced"]
                                           - grouped["balanced"]),
        }
        print(f"{flag:9s} theirs={theirs['balanced']:.3f}  "
              f"ours@theirs={same_protocol['balanced']:.3f}  "
              f"ours@grouped={grouped['balanced']:.3f}", flush=True)

    rows = result["flags"].values()
    if rows:
        result["summary"] = {
            "mean_balanced_crowtools": float(np.mean(
                [r["crowtools_reported"]["balanced"] for r in rows])),
            "mean_balanced_ours_their_protocol": float(np.mean(
                [r["ours_their_protocol"]["balanced"] for r in rows])),
            "mean_balanced_ours_grouped": float(np.mean(
                [r["ours_grouped_protocol"]["balanced"] for r in rows])),
            "mean_leakage_cost": float(np.mean(
                [r["leakage_cost_balanced"] for r in rows])),
        }
    RESULTS.write_text(json.dumps(result, indent=2))
    print("\nwrote comparison.json")


if __name__ == "__main__":
    main()
