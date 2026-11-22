"""Steps C & D — Dev-only evaluation (date < 2023-01-01) for Experiment 0103.

Strictly asserts that zero holdout recordings (date >= 2023-01-01) enter any
feature scaling, matching, cross-validation, or diagnostic.

Runs on CPU:
  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0103-caw-level-and-posture-controls/eval_dev.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0103-caw-level"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402


def group_key(rec: dict) -> str:
    r = (rec.get("recordist") or "").strip().lower()
    return r if r else f"rec_{rec['id']}"


def parse_meta_vec(rec: dict) -> np.ndarray:
    """Metadata-only null features: duration_s, lat, lng, month sin/cos, hour sin/cos, source."""
    dur = float(rec.get("duration_s") or 0.0)
    lat = float(rec["lat"]) if rec.get("lat") is not None else 0.0
    lng = float(rec["lng"]) if rec.get("lng") is not None else 0.0
    dt = rec.get("date") or ""
    try:
        m = int(dt.split("-")[1])
        m_sin, m_cos = math.sin(2 * math.pi * m / 12.0), math.cos(2 * math.pi * m / 12.0)
    except Exception:
        m_sin, m_cos = 0.0, 0.0
    tm = rec.get("time") or ""
    try:
        parts = tm.replace(":", " ").split()
        hr = float(parts[0]) + (float(parts[1]) / 60.0 if len(parts) > 1 else 0.0)
        h_sin, h_cos = math.sin(2 * math.pi * hr / 24.0), math.cos(2 * math.pi * hr / 24.0)
    except Exception:
        h_sin, h_cos = 0.0, 0.0
    src = 1.0 if rec.get("source") == "macaulay" else 0.0
    return np.array([dur, lat, lng, m_sin, m_cos, h_sin, h_cos, src], dtype=np.float32)


def eval_recording_cv(
    X: np.ndarray,
    y: np.ndarray,
    g: np.ndarray,
    C: float = 0.05,
    n_perm: int = 400,
    seed: int = 42,
    st=None,
) -> dict:
    n_splits = min(5, int(y.sum()), int((1 - y).sum()), len(set(g)))
    if n_splits < 2:
        return {"n": int(len(y)), "auc": None, "bal_acc": None, "perm_p": None}
    cv = StratifiedGroupKFold(n_splits=n_splits)

    def score_once(yy: np.ndarray) -> tuple[float, float]:
        probs = np.zeros(len(yy), dtype=np.float64)
        clf = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=C, max_iter=2000, solver="liblinear", class_weight="balanced"),
        )
        for tr, te in cv.split(X, yy, g):
            clf.fit(X[tr], yy[tr])
            probs[te] = clf.predict_proba(X[te])[:, 1]
        return float(roc_auc_score(yy, probs)), float(balanced_accuracy_score(yy, probs >= 0.5))

    auc, bal = score_once(y)
    perm_p = None
    perm_mean = None
    if n_perm > 0:
        rng = np.random.default_rng(seed)
        uniq_g = np.array(sorted(set(g)))
        g_y = np.array([int(np.round(np.mean(y[g == ug]))) for ug in uniq_g])
        ge, vals = 0, []
        for k in range(1, n_perm + 1):
            shuf = rng.permutation(g_y)
            gm = dict(zip(uniq_g, shuf))
            yp = np.array([gm[gi] for gi in g])
            if yp.sum() < n_splits or (1 - yp).sum() < n_splits:
                continue
            try:
                ap, _ = score_once(yp)
                vals.append(ap)
                if ap >= auc:
                    ge += 1
            except Exception:
                continue
            if st is not None and (k % 50 == 0 or k == n_perm):
                st.update(k, n_perm, extra=f"auc={auc:.3f}")
        perm_p = (ge + 1) / (len(vals) + 1)
        perm_mean = float(np.mean(vals)) if vals else 0.5

    return {
        "n": int(len(y)),
        "n_pos": int(y.sum()),
        "n_neg": int((1 - y).sum()),
        "n_groups": int(len(set(g))),
        "auc": round(auc, 4),
        "bal_acc": round(bal, 4),
        "perm_p": round(float(perm_p), 4) if perm_p is not None else None,
        "perm_mean": round(float(perm_mean), 4) if perm_mean is not None else None,
    }


def eval_caw_cv(
    X_caw: np.ndarray,
    y_caw: np.ndarray,
    rec_ids: np.ndarray,
    g_caw: np.ndarray,
    C: float = 0.1,
    n_perm: int = 400,
    seed: int = 42,
    st=None,
) -> dict:
    """Pre-declared primary Step C evaluator: inverse-recording-weighted per-caw ROC-AUC,
    5-fold StratifiedGroupKFold holding out whole recordings by recordist.
    Also reports exploratory unweighted per-caw AUC and recording-averaged caw AUC.
    """
    # Compute inverse-recording-count sample weights
    rec_counts = Counter(rec_ids.tolist())
    w_caw = np.array([1.0 / rec_counts[rid] for rid in rec_ids], dtype=np.float64)

    # Split strictly at the RECORDING level grouped by RECORDIST so whole recordings & recordists stay together
    uniq_rids = sorted(rec_counts.keys())
    rid_to_y = {rid: int(y_caw[rec_ids == rid][0]) for rid in uniq_rids}
    rid_to_g = {rid: str(g_caw[rec_ids == rid][0]) for rid in uniq_rids}
    r_y = np.array([rid_to_y[r] for r in uniq_rids])
    r_g = np.array([rid_to_g[r] for r in uniq_rids])

    n_splits = min(5, int(r_y.sum()), int((1 - r_y).sum()), len(set(r_g)))
    cv = StratifiedGroupKFold(n_splits=n_splits)

    def score_once(y_by_rid: dict[int, int]) -> tuple[float, float, float, float]:
        yy_rec = np.array([y_by_rid[r] for r in uniq_rids])
        yy_caw = np.array([y_by_rid[rid] for rid in rec_ids])
        probs = np.zeros(len(yy_caw), dtype=np.float64)
        for tr_r, te_r in cv.split(np.zeros((len(uniq_rids), 1)), yy_rec, r_g):
            tr_set = {uniq_rids[i] for i in tr_r}
            te_set = {uniq_rids[i] for i in te_r}
            tr_m = np.array([rid in tr_set for rid in rec_ids])
            te_m = np.array([rid in te_set for rid in rec_ids])
            sc = StandardScaler().fit(X_caw[tr_m])
            # Combine inverse-recording weight with balanced class weight on training fold
            wt = w_caw[tr_m].copy()
            pos_w = wt[yy_caw[tr_m] == 1].sum()
            neg_w = wt[yy_caw[tr_m] == 0].sum()
            wt[yy_caw[tr_m] == 1] *= 0.5 / max(pos_w, 1e-12)
            wt[yy_caw[tr_m] == 0] *= 0.5 / max(neg_w, 1e-12)
            clf = LogisticRegression(C=C, max_iter=2000, solver="liblinear").fit(
                sc.transform(X_caw[tr_m]), yy_caw[tr_m], sample_weight=wt * len(wt)
            )
            probs[te_m] = clf.predict_proba(sc.transform(X_caw[te_m]))[:, 1]

        w_auc = float(roc_auc_score(yy_caw, probs, sample_weight=w_caw))
        w_bal = float(balanced_accuracy_score(yy_caw, probs >= 0.5, sample_weight=w_caw))
        unw_auc = float(roc_auc_score(yy_caw, probs))
        # Recording-averaged mean caw probability
        rec_p = np.array([float(np.mean(probs[rec_ids == r])) for r in uniq_rids])
        rec_auc = float(roc_auc_score(yy_rec, rec_p))
        return w_auc, w_bal, unw_auc, rec_auc

    w_auc, w_bal, unw_auc, rec_auc = score_once(rid_to_y)

    perm_p = None
    perm_mean = None
    if n_perm > 0:
        rng = np.random.default_rng(seed)
        uniq_g = np.array(sorted(set(r_g)))
        g_y = np.array([int(np.round(np.mean(r_y[r_g == ug]))) for ug in uniq_g])
        ge, vals = 0, []
        for k in range(1, n_perm + 1):
            shuf = rng.permutation(g_y)
            gm = dict(zip(uniq_g, shuf))
            y_by_r = {r: gm[rid_to_g[r]] for r in uniq_rids}
            yp_r = np.array([y_by_r[r] for r in uniq_rids])
            if yp_r.sum() < n_splits or (1 - yp_r).sum() < n_splits:
                continue
            try:
                ap, _, _, _ = score_once(y_by_r)
                vals.append(ap)
                if ap >= w_auc:
                    ge += 1
            except Exception:
                continue
            if st is not None and (k % 50 == 0 or k == n_perm):
                st.update(k, n_perm, extra=f"w_auc={w_auc:.3f}")
        perm_p = (ge + 1) / (len(vals) + 1)
        perm_mean = float(np.mean(vals)) if vals else 0.5

    return {
        "n_caws": int(len(y_caw)),
        "n_recordings": int(len(uniq_rids)),
        "n_pos_recs": int(r_y.sum()),
        "n_neg_recs": int((1 - r_y).sum()),
        "n_groups": int(len(set(r_g))),
        "primary_weighted_per_caw_auc": round(w_auc, 4),
        "weighted_bal_acc": round(w_bal, 4),
        "exploratory_unweighted_per_caw_auc": round(unw_auc, 4),
        "exploratory_rec_mean_caw_auc": round(rec_auc, 4),
        "perm_p": round(float(perm_p), 4) if perm_p is not None else None,
        "perm_mean": round(float(perm_mean), 4) if perm_mean is not None else None,
    }


def match_density_1to1(recs: list[dict]) -> list[int]:
    """1-to-1 Hungarian matching between owl and hawk dev recordings on
    (pure_crow_frac, duty_cycle, log1p(n_pure_crow_w)).
    """
    cov = np.array(
        [[r["pure_crow_frac"], r["duty_cycle"], math.log1p(r["n_pure_crow_w"])] for r in recs],
        dtype=np.float64,
    )
    cov_z = StandardScaler().fit_transform(cov)
    owls = [i for i, r in enumerate(recs) if r["context"] == "owl_mobbing"]
    hawks = [i for i, r in enumerate(recs) if r["context"] == "hawk_mobbing"]
    cost = np.linalg.norm(cov_z[owls][:, None, :] - cov_z[hawks][None, :, :], axis=2)
    ri, ci = linear_sum_assignment(cost)
    # Keep pairs within reasonable standardized distance (< 1.5 SD)
    keep = []
    for a, b in zip(ri, ci):
        if cost[a, b] <= 1.8:
            keep.append(recs[owls[a]]["id"])
            keep.append(recs[hawks[b]]["id"])
    return sorted(keep)


def main():
    ho = json.loads((HERE / "holdout_2023.json").read_text())
    ho_ids = set(ho["holdout_ids"])
    posture_map = {r["id"]: r for r in json.loads((HERE / "posture_labels.json").read_text())}

    recs = json.loads((CACHE_DIR / "recordings.json").read_text())
    caws = json.loads((CACHE_DIR / "caws.json").read_text())
    npz = np.load(CACHE_DIR / "features.npz")

    # HARD GUARD: strictly filter to dev split only (date < 2023-01-01)
    dev_rec_idxs = [i for i, r in enumerate(recs) if r["split"] == "dev"]
    assert all(recs[i]["id"] not in ho_ids for i in dev_rec_idxs), "Holdout leak!"
    dev_recs = [recs[i] for i in dev_rec_idxs]
    rec_by_id = {r["id"]: (i, r) for i, r in enumerate(recs)}

    dev_caw_idxs = [i for i, c in enumerate(caws) if c["split"] == "dev"]
    assert all(caws[i]["rec_id"] not in ho_ids for i in dev_caw_idxs), "Holdout caw leak!"

    run = Run("0103 dev evaluation (Steps C & D)", ["step_c_full", "step_c_density_matched", "step_c_exploratory", "step_d_posture"])
    report: dict = {"split": "dev_only (date < 2023-01-01)"}

    # --- STEP C: CAW-LEVEL PRIMARY ---
    X_caw_44 = npz["caw_acoustic_44d"][dev_caw_idxs]
    X_caw_bn = npz["caw_birdnet_1024d"][dev_caw_idxs]
    y_caw = np.array([1 if caws[i]["context"] == "owl_mobbing" else 0 for i in dev_caw_idxs])
    rid_caw = np.array([caws[i]["rec_id"] for i in dev_caw_idxs])
    g_caw = np.array([group_key(rec_by_id[caws[i]["rec_id"]][1]) for i in dev_caw_idxs])

    # Metadata null on the exact recordings that have >= 1 segmented pure-crow caw
    caw_rec_ids = sorted(set(rid_caw.tolist()))
    caw_recs = [rec_by_id[rid][1] for rid in caw_rec_ids]
    X_meta_c = np.stack([parse_meta_vec(r) for r in caw_recs])
    y_meta_c = np.array([1 if r["context"] == "owl_mobbing" else 0 for r in caw_recs])
    g_meta_c = np.array([group_key(r) for r in caw_recs])

    with run.stage("step_c_full") as st:
        c_primary = eval_caw_cv(X_caw_44, y_caw, rid_caw, g_caw, C=0.1, n_perm=400, seed=42, st=st)
        c_meta = eval_recording_cv(X_meta_c, y_meta_c, g_meta_c, C=0.5, n_perm=0)
        report["step_c_primary_full_dev"] = c_primary
        report["step_c_metadata_null"] = c_meta
        print("=== STEP C (PRIMARY): CAW-LEVEL OWL vs HAWK (ALL-NON-CROW MASKED, DEV) ===")
        print(f"  caw_acoustic_44d: primary_w_AUC={c_primary['primary_weighted_per_caw_auc']:.4f} "
              f"(perm_p={c_primary['perm_p']:.4f}, perm_mean={c_primary['perm_mean']:.3f}) | "
              f"unw_caw={c_primary['exploratory_unweighted_per_caw_auc']:.4f} | "
              f"rec_mean={c_primary['exploratory_rec_mean_caw_auc']:.4f} | "
              f"caws={c_primary['n_caws']}, recs={c_primary['n_recordings']} ({c_primary['n_pos_recs']} owl / {c_primary['n_neg_recs']} hawk), groups={c_primary['n_groups']}")
        print(f"  metadata null:    AUC={c_meta['auc']:.4f} (n={c_meta['n']})")

    # Density-matched subset of dev recordings with >= 1 segmented pure-crow caw
    with run.stage("step_c_density_matched") as st:
        dm_ids = set(match_density_1to1(caw_recs))
        dm_recs = [r for r in caw_recs if r["id"] in dm_ids]
        cov_dm = np.array([[r["pure_crow_frac"], r["duty_cycle"], math.log1p(r["n_pure_crow_w"])] for r in dm_recs])
        y_dm_r = np.array([1 if r["context"] == "owl_mobbing" else 0 for r in dm_recs])
        g_dm_r = np.array([group_key(r) for r in dm_recs])
        dm_cov_check = eval_recording_cv(cov_dm, y_dm_r, g_dm_r, C=1.0, n_perm=0)

        dm_mask = np.array([rid in dm_ids for rid in rid_caw])
        c_dm = eval_caw_cv(X_caw_44[dm_mask], y_caw[dm_mask], rid_caw[dm_mask], g_caw[dm_mask], C=0.1, n_perm=400, seed=43, st=st)
        report["step_c_density_matched_dev"] = c_dm
        report["step_c_density_covariate_check"] = dm_cov_check
        print("\n=== STEP C (DENSITY-MATCHED SUBSET, DEV) ===")
        print(f"  density covariates check AUC={dm_cov_check['auc']:.4f} (n={dm_cov_check['n']}: {dm_cov_check['n_pos']} owl / {dm_cov_check['n_neg']} hawk)")
        print(f"  caw_acoustic_44d: primary_w_AUC={c_dm['primary_weighted_per_caw_auc']:.4f} "
              f"(perm_p={c_dm['perm_p']:.4f}) | unw_caw={c_dm['exploratory_unweighted_per_caw_auc']:.4f} | "
              f"rec_mean={c_dm['exploratory_rec_mean_caw_auc']:.4f} | caws={c_dm['n_caws']}, recs={c_dm['n_recordings']}")

    # Exploratory C diagnostics: isolated-caw BirdNET + bystander-masking comparison on recording-level BirdNET
    with run.stage("step_c_exploratory") as st:
        c_iso_bn = eval_caw_cv(X_caw_bn, y_caw, rid_caw, g_caw, C=0.05, n_perm=200, seed=44, st=st)
        c_iso_bn_dm = eval_caw_cv(X_caw_bn[dm_mask], y_caw[dm_mask], rid_caw[dm_mask], g_caw[dm_mask], C=0.05, n_perm=200, seed=45)

        # Compare recording-level BirdNET mean: raptor-masked-only (emb_allcrow_mean) vs strictly all-non-crow-masked (emb_pure_mean)
        pure_dev_idxs = [i for i in dev_rec_idxs if npz["has_pure"][i]]
        y_pd = np.array([1 if recs[i]["context"] == "owl_mobbing" else 0 for i in pure_dev_idxs])
        g_pd = np.array([group_key(recs[i]) for i in pure_dev_idxs])
        rec_bn_allcrow = eval_recording_cv(npz["emb_allcrow_mean"][pure_dev_idxs], y_pd, g_pd, C=0.05, n_perm=200, seed=46)
        rec_bn_pure = eval_recording_cv(npz["emb_pure_mean"][pure_dev_idxs], y_pd, g_pd, C=0.05, n_perm=400, seed=47)

        # Density-matched recording-level pure-crow BirdNET
        dm_rec_idxs = [rec_by_id[rid][0] for rid in sorted(dm_ids)]
        y_dm_bn = np.array([1 if recs[i]["context"] == "owl_mobbing" else 0 for i in dm_rec_idxs])
        g_dm_bn = np.array([group_key(recs[i]) for i in dm_rec_idxs])
        rec_bn_pure_dm = eval_recording_cv(npz["emb_pure_mean"][dm_rec_idxs], y_dm_bn, g_dm_bn, C=0.05, n_perm=400, seed=48)

        # Top bystander species by context in dev
        by_owl, by_hawk = Counter(), Counter()
        owl_has_by, hawk_has_by = 0, 0
        owl_tot, hawk_tot = 0, 0
        for r in dev_recs:
            sp = r.get("bystander_species") or {}
            if r["context"] == "owl_mobbing":
                owl_tot += 1
                if sp:
                    owl_has_by += 1
                for k, v in sp.items():
                    by_owl[k] += 1
            else:
                hawk_tot += 1
                if sp:
                    hawk_has_by += 1
                for k, v in sp.items():
                    by_hawk[k] += 1

        report["step_c_exploratory"] = {
            "birdnet_isolated_caw_full": c_iso_bn,
            "birdnet_isolated_caw_density_matched": c_iso_bn_dm,
            "recording_bn_raptor_masked_only_same_recs": rec_bn_allcrow,
            "recording_bn_all_noncrow_masked": rec_bn_pure,
            "recording_bn_all_noncrow_masked_density_matched": rec_bn_pure_dm,
            "bystander_prevalence_dev": {
                "owl_recs_with_any_bystander": f"{owl_has_by}/{owl_tot}",
                "hawk_recs_with_any_bystander": f"{hawk_has_by}/{hawk_tot}",
                "top_owl_bystanders": by_owl.most_common(10),
                "top_hawk_bystanders": by_hawk.most_common(10),
            },
        }
        print("\n=== STEP C (EXPLORATORY DIAGNOSTICS, DEV) ===")
        print(f"  isolated-caw BirdNET (full):  w_AUC={c_iso_bn['primary_weighted_per_caw_auc']:.4f} (p={c_iso_bn['perm_p']:.4f}) | rec_mean={c_iso_bn['exploratory_rec_mean_caw_auc']:.4f}")
        print(f"  isolated-caw BirdNET (DM):    w_AUC={c_iso_bn_dm['primary_weighted_per_caw_auc']:.4f} (p={c_iso_bn_dm['perm_p']:.4f}) | rec_mean={c_iso_bn_dm['exploratory_rec_mean_caw_auc']:.4f}")
        print(f"  Rec BirdNET (raptor-masked only, n={rec_bn_allcrow['n']}): AUC={rec_bn_allcrow['auc']:.4f} (p={rec_bn_allcrow['perm_p']:.4f})")
        print(f"  Rec BirdNET (ALL-non-crow masked, n={rec_bn_pure['n']}): AUC={rec_bn_pure['auc']:.4f} (p={rec_bn_pure['perm_p']:.4f})")
        print(f"  Rec BirdNET (ALL-non-crow + DM,   n={rec_bn_pure_dm['n']}): AUC={rec_bn_pure_dm['auc']:.4f} (p={rec_bn_pure_dm['perm_p']:.4f})")
        print(f"  Bystanders in dev: owl={owl_has_by}/{owl_tot} {by_owl.most_common(5)} | hawk={hawk_has_by}/{hawk_tot} {by_hawk.most_common(5)}")

    # --- STEP D: ARCHIVE POSTURE CONTROL (PERCHED vs FLYING) ---
    with run.stage("step_d_posture") as st:
        posture_table_dev = Counter((r["context"], posture_map[r["id"]]["posture"]) for r in dev_recs if r["id"] in posture_map)
        perched_pure_idxs = [
            i for i in dev_rec_idxs
            if npz["has_pure"][i] and posture_map.get(recs[i]["id"], {}).get("posture") == "perched"
        ]
        y_pp = np.array([1 if recs[i]["context"] == "owl_mobbing" else 0 for i in perched_pure_idxs])
        g_pp = np.array([group_key(recs[i]) for i in perched_pure_idxs])
        d_primary = eval_recording_cv(npz["emb_pure_mean"][perched_pure_idxs], y_pp, g_pp, C=0.05, n_perm=400, seed=49, st=st)
        d_meta = eval_recording_cv(np.stack([parse_meta_vec(recs[i]) for i in perched_pure_idxs]), y_pp, g_pp, C=0.5, n_perm=0)

        # Also check perched-only on raptor-masked-only (0102-style) for direct comparison
        perched_all_idxs = [i for i in dev_rec_idxs if posture_map.get(recs[i]["id"], {}).get("posture") == "perched"]
        y_pa = np.array([1 if recs[i]["context"] == "owl_mobbing" else 0 for i in perched_all_idxs])
        g_pa = np.array([group_key(recs[i]) for i in perched_all_idxs])
        d_raptor_only = eval_recording_cv(npz["emb_allcrow_mean"][perched_all_idxs], y_pa, g_pa, C=0.05, n_perm=400, seed=50)

        # Exploratory: caw-level on perched-only dev clips
        perched_ids = {recs[i]["id"] for i in perched_pure_idxs}
        pmask = np.array([rid in perched_ids for rid in rid_caw])
        d_caw_44 = eval_caw_cv(X_caw_44[pmask], y_caw[pmask], rid_caw[pmask], g_caw[pmask], C=0.1, n_perm=400, seed=51) if pmask.sum() > 10 else {}
        d_caw_bn = eval_caw_cv(X_caw_bn[pmask], y_caw[pmask], rid_caw[pmask], g_caw[pmask], C=0.05, n_perm=200, seed=52) if pmask.sum() > 10 else {}

        # Exploratory: perched vs flying WITHIN hawk_mobbing (dev)
        hawk_pf_idxs = [
            i for i in dev_rec_idxs
            if npz["has_pure"][i] and recs[i]["context"] == "hawk_mobbing"
            and posture_map.get(recs[i]["id"], {}).get("posture") in ("perched", "flying")
        ]
        y_hpf = np.array([1 if posture_map[recs[i]["id"]]["posture"] == "perched" else 0 for i in hawk_pf_idxs])
        g_hpf = np.array([group_key(recs[i]) for i in hawk_pf_idxs])
        d_hawk_pf = eval_recording_cv(npz["emb_pure_mean"][hawk_pf_idxs], y_hpf, g_hpf, C=0.05, n_perm=200, seed=53) if (y_hpf.sum() >= 3 and (1 - y_hpf).sum() >= 3) else {"n": len(hawk_pf_idxs), "note": "too few perched/flying hawks"}

        report["step_d_posture_table_dev"] = {f"{k[0]}|{k[1]}": v for k, v in sorted(posture_table_dev.items())}
        report["step_d_primary_perched_pure_bn"] = d_primary
        report["step_d_metadata_null"] = d_meta
        report["step_d_exploratory"] = {
            "perched_raptor_masked_only_bn": d_raptor_only,
            "perched_caw_acoustic_44d": d_caw_44,
            "perched_caw_isolated_bn": d_caw_bn,
            "within_hawk_perched_vs_flying": d_hawk_pf,
        }
        print("\n=== STEP D (PRIMARY): ARCHIVE POSTURE CONTROL — PERCHED OWL vs PERCHED HAWK (DEV) ===")
        print("  Dev posture table:", dict(sorted(posture_table_dev.items())))
        print(f"  PRIMARY (perched + pure-crow BN mean): AUC={d_primary['auc']:.4f} (perm_p={d_primary['perm_p']:.4f}) | "
              f"n={d_primary['n']} ({d_primary['n_pos']} owl / {d_primary['n_neg']} hawk, groups={d_primary['n_groups']}) | meta_null={d_meta['auc']:.4f}")
        print(f"  Exploratory (perched + raptor-masked BN): AUC={d_raptor_only['auc']:.4f} (p={d_raptor_only['perm_p']:.4f}, n={d_raptor_only['n']})")
        if d_caw_44:
            print(f"  Exploratory (perched caw_acoustic_44d):   w_AUC={d_caw_44['primary_weighted_per_caw_auc']:.4f} (p={d_caw_44['perm_p']:.4f}, caws={d_caw_44['n_caws']}, recs={d_caw_44['n_recordings']})")
        if d_caw_bn:
            print(f"  Exploratory (perched isolated-caw BN):    w_AUC={d_caw_bn['primary_weighted_per_caw_auc']:.4f} (p={d_caw_bn['perm_p']:.4f})")
        print(f"  Exploratory (within-hawk perched vs flying): {d_hawk_pf}")

    (HERE / "dev_metrics.json").write_text(json.dumps(report, indent=2))
    run.note("saved dev_metrics.json (holdout untouched)")


if __name__ == "__main__":
    main()
