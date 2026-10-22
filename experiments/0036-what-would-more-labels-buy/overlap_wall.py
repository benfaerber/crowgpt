#!/usr/bin/env python3
"""How much does the pipeline lose when more than one crow is calling?

0025 found the wall from one side: all of Perch's gain over BirdNET is on
single-crow segments (0.848 -> 0.875), and at crowCount>=2 Perch is slightly
*worse* (0.775 -> 0.747). A better backbone does not separate two crows calling
over each other.

This measures the same wall per class rather than in aggregate, because the
classes are not equally exposed to it. crow-tools' `mob` carries 231 of its 738
positives at crowCount=4 — mobbing is partly a crowd phenomenon — so "mob is
hard" and "overlap is hard" may be the same sentence.

Method: one model, fitted once under recording-grouped CV over the whole pool,
then the SAME out-of-fold predictions scored separately within each crowCount
stratum. Splitting the evaluation rather than the training is the point: it asks
what the shipped model does on overlapping audio, not what a model trained only
on overlapping audio could do.

    ../../pipelines/representation/.venv-birdnet/bin/python overlap_wall.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
FLAGS = ["alert", "begging", "softSong", "rattle", "mob"]
CORE = ["alarm call", "begging", "call", "song"]


def clf():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(max_iter=2000, class_weight="balanced"))


def load():
    keyed = np.load(OUT / "crowtools_keyed.npz", allow_pickle=True)
    flags = {r["key"]: r["flags"]
             for r in json.loads((OUT / "crowtools_flags.json").read_text())}
    keys = [f"{g}-{s}" for g, s in zip(keyed["groups"], keyed["starts"])]
    return (keyed["X"], keyed["groups"], [sorted(v) for v in keyed["labels"]],
            [flags[k] for k in keys])


def strata(counts):
    """crowCount 1 against 2+, which is the only split the corpus supports.

    crowCount 3 has zero examples in crow-tools' whole corpus and 4 means
    'crowd', so 2 and 4 are pooled rather than treated as an ordered scale.
    """
    return {"one_crow": counts == 1, "two_or_more": counts >= 2}


def main():
    X, groups, labels, flags = load()
    counts = np.array([int(f.get("crowCount") or 0) for f in flags])
    result = {"pool": {"n": int(len(X)),
                       "crowCount_distribution":
                           {str(k): int(v) for k, v in sorted(Counter(counts).items())}},
              "note": ("one model, recording-grouped out-of-fold predictions, "
                       "scored within each stratum — the evaluation is split, "
                       "not the training"),
              "core_multiclass": {}, "flags": {}}

    # --- CORE multiclass, single-label rows, macro-F1 per stratum ---------
    single = np.array([len(v) == 1 for v in labels])
    ys = np.array([v[0] for v in np.array(labels, dtype=object)[single]])
    Xs, gs, cs = X[single], groups[single], counts[single]
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    pred = np.empty(len(ys), dtype=object)
    for tr, te in cv.split(Xs, ys, gs):
        pred[te] = clf().fit(Xs[tr], ys[tr]).predict(Xs[te])
    for name, mask in strata(cs).items():
        if mask.sum() < 30:
            continue
        result["core_multiclass"][name] = {
            "n": int(mask.sum()),
            "macro_f1": float(f1_score(ys[mask], pred[mask], average="macro",
                                       zero_division=0)),
            "accuracy": float((pred[mask] == ys[mask]).mean()),
            "class_mix": {k: int(v) for k, v in Counter(ys[mask]).most_common()},
        }

    # --- per raw flag, AP and positive recall per stratum -----------------
    for flag in FLAGS:
        asked = np.array([flag in f for f in flags])
        y = np.array([1 if f.get(flag) else 0 for f, a in zip(flags, asked) if a])
        Xa, ga, ca = X[asked], groups[asked], counts[asked]
        if y.sum() < 25:
            continue
        proba = np.zeros(len(y))
        pr = np.zeros(len(y), dtype=int)
        for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True,
                                           random_state=0).split(Xa, y, ga):
            m = clf().fit(Xa[tr], y[tr])
            proba[te] = m.predict_proba(Xa[te])[:, 1]
            pr[te] = m.predict(Xa[te])
        entry = {"n_positive_total": int(y.sum())}
        for name, mask in strata(ca).items():
            if mask.sum() < 30 or y[mask].sum() < 5 or y[mask].sum() == mask.sum():
                continue
            neg = recall_score(y[mask], pr[mask], pos_label=0, zero_division=0)
            pos = recall_score(y[mask], pr[mask], pos_label=1, zero_division=0)
            entry[name] = {
                "n": int(mask.sum()),
                "n_positive": int(y[mask].sum()),
                "prevalence": float(y[mask].mean()),
                "average_precision": float(average_precision_score(y[mask], proba[mask])),
                "pos_recall": float(pos),
                "balanced_accuracy": float((neg + pos) / 2),
            }
        if "one_crow" in entry and "two_or_more" in entry:
            entry["ap_drop"] = float(entry["one_crow"]["average_precision"]
                                     - entry["two_or_more"]["average_precision"])
        result["flags"][flag] = entry
        print(f"{flag:9s} " + "  ".join(
            f"{k}: AP={v['average_precision']:.3f} prev={v['prevalence']:.2f}"
            for k, v in entry.items() if isinstance(v, dict)), flush=True)

    (HERE / "overlap.json").write_text(json.dumps(result, indent=2))
    print("\ncore:", json.dumps(result["core_multiclass"], indent=1))
    print("wrote overlap.json")


if __name__ == "__main__":
    main()
