"""Does the vendored label corpus lift the label-limited classes?

One-vs-rest AUC per CORE class on its pooled features, multi-label
aware and with **recording-grouped** CV — segments from one recording never span
the train/test split, so the model can't cheat on mic/background/individual.
Compare to the archive-tag baseline that left alarm/song stuck (commit 59f1ce1).

  ../representation/.venv-birdnet/bin/python evaluate.py --dataset all-public
  ../representation/.venv-birdnet/bin/python evaluate.py --dataset all-public --combine
"""

import argparse
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ARCHIVE_CACHE = HERE.parent / "training" / "results" / "pooled_embeddings.npz"

import sys  # noqa: E402

sys.path.insert(0, str(HERE.parent / "training"))
from recover_and_pool import CORE  # noqa: E402  — the one home of the class list
# The archive-tag numbers this corpus has to beat. Begging has none: the archive set
# carries 4 begging recordings against this corpus's 307, so there was never a
# baseline to measure it against — hence the blank column, not a zero.
BASELINE = {"alarm call": 0.681, "call": 0.716, "flight call": 0.87, "song": 0.592}


def load(path, group_prefix):
    d = np.load(path, allow_pickle=True)
    X = d["X"]
    Y = [set(labels) for labels in d["Y"]]
    if "groups" in d.files:
        groups = np.array([f"{group_prefix}:{g}" for g in d["groups"]])
    else:
        # one vector per clip (archive set) -> each row is already its own group
        groups = np.array([f"{group_prefix}:{i}" for i in range(len(Y))])
    return X, Y, groups


def one_vs_rest_auc(X, Y, groups, cls):
    yb = np.array([1 if cls in s else 0 for s in Y])
    pos = int(yb.sum())
    n_groups_pos = len(set(groups[yb == 1]))
    if pos < 8 or pos == len(yb) or n_groups_pos < 3:
        return None, pos
    n_splits = min(5, n_groups_pos, len(set(groups[yb == 0])))
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=0)
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced"),
    )
    try:
        proba = cross_val_predict(clf, X, yb, cv=cv, groups=groups,
                                  method="predict_proba")[:, 1]
    except ValueError:
        return None, pos
    return round(float(roc_auc_score(yb, proba)), 3), pos


def report(name, X, Y, groups):
    print(f"\n=== {name}  (n={len(Y)}, recordings={len(set(groups))}) ===")
    print(f"{'class':<12}{'n+':>6}{'AUC':>8}{'baseline':>10}{'Δ':>8}")
    for cls in CORE:
        auc, pos = one_vs_rest_auc(X, Y, groups, cls)
        base = BASELINE.get(cls)
        shown = "—" if auc is None else f"{auc}"
        base_shown = "—" if base is None else f"{base}"
        delta = "—" if auc is None or base is None else f"{auc - base:+.3f}"
        print(f"{cls:<12}{pos:>6}{shown:>8}{base_shown:>10}{delta:>8}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="all-public")
    parser.add_argument("--combine", action="store_true",
                        help="also evaluate it concatenated with the archive set")
    args = parser.parse_args()

    ct_path = HERE / "results" / f"pooled_embeddings_crowtools_{args.dataset}.npz"
    Xc, Yc, Gc = load(ct_path, "ct")
    report("reviewed labels only", Xc, Yc, Gc)

    if args.combine:
        if not ARCHIVE_CACHE.exists():
            print(f"\n(skipping combine — no archive cache at {ARCHIVE_CACHE})")
            return
        Xx, Yx, Gx = load(ARCHIVE_CACHE, "xc")
        report("archive set only", Xx, Yx, Gx)
        report("combined", np.concatenate([Xx, Xc]), Yx + Yc,
               np.concatenate([Gx, Gc]))


if __name__ == "__main__":
    main()
