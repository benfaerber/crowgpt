#!/usr/bin/env python3
"""Is recording-grouped CV strict enough, or is the recordist the real group?

CrowGPT groups CV by recording, which is already stricter than crow-tools'
segment-level split (worth +0.043 balanced accuracy, see compare_crowtools.py).
But a recordist contributes many recordings with the same microphone, the same
back garden and often the same individual birds, and the archive's library.csv
carries a **Recordist** column on 100% of rows that nothing in this project has
ever read.

If macro-F1 drops again when whole recordists are held out, then every number
this project reports — including all of 0036 — is optimistic by that much, and
the grouping key should change.

Also measures the overlap wall's prevalence correction: `mob` scores AP 0.867 on
multi-crow audio against 0.551 on single-crow, but its prevalence there is 0.65
against 0.19, so the raw APs say the opposite of what lift over chance says.

    ../../pipelines/representation/.venv-birdnet/bin/python recordist_split.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
FORK = Path("/home/ben/Code/crow-tools")
LIBS = FORK / ".cache" / "libraries"
FLAGS = ["alert", "begging", "softSong", "rattle", "mob"]


def clf():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(max_iter=2000, class_weight="balanced"))


def recordists():
    """recording id -> recordist, from both libraries' metadata."""
    out = {}
    for lib, col in (("library-1", "Recordist"), ("library-2", "Recordist")):
        path = LIBS / lib / "library.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                rid = (row.get("ML Catalog Number") or "").strip()
                who = (row.get(col) or "").strip()
                if rid and who:
                    out[rid] = f"{lib}:{who}"
    return out


def load():
    keyed = np.load(OUT / "crowtools_keyed.npz", allow_pickle=True)
    flags = {r["key"]: r["flags"]
             for r in json.loads((OUT / "crowtools_flags.json").read_text())}
    keys = [f"{g}-{s}" for g, s in zip(keyed["groups"], keyed["starts"])]
    return (keyed["X"], np.array(keyed["groups"]),
            [sorted(v) for v in keyed["labels"]], [flags[k] for k in keys])


def grouped_macro_f1(X, y, groups, seed=0):
    counts = Counter(y)
    n = min(5, min(counts.values()), len(set(groups)))
    if n < 2:
        return None
    cv = StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=seed)
    pred = np.empty(len(y), dtype=object)
    for tr, te in cv.split(X, y, groups):
        pred[te] = clf().fit(X[tr], y[tr]).predict(X[te])
    return float(f1_score(y, pred, average="macro", zero_division=0))


def grouped_ap(X, y, groups, seed=0):
    if y.sum() < 5:
        return None
    n = min(5, int(y.sum()), len(set(groups)))
    if n < 2:
        return None
    cv = StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=seed)
    p = np.zeros(len(y))
    for tr, te in cv.split(X, y, groups):
        if len(set(y[tr])) < 2:
            return None
        p[te] = clf().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return float(average_precision_score(y, p))


def main():
    X, groups, labels, flags = load()
    who = recordists()
    by_rec = np.array([who.get(g, f"UNKNOWN:{g}") for g in groups])
    known = np.array([g in who for g in groups])

    result = {
        "coverage": {
            "segments": int(len(groups)),
            "recordings": int(len(set(groups))),
            "segments_with_a_recordist": int(known.sum()),
            "distinct_recordists": int(len(set(by_rec[known]))),
            "recordings_per_recordist_mean": float(
                len(set(groups[known])) / max(1, len(set(by_rec[known])))),
        },
        "note": ("recording-grouped against recordist-grouped, same rows, same "
                 "head, same folds — only the grouping key changes"),
    }
    top = Counter(by_rec[known]).most_common(5)
    result["coverage"]["biggest_recordists"] = [
        {"recordist": k, "segments": int(v)} for k, v in top]
    print(json.dumps(result["coverage"], indent=1), flush=True)

    single = np.array([len(v) == 1 for v in labels]) & known
    ys = np.array([v[0] for v in np.array(labels, dtype=object)[single]])
    Xs, gs, rs = X[single], groups[single], by_rec[single]

    result["core_macro_f1"] = {
        "by_recording": grouped_macro_f1(Xs, ys, gs),
        "by_recordist": grouped_macro_f1(Xs, ys, rs),
    }
    a, b = result["core_macro_f1"]["by_recording"], result["core_macro_f1"]["by_recordist"]
    if a and b:
        result["core_macro_f1"]["cost_of_the_stricter_group"] = float(a - b)
    print("CORE macro-F1  by_recording=%.3f  by_recordist=%.3f" % (a, b), flush=True)

    result["flags"] = {}
    for flag in FLAGS:
        asked = np.array([flag in f for f in flags]) & known
        y = np.array([1 if f.get(flag) else 0
                      for f, k in zip(flags, asked) if k])
        Xa, ga, ra = X[asked], groups[asked], by_rec[asked]
        rec_ap, who_ap = grouped_ap(Xa, y, ga), grouped_ap(Xa, y, ra)
        if rec_ap is None or who_ap is None:
            continue
        prev = float(y.mean())
        result["flags"][flag] = {
            "prevalence": prev,
            "ap_by_recording": rec_ap, "ap_by_recordist": who_ap,
            "cost_of_the_stricter_group": float(rec_ap - who_ap),
            "lift_over_chance_by_recordist": float(who_ap / prev),
        }
        print("%-9s AP by_recording=%.3f  by_recordist=%.3f  (prev %.2f)"
              % (flag, rec_ap, who_ap, prev), flush=True)

    # --- the overlap wall, read as lift over chance rather than raw AP ----
    overlap = HERE / "overlap.json"
    if overlap.exists():
        o = json.loads(overlap.read_text())
        corrected = {}
        for flag, v in o.get("flags", {}).items():
            row = {}
            for stratum in ("one_crow", "two_or_more"):
                if stratum in v:
                    s = v[stratum]
                    row[stratum] = {
                        "average_precision": s["average_precision"],
                        "prevalence": s["prevalence"],
                        "lift_over_chance": float(s["average_precision"]
                                                  / s["prevalence"]),
                    }
            if len(row) == 2:
                row["lift_drop"] = float(row["one_crow"]["lift_over_chance"]
                                         - row["two_or_more"]["lift_over_chance"])
                corrected[flag] = row
        result["overlap_wall_lift_corrected"] = {
            "note": ("AP must be read against prevalence. mob's AP RISES with "
                     "more crows (0.551 -> 0.867) while its prevalence rises "
                     "0.19 -> 0.65, so its lift over chance FALLS — mobbing "
                     "detection is substantially crowd detection."),
            "flags": corrected,
        }

    (HERE / "recordist.json").write_text(json.dumps(result, indent=2))
    print("\nwrote recordist.json")


if __name__ == "__main__":
    main()
