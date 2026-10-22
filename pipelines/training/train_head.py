"""Train an American Crow call-type head, and be able to say two calls at once.

Two changes from `train_american_crow.py`, measurable separately, which is why
this script takes both as flags rather than baking either in.

**--head onevsrest** replaces the multiclass softmax with one logistic
regression per class. The shipped heads cannot report a co-occurrence — they
argmax over classes that sum to one — and worse, they were never shown one:
`train.py:41`, `train_species.py:131` and `train_american_crow.py:84` each drop
any segment carrying two labels. That discards 241 of crow-tools' 2,494 rows,
including 23 `begging + call` — a fledgling begging while an adult caws, which
is exactly the failure Ben heard on capture 104. Kept as one-vs-rest, `call`
gains 54% more positives and `song` 38%.

**--backbone perch** swaps BirdNET's 1024-d embedding for Perch 2.0's 1536-d.
Experiment 0025 measured that swap as worth +0.022 macro-F1 and, on the fine
within-recording distinctions, +0.10 AUC.

Both read the keyed feature caches experiment 0025 built, so every combination
is scored on exactly the same rows and the two changes never confound.

    ../representation/.venv-birdnet/bin/python train_head.py --all
    ../representation/.venv-birdnet/bin/python train_head.py \
        --backbone perch --head onevsrest --write

Writes to `models-candidate/` unless --write is given. Nothing shipped moves
until the numbers say it should, and `analyzer/birdnet.py` refuses at load any
head whose feature width or backbone disagrees with the pooling definition — so
a candidate cannot be served by accident.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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

#: The four crow-tools can express. No flight-call flag exists upstream, so the
#: fifth CORE class cannot appear in a crow-tools-only comparison at all — see
#: experiment 0025's preflight for why the shipped 0.975 for flight call is not
#: a within-corpus number.
CROWTOOLS_CORE = ["alarm call", "begging", "call", "song"]

#: What a *shipped* head must carry. The pooled source includes the archive
#: set, which is the only place flight call exists, and dropping it would be a
#: visible regression — the app would stop offering a class it offers today.
SHIPPED_CORE = CROWTOOLS_CORE + ["flight call"]

BACKBONES = {
    "birdnet": ("a-birdnet-grid.npz", "birdnet", 1024),
    "perch": ("c-perch-3s.npz", "perch_v2", 1536),
}
MIN_PER_CLASS = 8

#: Carried into every metrics.json this writes, because the numbers above it are
#: read by the dashboard and by anyone deciding whether to believe a call type.
CAVEATS = {
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


def load(backbone, source="raw"):
    """The feature matrix, either like-for-like or exactly what ships.

    `raw` reads experiment 0025's keyed arms — identical rows across backbones,
    which is what makes the four-way comparison honest, but 1024/1536-d single
    windows.

    `pooled` reads the caches the shipped head was trained from: crow-tools plus
    the archive set that carries flight call, run through `pooling.pool` to
    3072-d. That is the ONLY source a drop-in replacement can use, because
    `SpeciesHead.predict` feeds `pool(embeddings)` at inference and a head
    trained on anything else is a different feature space wearing the same name.
    Perch has no pooled cache, so `pooled` implies BirdNET.
    """
    if source == "raw":
        name, _, dim = BACKBONES[backbone]
        feats = Features.read(ARMS / name)
        if feats.dim != dim:
            raise SystemExit(f"{name} is {feats.dim}-d, expected {dim}")
        return feats

    if backbone != "birdnet":
        raise SystemExit(
            "--source pooled is BirdNET only: no pooled Perch cache exists, and "
            "building one means re-embedding the archive flight-call clips."
        )
    parts = []
    for path, prefix in ((INGEST_POOLED, "ct"), (ARCHIVE_POOLED, "xc")):
        if not path.exists():
            continue
        d = np.load(path, allow_pickle=True)
        Y = [sorted(set(s)) for s in d["Y"]]
        if "groups" in d.files:
            groups = np.array([f"{prefix}:{g}" for g in d["groups"]])
        else:  # one vector per clip -> each row is its own recording
            groups = np.array([f"{prefix}:{i}" for i in range(len(Y))])
        keys = [f"{prefix}:{i}" for i in range(len(Y))]
        parts.append(Features(d["X"], Y, groups, keys, pooling.FEATURE))
    if not parts:
        raise SystemExit("no pooled caches on disk; run build_dataset.py first")
    return Features(
        np.concatenate([p.X for p in parts]),
        [y for p in parts for y in p.Y],
        np.concatenate([p.groups for p in parts]),
        [k for p in parts for k in p.keys],
        pooling.FEATURE,
    )


def evaluate(feats, head_kind, CORE):
    """Recording-grouped per-class AUC and AP, identical for both head kinds.

    One-vs-rest AUC is computed the same way whatever the head is, so the two
    are directly comparable — the difference is only which rows each was
    allowed to learn from.
    """
    probe = GroupedProbe(feats.X, feats.Y, feats.groups)
    out = {}
    for cls in CORE:
        if head_kind == "softmax":
            # What the shipped head actually sees: multi-label rows deleted.
            keep = np.array([len(set(y)) == 1 for y in feats.Y])
            sub = GroupedProbe(feats.X[keep], [feats.Y[i] for i in np.where(keep)[0]],
                               feats.groups[keep])
            auc, pos = sub.ovr_auc(cls)
            ap, _ = sub.ovr_ap(cls)
        else:
            auc, pos = probe.ovr_auc(cls)
            ap, _ = probe.ovr_ap(cls)
        out[cls] = {"auc": auc, "ap": ap, "positives": pos}
    return out


def co_occurrence(feats, head_kind, CORE):
    """Can the head report BOTH classes on a segment that carries both?

    The metric the AUCs cannot show, and the one capture 104 is about: a
    fledgling begging while an adult caws over it.

    Measured for both head kinds rather than asserted for one. A softmax cannot
    put two classes above 0.5 at once — they sum to one — but it *can* put two
    above 0.3, so the comparison at that threshold is real rather than rigged.
    The softmax is trained the way it ships, on single-label rows only, and then
    asked about co-occurrences it never saw; that is precisely the question.
    """
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
    for train, test in cv.split(feats.X, yb, groups):
        if head_kind == "onevsrest":
            head = MultiLabelHead(CORE).fit(feats.X[train],
                                            [feats.Y[i] for i in train])
            order = CORE
            proba = head.predict_proba(feats.X[test])
        else:
            # Trained as it ships: multi-label rows deleted from the fit.
            rows = [i for i in train if len(set(feats.Y[i]) & set(CORE)) == 1]
            y = [next(iter(set(feats.Y[i]) & set(CORE))) for i in rows]
            if len(set(y)) < 2:
                continue
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=5000, class_weight="balanced"),
            ).fit(feats.X[rows], y)
            order = list(clf.classes_)
            proba = clf.predict_proba(feats.X[test])
        for row, i in zip(proba, test):
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
          scores=None):
    _, backbone_name, dim = BACKBONES[backbone]
    if source == "pooled":
        # A drop-in for the shipped head: same feature name, same width, so
        # analyzer/birdnet.py's load check passes and pool() still applies.
        feature_name, dim = pooling.FEATURE, pooling.POOLED_DIM
    else:
        feature_name = f"{backbone_name}_single_window"
    if head_kind == "onevsrest":
        model = MultiLabelHead(CORE).fit(feats.X, feats.Y)
        classes = CORE
        n_train = len(feats.Y)
    else:
        keep = [i for i, y in enumerate(feats.Y) if len(set(y)) == 1]
        y = np.array([next(iter(set(feats.Y[i]))) for i in keep])
        strong = {c for c in set(y) if (y == c).sum() >= MIN_PER_CLASS}
        rows = [i for i, c in zip(keep, y) if c in strong]
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=5000, class_weight="balanced"),
        ).fit(feats.X[rows], [next(iter(set(feats.Y[i]))) for i in rows])
        classes = list(model.classes_)
        n_train = len(rows)

    root = HERE / "models" if write else CANDIDATES
    out_dir = root / ("american-crow" if write
                      else f"american-crow-{backbone}-{head_kind}-{source}")
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model, "classes": classes,
        # The three fields analyzer/birdnet.py checks at load. A head trained on
        # one backbone cannot be silently served by another.
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
        (out_dir / "metrics.json").write_text(json.dumps({
            "n": int(len(feats.Y)),
            "trained_on": n_train,
            "head": "one-vs-rest" if head_kind == "onevsrest" else "softmax",
            "backbone": backbone_name,
            "feature": feature_name,
            "source": source,
            "classes": {c: int(sum(1 for y in feats.Y if c in set(y)))
                        for c in classes},
            "per_class_auc": {c: scores[c]["auc"] for c in scores},
            "caveats": CAVEATS,
        }, indent=2))
    return out_dir, n_train


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backbone", choices=sorted(BACKBONES), default="perch")
    parser.add_argument("--head", choices=["softmax", "onevsrest"],
                        default="onevsrest")
    parser.add_argument("--all", action="store_true",
                        help="train and score all four combinations")
    parser.add_argument("--source", choices=["raw", "pooled"], default="raw",
                        help="raw = like-for-like across backbones; "
                             "pooled = the 3072-d feature the analyzer serves")
    parser.add_argument("--write", action="store_true",
                        help="write into models/ instead of models-candidate/")
    args = parser.parse_args()

    combos = ([(b, h) for b in sorted(BACKBONES) for h in ("softmax", "onevsrest")]
              if args.all else [(args.backbone, args.head)])

    results = {}
    for backbone, head_kind in combos:
        feats = load(backbone, args.source)
        label = f"{backbone}/{head_kind}"
        print(f"\n=== {label}  ({feats.dim}-d, {len(feats)} rows) ===")
        CORE = SHIPPED_CORE if args.source == "pooled" else CROWTOOLS_CORE
        scores = evaluate(feats, head_kind, CORE)
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
        co = co_occurrence(feats, head_kind, CORE)
        entry["co_occurrence"] = co
        if co and co["total"]:
            print(f"  co-occurrence: both true classes >0.5 on "
                  f"{co['both_above_0.5']}/{co['total']} held-out multi-label rows "
                  f"({co['both_above_0.5'] / co['total']:.0%}); "
                  f">0.3 on {co['both_above_0.3']}/{co['total']} "
                  f"({co['both_above_0.3'] / co['total']:.0%})")
        out_dir, n_train = train(feats, head_kind, backbone, args.write,
                                 args.source, CORE, scores)
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
