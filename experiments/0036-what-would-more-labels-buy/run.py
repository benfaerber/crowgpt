#!/usr/bin/env python3
"""0036 — what would more manual labelling buy?

Six arms, each with a decision attached. Everything reuses the cached 3,072-d
pooled BirdNET features unless it says otherwise, and every split is grouped by
recording, so the numbers land next to 0012 and 0025 rather than beside them.

  A  learning curve over archive labels, subsampled BY RECORDING, with a power
     law fitted to it and extrapolated — bounded, because a fit over one decade
     is not evidence about three
  B  the same curve for `mob` and `rattle` in average precision, which is where
     0012 found mob stops being shippable
  C  does labelling ORDER matter — random vs cluster-stratified vs uncertainty,
     at matched budget. The arm that writes the pipeline's spec
  D  the transfer smoke test: the shipped head against Ben's own labelled spans
  E1 does crow-tools' `quality` field earn its keep, against a size-matched
     random drop so quality is not confounded with quantity
  E2 does an explicit garbage class cut false positives
  E3 do crow-tools' auxiliary heads (crowCount/crowAge/quality) regularise

Arms D and E2 need `prepare.py` to have run first; both are skipped with a note
rather than a crash if their cache is absent.

    ../../pipelines/representation/.venv-birdnet/bin/python run.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
RESULTS = HERE / "results.json"
CACHE = REPO / "pipelines" / "ingest" / "results" / "pooled_embeddings_crowtools_all-public.npz"

sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
sys.path.insert(0, str(REPO / "pipelines" / "training"))

CORE = ["alarm call", "begging", "call", "song"]
SEEDS = [0, 1, 2]
FRACTIONS = [0.08, 0.15, 0.25, 0.40, 0.55, 0.70, 0.85, 1.00]
FOLDS = 5

_state: dict = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def progress(msg):
    print(msg, flush=True)


def save(key, value):
    _state[key] = value
    RESULTS.write_text(json.dumps(_state, indent=2, default=float))


def clf():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

class Row:
    """One labelled segment: its features, its CORE labels, and its raw flags."""

    __slots__ = ("flags",)

    def __init__(self, flags):
        self.flags = flags


def load_aligned():
    """Keyed feature rows with their raw crow-tools flags attached.

    Deliberately NOT the shipped cache. `pooled_embeddings_crowtools_all-public.npz`
    carries no segment key, so recovering raw flags from it means matching rows to
    segments by position within a file. That was sound when 0012 did it and is not
    sound now — the cache holds 2,494 rows against 2,339 segments that still have
    audio, 98 files disagree on count, and at least one file's cached label order
    is a permutation of the corpus order. prepare.py rebuilds the features with the
    key on the row, so this function does a dictionary lookup instead of trusting
    an ordering. See that file's docstring.
    """
    keyed = OUT / "crowtools_keyed.npz"
    flagfile = OUT / "crowtools_flags.json"
    if not (keyed.exists() and flagfile.exists()):
        raise SystemExit("run prepare.py first — it builds results/crowtools_keyed.npz")

    d = np.load(keyed, allow_pickle=True)
    X, groups, starts = d["X"], d["groups"], d["starts"]
    Y = [sorted(v) for v in d["labels"]]

    by_key = {r["key"]: r["flags"] for r in json.loads(flagfile.read_text())}
    segments = []
    for g, s in zip(groups, starts):
        flags = by_key.get(f"{g}-{s}")
        if flags is None:
            raise SystemExit(f"row {g}-{s} has no flags — rebuild with prepare.py")
        segments.append(Row(flags))

    # The join is now by key, so the only thing left to check is that the labels
    # the features were built from still agree with the flags stored beside them.
    from corpus import LabelCorpus
    core_of = LabelCorpus.core_labels
    for labs, seg in zip(Y, segments):
        if sorted(core_of(seg.flags)) != labs:
            raise SystemExit(f"flags {seg.flags} do not yield {labs} — rebuild")
    return X, Y, np.array(groups), segments


def single_label(X, Y, groups, segments):
    """Rows carrying exactly one CORE label — what the shipped head trains on."""
    m = np.array([len(s) == 1 for s in Y])
    y = np.array([s[0] for s in np.array(Y, dtype=object)[m]])
    return X[m], y, groups[m], [s for s, keep in zip(segments, m) if keep]


def sample_recordings(groups, frac, seed):
    """A row mask keeping `frac` of the RECORDINGS — never a sample of rows.

    Sampling rows would put the same recording on both sides of a later split
    and measure the curve of a leak instead of the curve of the labels.
    """
    recs = np.array(sorted(set(groups)))
    rng = np.random.default_rng(seed)
    n = max(2, int(round(len(recs) * frac)))
    chosen = set(rng.choice(recs, size=n, replace=False).tolist())
    return np.array([g in chosen for g in groups])


def grouped_predict(X, y, groups, folds=FOLDS, seed=0):
    """Out-of-fold probabilities, recording-grouped. None if it cannot be split."""
    classes = sorted(set(y))
    counts = Counter(y)
    if len(classes) < 2 or min(counts.values()) < folds:
        return None, None
    n_splits = min(folds, min(counts.values()), len(set(groups)))
    if n_splits < 2:
        return None, None
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    proba = np.zeros((len(y), len(classes)))
    pred = np.empty(len(y), dtype=object)
    try:
        for tr, te in cv.split(X, y, groups):
            if len(set(y[tr])) < 2:
                return None, None
            model = clf().fit(X[tr], y[tr])
            p = model.predict_proba(X[te])
            for j, c in enumerate(model.classes_):
                proba[te, classes.index(c)] = p[:, j]
            pred[te] = model.predict(X[te])
    except ValueError:
        return None, None
    return pred, (classes, proba)


def score(y, pred, classes_proba):
    classes, proba = classes_proba
    out = {"macro_f1": float(f1_score(y, pred, average="macro")),
           "accuracy": float((pred == y).mean()), "per_class_ap": {}}
    for j, c in enumerate(classes):
        binary = (y == c).astype(int)
        if 0 < binary.sum() < len(binary):
            out["per_class_ap"][c] = float(average_precision_score(binary, proba[:, j]))
    return out


# --------------------------------------------------------------------------
# A — the learning curve
# --------------------------------------------------------------------------

def power_law_fit(ns, scores):
    """f1(n) = c - a * n**(-b), fitted on the means. Returns None if it will not fit."""
    try:
        from scipy.optimize import curve_fit
    except Exception:  # noqa: BLE001
        return None
    ns = np.asarray(ns, dtype=float)
    ys = np.asarray(scores, dtype=float)
    if len(ns) < 4:
        return None

    def f(n, a, b, c):
        return c - a * np.power(n, -b)

    try:
        popt, _ = curve_fit(f, ns, ys, p0=[1.0, 0.5, 0.9],
                            bounds=([0, 0.01, 0.0], [50, 3.0, 1.0]), maxfev=20000)
    except Exception:  # noqa: BLE001
        return None
    a, b, c = (float(v) for v in popt)
    resid = ys - f(ns, a, b, c)
    n_max = float(ns.max())
    return {
        "a": a, "b": b, "ceiling_c": c,
        "rmse": float(np.sqrt((resid ** 2).mean())),
        "at_1x": float(f(n_max, a, b, c)),
        "at_2x": float(f(n_max * 2, a, b, c)),
        "at_4x": float(f(n_max * 4, a, b, c)),
        "gain_doubling": float(f(n_max * 2, a, b, c) - f(n_max, a, b, c)),
        "gain_4x": float(f(n_max * 4, a, b, c) - f(n_max, a, b, c)),
        "caveat": ("fitted over one decade of n; the 2x figure is the only "
                   "extrapolation worth quoting and the 4x is indicative"),
    }


def arm_a(X, y, groups):
    progress("arm A — learning curve over archive labels")
    curve = []
    for frac in FRACTIONS:
        runs = []
        for seed in SEEDS:
            m = sample_recordings(groups, frac, seed)
            pred, cp = grouped_predict(X[m], y[m], groups[m], seed=seed)
            if pred is None:
                continue
            runs.append(score(y[m], pred, cp))
        if not runs:
            continue
        m0 = sample_recordings(groups, frac, SEEDS[0])
        point = {
            "fraction": frac,
            "n_segments": int(m0.sum()),
            "n_recordings": int(len(set(groups[m0]))),
            "macro_f1_mean": float(np.mean([r["macro_f1"] for r in runs])),
            "macro_f1_sd": float(np.std([r["macro_f1"] for r in runs])),
            "accuracy_mean": float(np.mean([r["accuracy"] for r in runs])),
            "per_class_ap_mean": {
                c: float(np.mean([r["per_class_ap"][c] for r in runs
                                  if c in r["per_class_ap"]]))
                for c in CORE
                if any(c in r["per_class_ap"] for r in runs)
            },
            "seeds": len(runs),
        }
        curve.append(point)
        progress(f"arm A — n={point['n_segments']:4d} "
                 f"macroF1={point['macro_f1_mean']:.3f}")

    result = {"curve": curve,
              "fit_macro_f1": power_law_fit([p["n_segments"] for p in curve],
                                            [p["macro_f1_mean"] for p in curve])}
    for c in CORE:
        pts = [(p["n_segments"], p["per_class_ap_mean"][c]) for p in curve
               if c in p["per_class_ap_mean"]]
        if len(pts) >= 4:
            result.setdefault("fit_per_class_ap", {})[c] = power_law_fit(
                [n for n, _ in pts], [v for _, v in pts])
    save("A_learning_curve", result)


# --------------------------------------------------------------------------
# B — mob and rattle, in average precision
# --------------------------------------------------------------------------

def flag_curve(X, groups, segments, flag):
    """Binary AP curve for one raw crow-tools flag, restricted to where it was ASKED.

    0012's trap: `scold` and `grief` were added mid-labelling, so on many
    segments the key is absent rather than False. Reading a missing key as a
    negative is what scored scold 0.581 against a 0.947 control.
    """
    asked = np.array([flag in s.flags for s in segments])
    Xa, ga = X[asked], groups[asked]
    ya = np.array([1 if s.flags.get(flag) else 0
                   for s, a in zip(segments, asked) if a])
    curve = []
    for frac in FRACTIONS:
        aps, aucs = [], []
        for seed in SEEDS:
            m = sample_recordings(ga, frac, seed)
            if ya[m].sum() < 8 or ya[m].sum() == m.sum():
                continue
            n_splits = min(FOLDS, int(ya[m].sum()), len(set(ga[m])))
            if n_splits < 2:
                continue
            cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True,
                                      random_state=seed)
            p = np.zeros(int(m.sum()))
            Xm, ym, gm = Xa[m], ya[m], ga[m]
            ok = True
            try:
                for tr, te in cv.split(Xm, ym, gm):
                    if len(set(ym[tr])) < 2:
                        ok = False
                        break
                    p[te] = clf().fit(Xm[tr], ym[tr]).predict_proba(Xm[te])[:, 1]
            except ValueError:
                ok = False
            if not ok:
                continue
            aps.append(average_precision_score(ym, p))
            aucs.append(roc_auc_score(ym, p))
        if not aps:
            continue
        m0 = sample_recordings(ga, frac, SEEDS[0])
        curve.append({
            "fraction": frac,
            "n_segments": int(m0.sum()),
            "n_positives": int(ya[m0].sum()),
            "prevalence": float(ya[m0].mean()),
            "ap_mean": float(np.mean(aps)), "ap_sd": float(np.std(aps)),
            "auc_mean": float(np.mean(aucs)),
            "seeds": len(aps),
        })
        progress(f"arm B — {flag} n={curve[-1]['n_segments']:4d} "
                 f"AP={curve[-1]['ap_mean']:.3f}")
    return curve


def labels_to_reach(fit, target, n_now):
    """How many segments the fit says a target AP needs. None if unreachable."""
    if not fit or fit["ceiling_c"] <= target:
        return None
    a, b, c = fit["a"], fit["b"], fit["ceiling_c"]
    need = (a / (c - target)) ** (1.0 / b)
    return {"target": target, "n_needed": float(need),
            "multiple_of_current": float(need / n_now)}


def arm_b(X, groups, segments):
    progress("arm B — mob and rattle in average precision")
    out = {}
    for flag in ("mob", "rattle", "alert"):
        curve = flag_curve(X, groups, segments, flag)
        if not curve:
            continue
        fit = power_law_fit([p["n_segments"] for p in curve],
                            [p["ap_mean"] for p in curve])
        n_now = curve[-1]["n_segments"]
        out[flag] = {
            "curve": curve, "fit_ap": fit,
            "to_reach_0.80": labels_to_reach(fit, 0.80, n_now),
            "to_reach_0.85": labels_to_reach(fit, 0.85, n_now),
        }
        save("B_flag_curves", out)


# --------------------------------------------------------------------------
# C — does labelling order matter
# --------------------------------------------------------------------------

def arm_c(X, y, groups, segments):
    progress("arm C — acquisition strategy at matched budget")
    clusters = np.array([int(s.flags.get("cluster", -1)) for s in segments])
    budgets = [100, 200, 400, 600, 900, 1200, 1500]
    out = {"budgets": budgets, "strategies": {}}

    for strategy in ("random", "cluster_stratified", "uncertainty"):
        rows = []
        for seed in SEEDS:
            # A fixed held-out 25% of RECORDINGS. Acquisition only ever sees the pool.
            gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
            pool_i, test_i = next(gss.split(X, y, groups))
            Xp, yp, cp = X[pool_i], y[pool_i], clusters[pool_i]
            Xt, yt = X[test_i], y[test_i]
            rng = np.random.default_rng(seed)

            order = None
            if strategy == "random":
                order = rng.permutation(len(yp))
            elif strategy == "cluster_stratified":
                by_c = defaultdict(list)
                for i in rng.permutation(len(yp)):
                    by_c[cp[i]].append(i)
                queues = [by_c[k] for k in sorted(by_c)]
                order = []
                while any(queues):
                    for q in queues:
                        if q:
                            order.append(q.pop())
                order = np.array(order)

            per_budget = []
            acquired = None
            for b in budgets:
                if b > len(yp):
                    break
                if strategy == "uncertainty":
                    if acquired is None:
                        acquired = list(rng.permutation(len(yp))[:budgets[0]])
                    else:
                        remaining = np.setdiff1d(np.arange(len(yp)), acquired)
                        need = b - len(acquired)
                        if len(set(yp[acquired])) >= 2 and need > 0:
                            model = clf().fit(Xp[acquired], yp[acquired])
                            p = model.predict_proba(Xp[remaining])
                            srt = np.sort(p, axis=1)
                            margin = srt[:, -1] - srt[:, -2]
                            acquired += list(remaining[np.argsort(margin)[:need]])
                        else:
                            acquired += list(rng.permutation(remaining)[:need])
                    idx = np.array(acquired)
                else:
                    idx = order[:b]
                if len(set(yp[idx])) < 2:
                    continue
                model = clf().fit(Xp[idx], yp[idx])
                pred = model.predict(Xt)
                per_budget.append({
                    "budget": int(b),
                    "macro_f1": float(f1_score(yt, pred, average="macro")),
                    "accuracy": float((pred == yt).mean()),
                    "classes_seen": int(len(set(yp[idx]))),
                })
            rows.append(per_budget)

        merged = []
        for k, b in enumerate(budgets):
            vals = [r[k]["macro_f1"] for r in rows if len(r) > k]
            if vals:
                merged.append({"budget": b, "macro_f1_mean": float(np.mean(vals)),
                               "macro_f1_sd": float(np.std(vals)),
                               "seeds": len(vals)})
        out["strategies"][strategy] = merged
        progress(f"arm C — {strategy}: " +
                 ", ".join(f"{m['budget']}:{m['macro_f1_mean']:.3f}" for m in merged))
        save("C_acquisition", out)

    # The headline: labels each strategy needs to match random-at-full-budget.
    rand = {m["budget"]: m["macro_f1_mean"] for m in out["strategies"]["random"]}
    if rand:
        target = max(rand.values())
        summary = {"target_macro_f1": target,
                   "random_labels_to_target": min(
                       (b for b, v in rand.items() if v >= target), default=None)}
        for name, ms in out["strategies"].items():
            hit = [m["budget"] for m in ms if m["macro_f1_mean"] >= target]
            summary[f"{name}_labels_to_target"] = min(hit) if hit else None
        out["summary"] = summary
    save("C_acquisition", out)


# --------------------------------------------------------------------------
# D — the transfer smoke test
# --------------------------------------------------------------------------

def arm_d():
    cache = OUT / "field_labels.npz"
    if not cache.exists():
        save("D_field_transfer", {"skipped": "run prepare.py first"})
        progress("arm D — skipped, no field cache")
        return
    import joblib

    progress("arm D — shipped head against Ben's own labelled spans")
    d = np.load(cache, allow_pickle=True)
    bundle = joblib.load(REPO / "pipelines" / "training" / "models" /
                         "american-crow" / "calltype_clf.joblib")
    head, classes = bundle["model"], bundle["classes"]

    y_all = d["y"]
    trainable = np.array([c in classes for c in y_all])
    kept = d["keep"].astype(bool)

    out = {"n_labels_embedded": int(len(y_all)),
           "n_trainable_class": int(trainable.sum()),
           "n_on_kept_captures": int((trainable & kept).sum()),
           "note": ("top-1 of a one-vs-rest head is what the app shows first, but "
                    "its probabilities do not sum to one — this is the app's "
                    "displayed answer, not a calibrated confidence"),
           "caveat": ("n is tens of labels over 13 captures. This detects a "
                      "catastrophic domain gap, as 0018 found on bouts; it cannot "
                      "measure a subtle one.")}

    for pooling in ("X_span", "X_win"):
        for scope, mask in (("all_trainable", trainable),
                            ("kept_only", trainable & kept)):
            if mask.sum() < 5:
                continue
            X = d[pooling][mask]
            y = y_all[mask]
            proba = head.predict_proba(X)
            top = np.array([classes[i] for i in proba.argmax(1)])
            counts = Counter(y)
            majority = counts.most_common(1)[0]
            confusion = {c: dict(Counter(top[y == c]).most_common())
                         for c in sorted(set(y))}
            out[f"{pooling}__{scope}"] = {
                "n": int(mask.sum()),
                "top1_accuracy": float((top == y).mean()),
                "constant_baseline": float(majority[1] / mask.sum()),
                "constant_class": majority[0],
                "beats_constant": bool((top == y).mean() > majority[1] / mask.sum()),
                "predicted_distribution": dict(Counter(top).most_common()),
                "confusion_true_to_predicted": confusion,
            }
            progress(f"arm D — {pooling} {scope}: top1="
                     f"{out[f'{pooling}__{scope}']['top1_accuracy']:.3f} "
                     f"vs constant {majority[1] / mask.sum():.3f}")
    save("D_field_transfer", out)


# --------------------------------------------------------------------------
# E1 — does `quality` earn its keep
# --------------------------------------------------------------------------

def arm_e1(X, y, groups, segments):
    progress("arm E1 — quality filtering vs a size-matched random drop")
    quality = np.array([int(s.flags.get("quality") or 0) for s in segments])
    good = quality >= 2
    n_drop = int((~good).sum())

    def run(mask, seed):
        pred, cp = grouped_predict(X[mask], y[mask], groups[mask], seed=seed)
        return None if pred is None else score(y[mask], pred, cp)

    out = {"n_total": int(len(y)), "n_quality_1_dropped": n_drop,
           "quality_distribution": {str(k): int(v) for k, v in
                                    sorted(Counter(quality).items())},
           "note": ("the random-drop control is the point: dropping 682 rows "
                    "changes n as well as purity, and without it a quality "
                    "'win' is indistinguishable from a size effect")}

    for name in ("all", "quality_ge_2", "random_drop_control"):
        runs = []
        for seed in SEEDS:
            if name == "all":
                mask = np.ones(len(y), bool)
            elif name == "quality_ge_2":
                mask = good
            else:
                rng = np.random.default_rng(100 + seed)
                mask = np.ones(len(y), bool)
                mask[rng.choice(len(y), size=n_drop, replace=False)] = False
            r = run(mask, seed)
            if r:
                runs.append(r)
            if name in ("all", "quality_ge_2"):
                break  # deterministic mask; one seed of CV is enough
        if runs:
            out[name] = {
                "n": int(mask.sum()),
                "macro_f1": float(np.mean([r["macro_f1"] for r in runs])),
                "per_class_ap": {c: float(np.mean([r["per_class_ap"][c] for r in runs
                                                   if c in r["per_class_ap"]]))
                                 for c in CORE},
            }
            progress(f"arm E1 — {name}: macroF1={out[name]['macro_f1']:.3f}")
    save("E1_quality_filter", out)


# --------------------------------------------------------------------------
# E2 — an explicit garbage class
# --------------------------------------------------------------------------

def arm_e2(X, y, groups):
    cache = OUT / "garbage.npz"
    if not cache.exists():
        save("E2_garbage_class", {"skipped": "run prepare.py first"})
        progress("arm E2 — skipped, no garbage cache")
        return
    progress("arm E2 — an explicit 'nothing here' class")
    g = np.load(cache, allow_pickle=True)
    Xg, gg = g["X"], g["groups"]

    Xa = np.vstack([X, Xg])
    ya = np.concatenate([y, np.array(["none"] * len(Xg))])
    ga = np.concatenate([groups, gg])

    out = {"n_call_rows": int(len(y)), "n_garbage_rows": int(len(Xg)),
           "note": ("false-positive rate is the share of garbage segments the "
                    "head assigns a call class with p>0.5 — the 4-class head has "
                    "no way to abstain, which is the whole point")}

    pred5, cp5 = grouped_predict(Xa, ya, ga, seed=0)
    if pred5 is not None:
        is_g = ya == "none"
        out["five_class"] = {
            "macro_f1_all": float(f1_score(ya, pred5, average="macro")),
            "macro_f1_core_only": float(
                f1_score(ya[~is_g], pred5[~is_g], average="macro",
                         labels=CORE, zero_division=0)),
            "garbage_correctly_rejected": float((pred5[is_g] == "none").mean()),
            "garbage_called_a_call": float((pred5[is_g] != "none").mean()),
        }

    pred4, cp4 = grouped_predict(X, y, groups, seed=0)
    if pred4 is not None and cp4 is not None:
        classes4, _ = cp4
        model = clf().fit(X, y)
        pg = model.predict_proba(Xg)
        out["four_class"] = {
            "macro_f1_core_only": float(f1_score(y, pred4, average="macro")),
            "garbage_assigned_a_call_p_gt_0.5": float((pg.max(1) > 0.5).mean()),
            "garbage_mean_top_probability": float(pg.max(1).mean()),
            "garbage_predicted_distribution": dict(
                Counter(np.array(model.classes_)[pg.argmax(1)]).most_common()),
            "caveat": ("fitted on all rows and scored on garbage it never saw; "
                       "recordings may overlap, so this is an upper bound on how "
                       "well the 4-class head copes with silence"),
        }
    save("E2_garbage_class", out)
    progress("arm E2 — done")


# --------------------------------------------------------------------------
# E3 — crow-tools' auxiliary heads
# --------------------------------------------------------------------------

def arm_e3(X, y, groups, segments):
    try:
        import torch
        import torch.nn as nn
    except Exception as ex:  # noqa: BLE001
        save("E3_multitask", {"skipped": f"torch unavailable: {ex}"})
        return
    progress("arm E3 — auxiliary heads (crowCount/crowAge/quality)")
    torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
    dev = "cpu"  # 240K params; the GPU is Ben's right now and does not need to be

    classes = sorted(set(y))
    yi = np.array([classes.index(v) for v in y])
    count = np.array([min(int(s.flags.get("crowCount") or 0), 4) for s in segments])
    age = np.array([max(0, int(s.flags.get("crowAge") or 1) - 1) for s in segments])
    qual = np.array([max(0, min(int(s.flags.get("quality") or 1) - 1, 2))
                     for s in segments])

    class Net(nn.Module):
        def __init__(self, multitask):
            super().__init__()
            self.trunk = nn.Sequential(
                nn.Linear(X.shape[1], 237), nn.BatchNorm1d(237), nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(237, 237), nn.BatchNorm1d(237), nn.ReLU(), nn.Dropout(0.3))
            self.core = nn.Linear(237, len(classes))
            self.multitask = multitask
            if multitask:
                self.count = nn.Linear(237, 5)
                self.age = nn.Linear(237, 2)
                self.qual = nn.Linear(237, 3)

        def forward(self, x):
            h = self.trunk(x)
            if not self.multitask:
                return self.core(h), None, None, None
            return self.core(h), self.count(h), self.age(h), self.qual(h)

    out = {"note": ("same trunk, same folds, same epochs — the only difference is "
                    "whether the auxiliary losses are added, which is crow-tools' "
                    "actual architectural claim")}

    for multitask in (False, True):
        f1s = []
        for seed in SEEDS:
            cv = StratifiedGroupKFold(n_splits=FOLDS, shuffle=True, random_state=seed)
            pred = np.zeros(len(yi), dtype=int)
            for tr, te in cv.split(X, yi, groups):
                mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
                Xtr = torch.tensor((X[tr] - mu) / sd, dtype=torch.float32, device=dev)
                Xte = torch.tensor((X[te] - mu) / sd, dtype=torch.float32, device=dev)
                t = {k: torch.tensor(v[tr], dtype=torch.long, device=dev)
                     for k, v in (("core", yi), ("count", count),
                                  ("age", age), ("qual", qual))}
                torch.manual_seed(seed)
                net = Net(multitask).to(dev)
                opt = torch.optim.Adam(net.parameters(), lr=1.45e-4)
                lossf = nn.CrossEntropyLoss()
                net.train()
                for _ in range(60):
                    perm = torch.randperm(len(Xtr), device=dev)
                    for i in range(0, len(perm), 64):
                        b = perm[i:i + 64]
                        if len(b) < 2:
                            continue
                        opt.zero_grad()
                        oc, ocnt, oage, oq = net(Xtr[b])
                        loss = lossf(oc, t["core"][b])
                        if multitask:
                            loss = (loss + lossf(ocnt, t["count"][b])
                                    + lossf(oage, t["age"][b])
                                    + lossf(oq, t["qual"][b]))
                        loss.backward()
                        opt.step()
                net.eval()
                with torch.no_grad():
                    pred[te] = net(Xte)[0].argmax(1).cpu().numpy()
            f1s.append(f1_score(yi, pred, average="macro"))
        key = "multitask" if multitask else "single_task"
        out[key] = {"macro_f1_mean": float(np.mean(f1s)),
                    "macro_f1_sd": float(np.std(f1s)), "seeds": len(f1s)}
        progress(f"arm E3 — {key}: macroF1={out[key]['macro_f1_mean']:.3f}")

    if "multitask" in out and "single_task" in out:
        out["delta_macro_f1"] = (out["multitask"]["macro_f1_mean"]
                                 - out["single_task"]["macro_f1_mean"])
    save("E3_multitask", out)


def main():
    # E3 is the one arm wanting torch, which the BirdNET venv does not carry.
    # Run it from crowgpt's venv, which has torch and sklearn both:
    #   ../../crowgpt/.venv/bin/python run.py --only e3
    only = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--only" else None

    progress("loading cached features and proving the join")
    X, Y, groups, segments = load_aligned()
    Xs, ys, gs, segs = single_label(X, Y, groups, segments)
    save("dataset", {
        "n_rows_cached": int(len(Y)),
        "n_single_label": int(len(ys)),
        "n_recordings": int(len(set(groups))),
        "n_recordings_single_label": int(len(set(gs))),
        "class_counts": {k: int(v) for k, v in Counter(ys).most_common()},
        "feature": "birdnet_pooled_mean_std_max (3072-d, cached)",
    })
    progress(f"{len(ys)} single-label rows over {len(set(gs))} recordings")

    if only in (None, "d"):
        arm_d()                   # cheap, and it can invalidate A-C
    if only in (None, "a"):
        arm_a(Xs, ys, gs)
    if only in (None, "b"):
        arm_b(X, groups, segments)
    if only in (None, "c"):
        arm_c(Xs, ys, gs, segs)
    if only in (None, "e1"):
        arm_e1(Xs, ys, gs, segs)
    if only in (None, "e2"):
        arm_e2(Xs, ys, gs)
    if only in (None, "e3"):
        arm_e3(Xs, ys, gs, segs)
    progress("done — results.json written")


if __name__ == "__main__":
    main()
