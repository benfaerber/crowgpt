"""Train an American Crow call-type head, and be able to say two calls at once.

Three measurable axes, taken as flags rather than baked in silently:

**--head onevsrest** replaces the multiclass softmax with one logistic
regression per class. The softmax heads cannot report a co-occurrence — they
argmax over classes that sum to one — and worse, they were never shown one:
`train.py:41`, `train_species.py:131` and `train_american_crow.py:84` each drop
any segment carrying two labels. That discards 241 of crow-tools' 2,494 rows,
including 23 `begging + rattle` — a fledgling begging while an adult rattles.

**--source window-mean** (validated in experiment 0121, now the shipped source
via `make train-crow`) trains on uniform 1024-d window-mean BirdNET features
(`pooling.MEAN_FEATURE`) with `C = 0.1` and renames crow-tools' `call` flag to
what it actually is (`rattle`; experiment 0012). Weak archive generic `call`
clips are excluded from the `rattle` binary classifier while remaining active
for `alarm call`, `begging`, `song`, and `flight call`. On Ben's kept field
captures, moving off 3072-d `mean+std+max` removes the single-window `std=0`
shortcut and lifts multi-window (`>= 6s`) span accuracy from 50% (7/14) to
100% (14/14), while raising `rattle` grouped AUC from 0.876 to 0.967.

**--backbone perch** (`--source raw`) swaps BirdNET's 1024-d embedding for
Perch 2.0's 1536-d on experiment 0025's keyed single-window arms.

    ../representation/.venv-birdnet/bin/python train_head.py --all
    ../representation/.venv-birdnet/bin/python train_head.py \
        --backbone birdnet --head onevsrest --source window-mean --write

Writes to `models-candidate/` unless --write is given. Nothing shipped moves
until the numbers say it should, and `analyzer/birdnet.py` refuses at load any
head whose feature width or backbone disagrees with the pooling definition — so
a candidate cannot be served by accident.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARMS = REPO / "experiments" / "0025-is-birdnet-the-bottleneck" / "arms"
CANDIDATES = HERE / "models-candidate"

sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(HERE))

import pooling  # noqa: E402
from features import Features  # noqa: E402
from heads import MultiLabelHead  # noqa: E402  — importable, so it unpickles
from probe import GroupedProbe  # noqa: E402

INGEST_POOLED = (REPO / "pipelines" / "ingest" / "results"
                 / "pooled_embeddings_crowtools_all-public.npz")
ARCHIVE_POOLED = HERE / "results" / "pooled_embeddings.npz"

#: The four crow-tools can express on legacy raw/pooled comparisons.
CROWTOOLS_CORE = ["alarm call", "begging", "call", "song"]

#: What a legacy 3072-d pooled head carries.
SHIPPED_CORE = CROWTOOLS_CORE + ["flight call"]

#: What the 0121-validated window-mean head carries: crow-tools' `rattle` flag
#: is named honestly as `rattle` rather than wearing the catch-all name `call`
#: (experiment 0012). `rattle` already resolves to core `call` in SEED_LABELS.
WINDOW_MEAN_CORE = ["alarm call", "begging", "rattle", "song", "flight call"]
WINDOW_MEAN_C = 0.1

BACKBONES = {
    "birdnet": ("a-birdnet-grid.npz", "birdnet", 1024),
    "perch": ("c-perch-3s.npz", "perch_v2", 1536),
}
MIN_PER_CLASS = 8

#: Carried into metrics.json so the dashboard and operators see the exact
#: provenance and corpus-boundary caveats behind the reported AUCs.
CAVEATS_POOLED = {
    "flight call": (
        "Measured across a corpus boundary that predicts the label. crow-tools "
        "has no flight-call flag, so all 40 positives come from the archive set — and "
        "the two corpora are trivially separable in this feature, since "
        "crow-tools pools a single 3s window (std=0) and the archive set pools whole clips. "
        "See experiments/0025 --preflight."
    ),
    "co-occurrence": (
        "A one-vs-rest head's probabilities are independent and do not sum to "
        "one. Do not argmax them and call the result a confidence."
    ),
}

CAVEATS_WINDOW_MEAN = {
    "flight call": (
        "crow-tools has no flight-call flag, so all 40 positives come from the "
        "archive set. Uniform 1024-d window-mean pooling removes the single-window "
        "std=0 shortcut (experiments 0036, 0121), though recording acoustics still "
        "differ across corpora (within-archive grouped AUC is ~0.74 vs ~0.86 combined)."
    ),
    "rattle": (
        "crow-tools' `call` class came exclusively from its `rattle` flag (experiment "
        "0012) and is emitted honestly as `rattle`. Weak archive generic `call` tags "
        "are excluded from fitting `rattle` (experiment 0121); ordinary contact caws "
        "remain unlabelled in crow-tools."
    ),
    "co-occurrence": (
        "A one-vs-rest head's probabilities are independent and do not sum to "
        "one. Do not argmax them and call the result a confidence."
    ),
}


def load(backbone, source="raw"):
    """Load training features for `raw`, `pooled` (3072-d), or `window-mean` (1024-d)."""
    if source == "raw":
        name, _, dim = BACKBONES[backbone]
        feats = Features.read(ARMS / name)
        if feats.dim != dim:
            raise SystemExit(f"{name} is {feats.dim}-d, expected {dim}")
        return feats, None

    if backbone != "birdnet":
        raise SystemExit(
            f"--source {source} is BirdNET only: no pooled Perch cache exists, and "
            "building one means re-embedding the archive flight-call clips."
        )

    is_window_mean = source == "window-mean"
    target_feature = pooling.MEAN_FEATURE if is_window_mean else pooling.FEATURE
    parts = []
    ct_flags = []
    for path, prefix in ((INGEST_POOLED, "ct"), (ARCHIVE_POOLED, "xc")):
        if not path.exists():
            continue
        d = np.load(path, allow_pickle=True)
        X_part = d["X"][:, :pooling.MEAN_DIM] if is_window_mean else d["X"]
        if is_window_mean:
            if prefix == "ct":
                # crow-tools' `call` is its `rattle` flag (corpus.py, 0012).
                Y = [sorted({"rattle" if c == "call" else c for c in s}) for s in d["Y"]]
            else:
                # Weak archive `call` clips are generic caws, not rattles; exclude
                # them from rattle while keeping flight/alarm/begging/song labels.
                Y = [sorted({c for c in s if c != "call"}) for s in d["Y"]]
        else:
            Y = [sorted(set(s)) for s in d["Y"]]
        if "groups" in d.files:
            groups = np.array([f"{prefix}:{g}" for g in d["groups"]])
        else:  # one vector per clip -> each row is its own recording
            groups = np.array([f"{prefix}:{i}" for i in range(len(Y))])
        keys = [f"{prefix}:{i}" for i in range(len(Y))]
        parts.append(Features(X_part, Y, groups, keys, target_feature))
        ct_flags.append(np.full(len(Y), prefix == "ct", dtype=bool))
    if not parts:
        raise SystemExit("no pooled caches on disk; run build_dataset.py first")

    feats = Features(
        np.concatenate([p.X for p in parts]),
        [y for p in parts for y in p.Y],
        np.concatenate([p.groups for p in parts]),
        [k for p in parts for k in p.keys],
        target_feature,
    )
    masks = {"rattle": np.concatenate(ct_flags)} if is_window_mean else None
    return feats, masks


def _ovr_scores(X, Y, groups, cls, c_val=1.0):
    yb = np.array([1 if cls in set(s) else 0 for s in Y], dtype=int)
    pos = int(yb.sum())
    n_groups_pos = len(set(groups[yb == 1]))
    if pos < MIN_PER_CLASS or pos == len(yb) or n_groups_pos < 3:
        return None, None, pos
    n_splits = min(5, n_groups_pos, len(set(groups[yb == 0])))
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=0)
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=c_val, max_iter=5000, class_weight="balanced"),
    )
    proba = cross_val_predict(clf, X, yb, cv=cv, groups=groups, method="predict_proba")[:, 1]
    return (
        round(float(roc_auc_score(yb, proba)), 3),
        round(float(average_precision_score(yb, proba)), 3),
        pos,
    )


def evaluate(feats, head_kind, CORE, masks=None, c_val=1.0):
    """Recording-grouped per-class AUC and AP, honouring per-class row masks and C."""
    out = {}
    if c_val == 1.0 and not masks:
        probe = GroupedProbe(feats.X, feats.Y, feats.groups)
        for cls in CORE:
            if head_kind == "softmax":
                keep = np.array([len(set(y)) == 1 for y in feats.Y])
                sub = GroupedProbe(
                    feats.X[keep],
                    [feats.Y[i] for i in np.where(keep)[0]],
                    feats.groups[keep],
                )
                auc, pos = sub.ovr_auc(cls)
                ap, _ = sub.ovr_ap(cls)
            else:
                auc, pos = probe.ovr_auc(cls)
                ap, _ = probe.ovr_ap(cls)
            out[cls] = {"auc": auc, "ap": ap, "positives": pos}
        return out

    for cls in CORE:
        keep = np.ones(len(feats.Y), dtype=bool)
        if masks and cls in masks:
            keep &= np.asarray(masks[cls], dtype=bool)
        if head_kind == "softmax":
            keep &= np.array([len(set(y)) == 1 for y in feats.Y])
        idx = np.flatnonzero(keep)
        auc, ap, pos = _ovr_scores(
            feats.X[idx],
            [feats.Y[i] for i in idx],
            feats.groups[idx],
            cls,
            c_val=c_val,
        )
        out[cls] = {"auc": auc, "ap": ap, "positives": pos}
    return out


def co_occurrence(feats, head_kind, CORE, masks=None, c_val=1.0):
    """Can the head report BOTH classes on a segment that carries both?"""
    multi = {i for i, y in enumerate(feats.Y) if len(set(y) & set(CORE)) > 1}
    if not multi:
        return None
    groups = feats.groups
    n_splits = min(5, len({groups[i] for i in multi}))
    if n_splits < 2:
        return None

    yb = np.array([1 if i in multi else 0 for i in range(len(feats.Y))])
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=0)
    hits = {"both_above_0.5": 0, "both_above_0.3": 0, "total": 0}
    for train_idx, test_idx in cv.split(feats.X, yb, groups):
        if head_kind == "onevsrest":
            fold_masks = (
                {k: np.asarray(v, dtype=bool)[train_idx] for k, v in masks.items()}
                if masks else None
            )
            head = MultiLabelHead(CORE, C=c_val).fit(
                feats.X[train_idx],
                [feats.Y[i] for i in train_idx],
                masks=fold_masks,
            )
            order = head.classes
            proba = head.predict_proba(feats.X[test_idx])
        else:
            rows = [i for i in train_idx if len(set(feats.Y[i]) & set(CORE)) == 1]
            y = [next(iter(set(feats.Y[i]) & set(CORE))) for i in rows]
            if len(set(y)) < 2:
                continue
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=c_val, max_iter=5000, class_weight="balanced"),
            ).fit(feats.X[rows], y)
            order = list(clf.classes_)
            proba = clf.predict_proba(feats.X[test_idx])
        for row, i in zip(proba, test_idx):
            truth = set(feats.Y[i]) & set(CORE)
            if len(truth) < 2 or not truth.issubset(set(order)):
                continue
            hits["total"] += 1
            scores = [row[order.index(c)] for c in truth]
            if min(scores) > 0.5:
                hits["both_above_0.5"] += 1
            if min(scores) > 0.3:
                hits["both_above_0.3"] += 1
    return hits


def train(feats, head_kind, backbone, write=False, source="raw", CORE=None,
          scores=None, masks=None, c_val=1.0):
    _, backbone_name, dim = BACKBONES[backbone]
    if source == "pooled":
        feature_name, dim = pooling.FEATURE, pooling.POOLED_DIM
        caveats = CAVEATS_POOLED
    elif source == "window-mean":
        feature_name, dim = pooling.MEAN_FEATURE, pooling.MEAN_DIM
        caveats = CAVEATS_WINDOW_MEAN
    else:
        feature_name = f"{backbone_name}_single_window"
        caveats = CAVEATS_POOLED

    if head_kind == "onevsrest":
        model = MultiLabelHead(CORE, C=c_val).fit(feats.X, feats.Y, masks=masks)
        classes = list(model.classes)
        n_train = len(feats.Y)
    else:
        keep = [i for i, y in enumerate(feats.Y) if len(set(y)) == 1]
        y = np.array([next(iter(set(feats.Y[i]))) for i in keep])
        strong = {c for c in set(y) if (y == c).sum() >= MIN_PER_CLASS}
        rows = [i for i, c in zip(keep, y) if c in strong]
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=c_val, max_iter=5000, class_weight="balanced"),
        ).fit(feats.X[rows], [next(iter(set(feats.Y[i]))) for i in rows])
        classes = list(model.classes_)
        n_train = len(rows)

    root = HERE / "models" if write else CANDIDATES
    out_dir = root / ("american-crow" if write
                      else f"american-crow-{backbone}-{head_kind}-{source}")
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model,
        "classes": classes,
        # The three fields analyzer/birdnet.py checks at load. A head trained on
        # one backbone or pooling width cannot be silently served by another.
        "feature": feature_name,
        "backbone": backbone_name,
        "dim": dim,
        # The analyzer branches on this: a multi-label head's probabilities do
        # not sum to one, so argmax-and-call-it-confidence would be wrong.
        "multi_label": head_kind == "onevsrest",
    }, out_dir / "calltype_clf.joblib")
    if scores is not None:
        # analyzer/birdnet.py reads per_class_auc from here to bucket each class
        # into a reliability tier, so a head shipped without refreshing this
        # would be described by its predecessor's numbers.
        meta = {
            "n": int(len(feats.Y)),
            "trained_on": n_train,
            "head": "one-vs-rest" if head_kind == "onevsrest" else "softmax",
            "backbone": backbone_name,
            "feature": feature_name,
            "source": source,
            "C": c_val,
            "classes": {c: int(scores[c]["positives"]) for c in classes if c in scores},
            "per_class_auc": {c: scores[c]["auc"] for c in scores},
            "caveats": caveats,
        }
        if source == "window-mean":
            xc_idx = np.array([str(g).startswith("xc:") for g in feats.groups])
            if xc_idx.any():
                fc_within_auc, _, _ = _ovr_scores(
                    feats.X[xc_idx],
                    [feats.Y[i] for i in np.flatnonzero(xc_idx)],
                    feats.groups[xc_idx],
                    "flight call",
                    c_val=c_val,
                )
                meta["within_archive_flight_call_auc"] = fc_within_auc
        (out_dir / "metrics.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out_dir, n_train


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backbone", choices=sorted(BACKBONES), default="perch")
    parser.add_argument("--head", choices=["softmax", "onevsrest"],
                        default="onevsrest")
    parser.add_argument("--all", action="store_true",
                        help="train and score all four combinations")
    parser.add_argument(
        "--source",
        choices=["raw", "pooled", "window-mean"],
        default="raw",
        help="raw = like-for-like across backbones; "
             "pooled = legacy 3072-d mean+std+max; "
             "window-mean = 1024-d uniform window mean + pure rattle (0121)",
    )
    parser.add_argument("--write", action="store_true",
                        help="write into models/ instead of models-candidate/")
    args = parser.parse_args()

    combos = ([(b, h) for b in sorted(BACKBONES) for h in ("softmax", "onevsrest")]
              if args.all else [(args.backbone, args.head)])

    results = {}
    for backbone, head_kind in combos:
        feats, masks = load(backbone, args.source)
        c_val = WINDOW_MEAN_C if args.source == "window-mean" else 1.0
        label = f"{backbone}/{head_kind}"
        print(f"\n=== {label}  ({feats.dim}-d, {len(feats)} rows, C={c_val}) ===")
        if args.source == "window-mean":
            CORE = WINDOW_MEAN_CORE
        elif args.source == "pooled":
            CORE = SHIPPED_CORE
        else:
            CORE = CROWTOOLS_CORE
        scores = evaluate(feats, head_kind, CORE, masks=masks, c_val=c_val)
        print(f"{'class':<12}{'n+':>6}{'AUC':>8}{'AP':>8}")
        for cls in CORE:
            s = scores[cls]
            print(f"{cls:<12}{s['positives']:>6}"
                  f"{_fmt(s['auc']):>8}{_fmt(s['ap']):>8}")
        aucs = [s["auc"] for s in scores.values() if s["auc"] is not None]
        print(f"  mean AUC {np.mean(aucs):.3f}")

        scored_on = sum(1 for y in feats.Y
                        if head_kind == "onevsrest"
                        or len(set(y) & set(CORE)) == 1)
        entry = {"scores": scores, "mean_auc": round(float(np.mean(aucs)), 3),
                 "scored_on_rows": scored_on}
        co = co_occurrence(feats, head_kind, CORE, masks=masks, c_val=c_val)
        entry["co_occurrence"] = co
        if co and co["total"]:
            print(f"  co-occurrence: both true classes >0.5 on "
                  f"{co['both_above_0.5']}/{co['total']} held-out multi-label rows "
                  f"({co['both_above_0.5'] / co['total']:.0%}); "
                  f">0.3 on {co['both_above_0.3']}/{co['total']} "
                  f"({co['both_above_0.3'] / co['total']:.0%})")
        out_dir, n_train = train(
            feats, head_kind, backbone, args.write, args.source, CORE, scores,
            masks=masks, c_val=c_val,
        )
        entry["trained_on"] = n_train
        entry["path"] = str(out_dir.relative_to(REPO))
        print(f"  trained on {n_train} rows -> {out_dir.relative_to(REPO)}")
        results[label] = entry

    path = (HERE / "models-candidate" / "comparison.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {path.relative_to(REPO)}")

    if args.all:
        print("\n" + "=" * 72)
        print(f"{'combination':<22}{'mean AUC':>10}{'scored on':>11}"
              f"{'both>0.5':>10}{'both>0.3':>10}")
        for label, e in results.items():
            co = e.get("co_occurrence") or {}
            t = co.get("total") or 0
            half = "{}/{}".format(co.get("both_above_0.5", 0), t) if t else "—"
            third = "{}/{}".format(co.get("both_above_0.3", 0), t) if t else "—"
            print(f"{label:<22}{e['mean_auc']:>10}{e['scored_on_rows']:>11}"
                  f"{half:>10}{third:>10}")
        print("\nREAD THE COLUMNS SEPARATELY. Mean AUC is NOT comparable across")
        print("head kinds: a softmax is scored only on rows carrying one label,")
        print("which is 2,110 of 2,339 and the easier subset — the 229 rows it")
        print("cannot represent are deleted before it is graded. Compare backbones")
        print("down a head kind, and head kinds by the co-occurrence columns.")


def _fmt(v):
    return "—" if v is None else f"{v}"


if __name__ == "__main__":
    main()
