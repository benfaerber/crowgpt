"""Step E — Single-shot final evaluation on untouched temporal holdout (date >= 2023-01-01).

Fit the pre-declared C and D models ONCE on dev (date < 2023-01-01) and evaluate
EXACTLY ONCE on holdout (date >= 2023-01-01). Reports both the full temporal
holdout and the zero-recordist-overlap subset.

Runs on CPU:
  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0103-caw-level-and-posture-controls/eval_holdout_once.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0103-caw-level"


def eval_caw_holdout(X_tr, y_tr, rid_tr, X_te, y_te, rid_te, C=0.1) -> dict:
    tr_cnt = Counter(rid_tr.tolist())
    wt = np.array([1.0 / tr_cnt[r] for r in rid_tr], dtype=np.float64)
    wt[y_tr == 1] *= 0.5 / max(wt[y_tr == 1].sum(), 1e-12)
    wt[y_tr == 0] *= 0.5 / max(wt[y_tr == 0].sum(), 1e-12)

    sc = StandardScaler().fit(X_tr)
    clf = LogisticRegression(C=C, max_iter=2000, solver="liblinear").fit(
        sc.transform(X_tr), y_tr, sample_weight=wt * len(wt)
    )
    probs = clf.predict_proba(sc.transform(X_te))[:, 1]

    te_cnt = Counter(rid_te.tolist())
    w_te = np.array([1.0 / te_cnt[r] for r in rid_te], dtype=np.float64)
    w_auc = float(roc_auc_score(y_te, probs, sample_weight=w_te))
    w_bal = float(balanced_accuracy_score(y_te, probs >= 0.5, sample_weight=w_te))
    unw_auc = float(roc_auc_score(y_te, probs))

    uniq_r = sorted(te_cnt.keys())
    rec_y = np.array([int(y_te[rid_te == r][0]) for r in uniq_r])
    rec_p = np.array([float(np.mean(probs[rid_te == r])) for r in uniq_r])
    rec_auc = float(roc_auc_score(rec_y, rec_p))
    _, mw_p2 = mannwhitneyu(rec_p[rec_y == 1], rec_p[rec_y == 0], alternative="two-sided")
    _, mw_p1 = mannwhitneyu(rec_p[rec_y == 1], rec_p[rec_y == 0], alternative="greater")

    return {
        "n_caws": int(len(y_te)),
        "n_recordings": int(len(uniq_r)),
        "n_pos_recs": int(rec_y.sum()),
        "n_neg_recs": int((1 - rec_y).sum()),
        "primary_weighted_per_caw_auc": round(w_auc, 4),
        "weighted_bal_acc": round(w_bal, 4),
        "exploratory_unweighted_per_caw_auc": round(unw_auc, 4),
        "exploratory_rec_mean_caw_auc": round(rec_auc, 4),
        "rec_mw_p_two_sided": round(float(mw_p2), 4),
        "rec_mw_p_one_sided": round(float(mw_p1), 4),
    }


def eval_rec_holdout(X_tr, y_tr, X_te, y_te, C=0.05) -> dict:
    if y_te.sum() < 1 or (1 - y_te).sum() < 1:
        return {"n": int(len(y_te)), "n_pos": int(y_te.sum()), "n_neg": int((1 - y_te).sum()), "auc": None}
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=C, max_iter=2000, solver="liblinear", class_weight="balanced"),
    ).fit(X_tr, y_tr)
    probs = clf.predict_proba(X_te)[:, 1]
    auc = float(roc_auc_score(y_te, probs))
    bal = float(balanced_accuracy_score(y_te, probs >= 0.5))
    _, mw_p2 = mannwhitneyu(probs[y_te == 1], probs[y_te == 0], alternative="two-sided")
    _, mw_p1 = mannwhitneyu(probs[y_te == 1], probs[y_te == 0], alternative="greater")
    return {
        "n": int(len(y_te)),
        "n_pos": int(y_te.sum()),
        "n_neg": int((1 - y_te).sum()),
        "auc": round(auc, 4),
        "bal_acc": round(bal, 4),
        "mw_p_two_sided": round(float(mw_p2), 4),
        "mw_p_one_sided": round(float(mw_p1), 4),
    }


def main():
    ho = json.loads((HERE / "holdout_2023.json").read_text())
    zo_ids = set(ho["holdout_zero_overlap_ids"])
    posture_map = {r["id"]: r for r in json.loads((HERE / "posture_labels.json").read_text())}

    recs = json.loads((CACHE_DIR / "recordings.json").read_text())
    caws = json.loads((CACHE_DIR / "caws.json").read_text())
    npz = np.load(CACHE_DIR / "features.npz")

    # Caw arrays
    tr_ci = [i for i, c in enumerate(caws) if c["split"] == "dev"]
    te_ci = [i for i, c in enumerate(caws) if c["split"] == "holdout"]
    te_ci_zo = [i for i in te_ci if caws[i]["rec_id"] in zo_ids]

    X_c44 = npz["caw_acoustic_44d"]
    X_cbn = npz["caw_birdnet_1024d"]
    y_c = np.array([1 if c["context"] == "owl_mobbing" else 0 for c in caws])
    r_c = np.array([c["rec_id"] for c in caws])

    res: dict = {"cutoff_date": ho["cutoff_date"]}

    # Step C primary on holdout
    res["step_c_holdout_full"] = eval_caw_holdout(X_c44[tr_ci], y_c[tr_ci], r_c[tr_ci], X_c44[te_ci], y_c[te_ci], r_c[te_ci], C=0.1)
    res["step_c_holdout_zero_overlap"] = eval_caw_holdout(X_c44[tr_ci], y_c[tr_ci], r_c[tr_ci], X_c44[te_ci_zo], y_c[te_ci_zo], r_c[te_ci_zo], C=0.1)
    # Exploratory isolated-caw BirdNET on holdout
    res["step_c_exploratory_isolated_bn_holdout"] = eval_caw_holdout(X_cbn[tr_ci], y_c[tr_ci], r_c[tr_ci], X_cbn[te_ci], y_c[te_ci], r_c[te_ci], C=0.05)

    # Recording-level pure-crow BirdNET (all & perched-only)
    tr_ri_pure = [i for i, r in enumerate(recs) if r["split"] == "dev" and npz["has_pure"][i]]
    te_ri_pure = [i for i, r in enumerate(recs) if r["split"] == "holdout" and npz["has_pure"][i]]
    te_ri_pure_zo = [i for i in te_ri_pure if recs[i]["id"] in zo_ids]
    y_r = np.array([1 if r["context"] == "owl_mobbing" else 0 for r in recs])
    X_pure = npz["emb_pure_mean"]
    X_all = npz["emb_allcrow_mean"]

    res["exploratory_rec_pure_bn_holdout_full"] = eval_rec_holdout(X_pure[tr_ri_pure], y_r[tr_ri_pure], X_pure[te_ri_pure], y_r[te_ri_pure], C=0.05)
    res["exploratory_rec_pure_bn_holdout_zero_overlap"] = eval_rec_holdout(X_pure[tr_ri_pure], y_r[tr_ri_pure], X_pure[te_ri_pure_zo], y_r[te_ri_pure_zo], C=0.05)

    # Step D primary: perched + pure-crow BirdNET mean on holdout
    tr_pp = [i for i in tr_ri_pure if posture_map.get(recs[i]["id"], {}).get("posture") == "perched"]
    te_pp = [i for i in te_ri_pure if posture_map.get(recs[i]["id"], {}).get("posture") == "perched"]
    te_pp_zo = [i for i in te_pp if recs[i]["id"] in zo_ids]

    res["step_d_holdout_perched_pure_full"] = eval_rec_holdout(X_pure[tr_pp], y_r[tr_pp], X_pure[te_pp], y_r[te_pp], C=0.05)
    res["step_d_holdout_perched_pure_zero_overlap"] = eval_rec_holdout(X_pure[tr_pp], y_r[tr_pp], X_pure[te_pp_zo], y_r[te_pp_zo], C=0.05)

    # Exploratory: perched raptor-masked-only (for comparison)
    tr_pa = [i for i, r in enumerate(recs) if r["split"] == "dev" and posture_map.get(r["id"], {}).get("posture") == "perched"]
    te_pa = [i for i, r in enumerate(recs) if r["split"] == "holdout" and posture_map.get(r["id"], {}).get("posture") == "perched"]
    res["step_d_exploratory_perched_raptor_masked_holdout"] = eval_rec_holdout(X_all[tr_pa], y_r[tr_pa], X_all[te_pa], y_r[te_pa], C=0.05)

    ho_posture = Counter((r["context"], posture_map[r["id"]]["posture"]) for r in recs if r["split"] == "holdout" and r["id"] in posture_map)
    res["holdout_posture_table"] = {f"{k[0]}|{k[1]}": v for k, v in sorted(ho_posture.items())}

    print("=== STEP E — SINGLE-SHOT TEMPORAL HOLDOUT EVALUATION (date >= 2023-01-01) ===")
    print("  Holdout posture table:", dict(sorted(ho_posture.items())))
    for k, v in res.items():
        if k in ("cutoff_date", "holdout_posture_table"):
            continue
        print(f"  {k:50s}: {v}")

    (HERE / "holdout_metrics.json").write_text(json.dumps(res, indent=2))
    print("Saved holdout_metrics.json")


if __name__ == "__main__":
    main()
