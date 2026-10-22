#!/usr/bin/env python3
"""Would training on all of crow-tools' categories beat collapsing them to CORE?

`FLAG_TO_CORE` in pipelines/ingest/corpus.py folds mob + alert + scold into one
"alarm call" and rattle into "call". The question is whether that collapse throws
away learnable structure — whether a head asked for `mob` vs `alert` would get
them right — or whether it is hiding a distinction the corpus cannot support.

Answering it needs no new embeddings. The cached features at
pipelines/ingest/results/pooled_embeddings_crowtools_all-public.npz were built
one row per labelled segment in corpus order, so each row can be walked back to
its segment and given its *raw* flags instead of the CORE class it was folded
into. `align()` proves the join rather than trusting it: every row's CORE labels
must equal the ones its segment maps to, or the run stops.

    ../../pipelines/representation/.venv-birdnet/bin/python run.py

Six things get measured, and C, D and E are the ones that decide it:

  A. inventory    — how often each flag is even *asked*, and across how many
                    recordings, which bounds what any AUC can mean
  B. one-vs-rest  — grouped AUC per raw flag next to the CORE class it folds into
  C. head-to-head — mob vs alert directly, and how many recordings contain both
                    (a split no recording spans is a recording classifier)
  D. thresholds   — precision actually available at a given recall, since the
                    app shows one answer rather than a sweep
  E. multiclass   — one head at CORE vs the same head at the finer classes,
                    its predictions mapped back down, on the same rows and folds
  F. confound     — how much of `begging` is just crowAge=juvenile
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, f1_score,
                             precision_recall_curve, roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
INGEST = REPO / "pipelines" / "ingest"
CACHE = INGEST / "results" / "pooled_embeddings_crowtools_all-public.npz"

sys.path.insert(0, str(INGEST))
from corpus import FLAG_TO_CORE, LabelCorpus  # noqa: E402

# Every call-type flag crow-tools carries, including the two the mapping drops.
FLAGS = ["mob", "alert", "scold", "softSong", "rattle", "begging", "grief"]
MIN_POSITIVES = 8
MIN_GROUPS = 3


def align():
    """Cached feature rows joined back to their segments, with the join checked.

    build_dataset.py appends one row per segment per file and records the file_id
    as the CV group, so the rows for a file are a contiguous run in `groups` and
    are in the same order as that file's segments. Files whose count disagrees or
    whose CORE labels disagree are a broken assumption, not a row to salvage:
    a silent misalignment would attribute one call's flags to another's audio and
    every number below would be noise wearing a decimal point.
    """
    data = np.load(CACHE, allow_pickle=True)
    X, Y, groups = data["X"], [sorted(s) for s in data["Y"]], list(data["groups"])

    corpus = LabelCorpus(dataset="all-public")
    by_file = defaultdict(list)
    for seg in corpus.labeled_segments(require_audio=True):
        by_file[Path(seg.audio_path).stem].append(seg)

    runs: list[tuple[str, list[int]]] = []
    for i, group in enumerate(groups):
        if runs and runs[-1][0] == group:
            runs[-1][1].append(i)
        else:
            runs.append((group, [i]))

    segments: list[object] = [None] * len(Y)
    for file_id, rows in runs:
        segs = by_file.get(file_id, [])
        if len(segs) != len(rows):
            raise SystemExit(
                f"{file_id}: {len(rows)} cached rows against {len(segs)} segments. "
                f"The cache is out of step with the fork — rebuild it with "
                f"build_dataset.py before trusting any of this."
            )
        for seg, row in zip(segs, rows):
            if sorted(seg.labels) != Y[row]:
                raise SystemExit(
                    f"{file_id} row {row}: cached {Y[row]} against {sorted(seg.labels)}. "
                    f"Same reason — rebuild."
                )
            segments[row] = seg
    if any(s is None for s in segments):
        raise SystemExit("some cached rows matched no segment; rebuild the cache")
    return X, segments, np.array(groups)


def grouped_auc(X, y, groups, seed=0):
    """Recording-grouped one-vs-rest AUC, or None when the class is too thin.

    Same shape as train_american_crow.grouped_auc so the numbers here are
    comparable to the ones the shipped head reports.
    """
    y = np.asarray(y)
    positives, n_pos_groups = int(y.sum()), len(set(groups[y == 1]))
    if positives < MIN_POSITIVES or positives == len(y) or n_pos_groups < MIN_GROUPS:
        return None
    splits = min(5, n_pos_groups, len(set(groups[y == 0])))
    if splits < 2:
        return None
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced"),
    )
    cv = StratifiedGroupKFold(n_splits=splits, shuffle=True, random_state=seed)
    try:
        proba = cross_val_predict(
            clf, X, y, cv=cv, groups=groups, method="predict_proba"
        )[:, 1]
    except ValueError:
        return None
    return round(float(roc_auc_score(y, proba)), 3)


def auc_spread(X, y, groups, seeds=5):
    """The same AUC over several fold shufflings, lowest to highest.

    Reported wherever the class is thin. One number from one seed on 138 segments
    invites a decision the sample cannot carry; the spread says how much of the
    gap between two options is real and how much is which recordings landed in
    which fold.
    """
    values = [grouped_auc(X, y, groups, seed=s) for s in range(seeds)]
    values = [v for v in values if v is not None]
    return sorted(values) or None


def inventory(segments, groups):
    """Per flag: whether it was asked, how many positives, across how many
    recordings — and the largest single recording's share of them.

    `asked` is the column that decides the question. crow-tools grew `scold` and
    `grief` after labelling had started, so they are absent from most segments
    rather than False on them. Training a scold head on the whole corpus would
    hand it ~1,000 segments nobody was ever asked about as confident negatives.
    """
    rows = {}
    for flag in FLAGS:
        asked = [s for s in segments if flag in s.flags]
        positive = np.array([bool(s.flags.get(flag)) for s in segments])
        pos_groups = Counter(groups[positive])
        rows[flag] = {
            "core": FLAG_TO_CORE.get(flag),
            "asked": len(asked),
            "positives": int(positive.sum()),
            "recordings": len(pos_groups),
            "largest_recording_share": (
                round(pos_groups.most_common(1)[0][1] / int(positive.sum()), 3)
                if pos_groups else None
            ),
        }
    return rows


def cooccurrence(segments):
    """How often two flags fire on the same segment, as a share of the smaller.

    A high share means the labellers did not treat them as alternatives, so a
    multiclass head asked to pick one would be scored against a coin flip the
    corpus itself declined to make.
    """
    out = {}
    for a, b in combinations(FLAGS, 2):
        both = sum(1 for s in segments if s.flags.get(a) and s.flags.get(b))
        if not both:
            continue
        smaller = min(
            sum(1 for s in segments if s.flags.get(a)),
            sum(1 for s in segments if s.flags.get(b)),
        )
        out[f"{a}+{b}"] = {"both": both, "share_of_smaller": round(both / smaller, 3)}
    return out


def one_vs_rest(X, segments, groups):
    """Grouped AUC for every raw flag and every CORE class it folds into.

    Restricted to the segments where the flag was asked, so the negatives are
    real negatives. A flag that scores well only on the whole corpus is scoring
    on the difference between two labelling eras.
    """
    raw = {}
    for flag in FLAGS:
        asked = np.array([flag in s.flags for s in segments])
        y = np.array([bool(s.flags.get(flag)) for s in segments])
        raw[flag] = {
            "auc_where_asked": grouped_auc(X[asked], y[asked], groups[asked]),
            "n_where_asked": int(asked.sum()),
        }
    core = {}
    for name in sorted(set(FLAG_TO_CORE.values())):
        y = np.array([name in s.labels for s in segments])
        core[name] = grouped_auc(X, y, groups)
    return {"raw_flags": raw, "core_classes": core}


def head_to_head(X, segments, groups, a="mob", b="alert"):
    """Can a head separate two flags that fold into the same CORE class?

    Two numbers, and the second is the one that decides. The AUC says whether
    the split is learnable; `recordings_with_both` says whether it was ever a
    question about calls. If almost no recording contains both, then a perfect
    score means the head learned which recording it was listening to — the exact
    failure recording-grouped CV exists to expose, which it cannot do when the
    grouping variable and the label are the same thing.
    """
    exclusive = np.array(
        [bool(s.flags.get(a)) != bool(s.flags.get(b)) for s in segments]
    )
    y = np.array([bool(s.flags.get(a)) for s in segments])
    per_recording = defaultdict(set)
    for seg, group in zip(segments, groups):
        for flag in (a, b):
            if seg.flags.get(flag):
                per_recording[group].add(flag)
    return {
        "pair": f"{a} vs {b}",
        "n_exclusive": int(exclusive.sum()),
        "auc": grouped_auc(X[exclusive], y[exclusive], groups[exclusive]),
        "recordings_with_both": sum(1 for f in per_recording.values() if len(f) == 2),
        "recordings_with_either": len(per_recording),
    }


def within_recording(X, segments, groups, a="mob", b="alert"):
    """The same pair, restricted to recordings that contain both calls.

    This is the measurement that upgrades "learnable" to "acoustic". Across the
    whole corpus a flag is nearly a property of the recording, so a head can score
    well by recognising which recording it is in — and recording-grouped CV cannot
    catch that, because holding out a recording also holds out its label. Inside
    recordings that carry both flags the recording is held constant and cannot be
    the answer, so whatever score survives is about the call.
    """
    both_flags = {
        group
        for group in set(groups)
        if any(s.flags.get(a) for s, g in zip(segments, groups) if g == group)
        and any(s.flags.get(b) for s, g in zip(segments, groups) if g == group)
    }
    inside = np.array([
        g in both_flags and bool(s.flags.get(a)) != bool(s.flags.get(b))
        for s, g in zip(segments, groups)
    ])
    y = np.array([bool(s.flags.get(a)) for s in segments])
    return {
        "pair": f"{a} vs {b}, within recordings holding both",
        "recordings": len(both_flags),
        "n": int(inside.sum()),
        "n_positive": int(y[inside].sum()),
        "auc": grouped_auc(X[inside], y[inside], groups[inside]),
        "auc_over_5_seeds": auc_spread(X[inside], y[inside], groups[inside]),
    }


def expanded_vs_collapsed(X, segments, groups):
    """Does a finer head still get the CORE answer right?

    One-vs-rest AUC cannot answer this. It scores each class against the rest in
    isolation, while what ships is one multiclass head whose classes compete — and
    the cost of splitting alarm into mob and alert is paid in confusion between
    them, which only a multiclass score can see.

    So: the same rows, the same folds, two label spaces. Train on CORE, and train
    on the raw flags and then map each prediction down to the CORE class it folds
    into. If the mapped-down score matches, the finer classes are free — the head
    can report mobbing rather than alarm and lose nothing. If it drops, the split
    is being paid for out of the class the app already shows.
    """
    fine = [f for f in FLAGS if FLAG_TO_CORE.get(f)]
    single = np.array([sum(bool(s.flags.get(f)) for f in fine) == 1 for s in segments])
    rows = [s for s, keep in zip(segments, single) if keep]
    y_fine = np.array([next(f for f in fine if s.flags.get(f)) for s in rows])
    y_core = np.array([FLAG_TO_CORE[f] for f in y_fine])
    Xs, gs = X[single], groups[single]

    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced"),
    )
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    predict = lambda y: cross_val_predict(clf, Xs, y, cv=cv, groups=gs)  # noqa: E731
    fine_pred = predict(y_fine)
    core_pred = predict(y_core)
    mapped = np.array([FLAG_TO_CORE[f] for f in fine_pred])

    return {
        "n": int(single.sum()),
        "fine_classes": sorted(set(y_fine)),
        "collapsed_macro_f1": round(f1_score(y_core, core_pred, average="macro"), 3),
        "expanded_mapped_down_macro_f1": round(f1_score(y_core, mapped, average="macro"), 3),
        "expanded_macro_f1_at_its_own_classes": round(
            f1_score(y_fine, fine_pred, average="macro"), 3
        ),
        "mob_alert_confusions": {
            "mob called alert": int(((y_fine == "mob") & (fine_pred == "alert")).sum()),
            "alert called mob": int(((y_fine == "alert") & (fine_pred == "mob")).sum()),
            "mob n": int((y_fine == "mob").sum()),
            "alert n": int((y_fine == "alert").sum()),
        },
    }


def operating_points(X, segments, groups):
    """What "can it detect mob" means at a threshold, not as an AUC.

    AUC is a ranking score over the whole sweep, and the app does not ship a
    sweep — `SpeciesHead.predict` takes one answer and shows it. So for each flag
    that could become a class: average precision, and the precision actually
    available at three recall levels. Prevalence is printed beside them because
    precision is meaningless without it — 30% of this corpus is mob, so 0.30 is
    what guessing achieves.

    `analyzer.birdnet.reliability_tier` is the yardstick already in the product:
    ≥0.80 AUC reads to the recordist as "reliable", 0.70-0.80 as "moderate".
    """
    out = {}
    for flag in ("mob", "alert", "begging", "rattle"):
        asked = np.array([flag in s.flags for s in segments])
        y = np.array([bool(s.flags.get(flag)) for s in segments])[asked]
        Xa, ga = X[asked], groups[asked]
        clf = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=5000, class_weight="balanced"),
        )
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
        proba = cross_val_predict(clf, Xa, y, cv=cv, groups=ga,
                                  method="predict_proba")[:, 1]
        precision, recall, _ = precision_recall_curve(y, proba)
        at = {}
        for target in (0.5, 0.7, 0.9):
            reachable = precision[:-1][recall[:-1] >= target]
            at[f"precision_at_recall_{target}"] = (
                round(float(reachable.max()), 3) if len(reachable) else None)
        f1 = 2 * precision * recall / np.clip(precision + recall, 1e-9, None)
        out[flag] = {
            "prevalence": round(float(y.mean()), 3),
            "average_precision": round(float(average_precision_score(y, proba)), 3),
            "best_f1": round(float(np.nanmax(f1)), 3),
            **at,
        }
    return out


def begging_confound(segments):
    """How much of `begging` is just "this recording has a juvenile in it".

    begging is the one expansion already made, and the one class the corpus
    supposedly carries alone. If it coincides with crowAge then the head may be
    reading juvenile-recording character rather than the call.
    """
    begging = [s for s in segments if s.flags.get("begging")]
    juvenile = [s for s in segments if s.flags.get("crowAge") == 2]
    both = [s for s in begging if s.flags.get("crowAge") == 2]
    return {
        "begging": len(begging),
        "crow_age_juvenile": len(juvenile),
        "both": len(both),
        "begging_that_is_juvenile": round(len(both) / len(begging), 3) if begging else None,
        "juvenile_that_is_begging": round(len(both) / len(juvenile), 3) if juvenile else None,
    }


def main() -> int:
    if not CACHE.exists():
        raise SystemExit(f"Missing {CACHE} — run pipelines/ingest/build_dataset.py first.")
    X, segments, groups = align()
    print(f"joined {len(segments)} cached rows to their segments, labels agreeing\n")

    results = {
        "n_segments": len(segments),
        "n_recordings": len(set(groups)),
        "inventory": inventory(segments, groups),
        "cooccurrence": cooccurrence(segments),
        "separability": one_vs_rest(X, segments, groups),
        "head_to_head": [
            head_to_head(X, segments, groups, "mob", "alert"),
            head_to_head(X, segments, groups, "mob", "scold"),
            head_to_head(X, segments, groups, "rattle", "softSong"),
        ],
        "within_recording": [
            within_recording(X, segments, groups, "mob", "alert"),
            within_recording(X, segments, groups, "rattle", "softSong"),
        ],
        "operating_points": operating_points(X, segments, groups),
        "expanded_vs_collapsed": expanded_vs_collapsed(X, segments, groups),
        "begging_confound": begging_confound(segments),
    }

    print("A. inventory")
    print(f"  {'flag':<10}{'core':<12}{'asked':>7}{'pos':>7}{'recs':>7}{'top rec':>9}")
    for flag, row in results["inventory"].items():
        share = row["largest_recording_share"]
        print(f"  {flag:<10}{str(row['core']):<12}{row['asked']:>7}{row['positives']:>7}"
              f"{row['recordings']:>7}{'' if share is None else f'{share:>8.0%}'}")

    print("\n  co-occurring pairs (share of the smaller class)")
    for pair, row in sorted(results["cooccurrence"].items(),
                            key=lambda kv: -kv[1]["share_of_smaller"]):
        print(f"    {pair:<22}{row['both']:>5}  {row['share_of_smaller']:>6.0%}")

    print("\nB. one-vs-rest grouped AUC")
    for flag, row in results["separability"]["raw_flags"].items():
        print(f"  {flag:<10}{str(row['auc_where_asked']):>7}  (n={row['n_where_asked']})")
    print("  --- collapsed into CORE ---")
    for name, auc in results["separability"]["core_classes"].items():
        print(f"  {name:<12}{str(auc):>7}")

    print("\nC. head-to-head inside one CORE class")
    for row in results["head_to_head"]:
        print(f"  {row['pair']:<22}auc {str(row['auc']):>6}  n={row['n_exclusive']:<6}"
              f"recordings with both {row['recordings_with_both']}/"
              f"{row['recordings_with_either']}")

    print("\n  with the recording held constant")
    for row in results["within_recording"]:
        spread = row["auc_over_5_seeds"] or []
        print(f"    {row['pair'].split(',')[0]:<22}auc {str(row['auc']):>6}  "
              f"n={row['n']:<6}({row['n_positive']} pos, {row['recordings']} recordings)"
              + (f"  5 seeds {spread[0]}-{spread[-1]}" if spread else ""))

    print("\nD. at a threshold, not as a sweep")
    print(f"  {'flag':<10}{'prev':>6}{'AP':>7}{'bestF1':>8}"
          f"{'P@R.5':>7}{'P@R.7':>7}{'P@R.9':>7}")
    for flag, row in results["operating_points"].items():
        cells = "".join(
            f"{'  --  ' if row[k] is None else f'{row[k]:>6.2f}'}"
            for k in ("precision_at_recall_0.5", "precision_at_recall_0.7",
                      "precision_at_recall_0.9"))
        print(f"  {flag:<10}{row['prevalence']:>6.2f}{row['average_precision']:>7.2f}"
              f"{row['best_f1']:>8.2f} {cells}")

    print("\nE. one multiclass head, two label spaces (same rows, same folds)")
    ev = results["expanded_vs_collapsed"]
    print(f"  rows with exactly one flag        {ev['n']}")
    print(f"  collapsed, macro-F1              {ev['collapsed_macro_f1']}")
    print(f"  expanded then mapped down        {ev['expanded_mapped_down_macro_f1']}")
    print(f"  expanded at its own classes      {ev['expanded_macro_f1_at_its_own_classes']}"
          f"  {ev['fine_classes']}")
    c = ev["mob_alert_confusions"]
    print(f"  mob called alert {c['mob called alert']}/{c['mob n']}   "
          f"alert called mob {c['alert called mob']}/{c['alert n']}")

    print("\nF. begging vs crowAge")
    for key, value in results["begging_confound"].items():
        print(f"  {key:<26}{value}")

    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {HERE / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
