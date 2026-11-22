"""Experiment 0102c — Perch 2.0 vs. BirdNET head-to-head on American Crow threat translation.

Tests whether Google DeepMind's Perch 2.0 (1536-d, 5 s windows at 32 kHz) beats
BirdNET on:
  1. 4-class calibrated Threat Translator (owl / hawk / terrestrial / non_threat)
     on the expanded strict witnessed Xeno-canto + Macaulay American Crow set;
  2. Strict zero-raptor Owl vs. Hawk (raw, 1-to-1 speed-matched, and in-fold
     orthogonalized against speed + density + p(alarm));
  3. Zero-shot generalization to Ben's 29 kept Poe Family field captures.

Runs on GPU in the Perch venv:
  pipelines/representation/perch/.venv/bin/python \
      experiments/0102-archive-remarks-semantics/benchmark_perch.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import warnings
from collections import Counter
from pathlib import Path

os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import joblib
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0102-archive-remarks"
DB_PATH = DATA_DIR / "corvid.db"
os.environ.setdefault("KAGGLEHUB_CACHE", str(DATA_DIR / "models"))

sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import media  # noqa: E402
from crowgpt.progress import Run  # noqa: E402
from pooling import pool  # noqa: E402

THREAT_CLASSES = ["owl", "hawk", "terrestrial", "non_threat"]
CTX_TO_THREAT = {
    "owl_mobbing": "owl",
    "hawk_mobbing": "hawk",
    "human_disturbance": "terrestrial",
    "mammal_scold": "terrestrial",
    "begging": "non_threat",
    "rattle_social": "non_threat",
    "food_foraging": "non_threat",
    "roost_gathering": "non_threat",
    "flight_contact": "non_threat",
}


def resolve_audio_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    p = Path(raw_path)
    if p.exists():
        return p
    if "/data/" in raw_path:
        cand = DATA_DIR / raw_path.split("/data/", 1)[1]
        if cand.exists():
            return cand
    return None


def group_id(r: dict) -> str:
    rec = (r.get("recordist") or "").strip().lower()
    return f"rec:{rec}" if rec else f"grp:{r.get('group_key') or r['id']}"


def decode_32k(path: Path, max_sec: float = 60.0, start_sec: float | None = None, end_sec: float | None = None) -> np.ndarray:
    """Fast mono 32 kHz float32 decode via ffmpeg."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error"]
    if start_sec and start_sec > 0:
        cmd += ["-ss", f"{start_sec:.3f}"]
    cmd += ["-i", str(path)]
    dur = max_sec
    if end_sec and end_sec > (start_sec or 0) + 1.0:
        dur = min(max_sec, end_sec - (start_sec or 0))
    cmd += ["-t", f"{dur:.3f}", "-ac", "1", "-ar", "32000", "-f", "f32le", "-"]
    res = subprocess.run(cmd, capture_output=True, timeout=45)
    if res.returncode != 0 or not res.stdout:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def embed_clip_perch(model, y: np.ndarray, sr: int = 32000, win_s: float = 5.0) -> np.ndarray | None:
    """Slice into non-overlapping 5 s windows, embed each with Perch 2.0, return mean+std+max (4608-d)."""
    win = int(sr * win_s)
    if len(y) < int(sr * 0.5):
        return None
    vecs = []
    n_chunks = max(1, (len(y) + win - 1) // win)
    for k in range(n_chunks):
        chunk = y[k * win : (k + 1) * win]
        if len(chunk) < int(sr * 0.5) and k > 0:
            break
        if len(chunk) < win:
            chunk = np.pad(chunk, (0, win - len(chunk)))
        out = model.embed(chunk)
        emb = np.asarray(out.embeddings, dtype=np.float32).reshape(-1)
        if np.isfinite(emb).all():
            vecs.append(emb)
    if not vecs:
        return None
    return pool(vecs).astype(np.float32)


class CalibratedOvRHead:
    """Block-standardized One-vs-Rest logistic head with out-of-fold Platt calibration."""

    def __init__(self, classes: list[str], C: float = 0.05, block_weights: list[float] | None = None):
        self.classes = list(classes)
        self.C = C
        self.block_weights = block_weights
        self.scalers: list[StandardScaler] = []
        self.models: dict[str, LogisticRegression] = {}
        self.calibrators: dict[str, LogisticRegression] = {}

    def _concat(self, blocks: list[np.ndarray], fit: bool = False) -> np.ndarray:
        weights = self.block_weights or [1.0] * len(blocks)
        ref_dim = blocks[0].shape[1]
        parts = []
        if fit:
            self.scalers = []
        for j, (B, w) in enumerate(zip(blocks, weights)):
            if fit:
                sc = StandardScaler().fit(B)
                self.scalers.append(sc)
                Z = sc.transform(B)
            else:
                Z = self.scalers[j].transform(B)
            scale = w * np.sqrt(ref_dim / max(B.shape[1], 1))
            parts.append(Z * scale)
        return np.hstack(parts)

    def fit(self, blocks: list[np.ndarray], y: np.ndarray, groups: np.ndarray):
        cv = StratifiedGroupKFold(n_splits=5)
        oof = {c: np.zeros(len(y), dtype=np.float64) for c in self.classes}
        weights = self.block_weights or [1.0] * len(blocks)
        ref_dim = blocks[0].shape[1]
        for c in self.classes:
            yb = (y == c).astype(int)
            for tr, te in cv.split(blocks[0], yb, groups):
                p_tr, p_te = [], []
                for B, w in zip(blocks, weights):
                    sc = StandardScaler().fit(B[tr])
                    s = w * np.sqrt(ref_dim / max(B.shape[1], 1))
                    p_tr.append(sc.transform(B[tr]) * s)
                    p_te.append(sc.transform(B[te]) * s)
                clf = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced").fit(np.hstack(p_tr), yb[tr])
                oof[c][te] = clf.decision_function(np.hstack(p_te))
        X_full = self._concat(blocks, fit=True)
        for c in self.classes:
            yb = (y == c).astype(int)
            self.models[c] = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced").fit(X_full, yb)
            self.calibrators[c] = LogisticRegression(C=1.0, max_iter=1000).fit(oof[c][:, None], yb)
        return self

    def predict_proba(self, blocks: list[np.ndarray]) -> np.ndarray:
        X = self._concat(blocks, fit=False)
        out = np.zeros((len(X), len(self.classes)), dtype=np.float64)
        for j, c in enumerate(self.classes):
            out[:, j] = self.calibrators[c].predict_proba(self.models[c].decision_function(X)[:, None])[:, 1]
        return out


def cv_eval(blocks: list[np.ndarray], y: np.ndarray, g: np.ndarray, C: float = 0.05, weights: list[float] | None = None) -> dict:
    cv = StratifiedGroupKFold(n_splits=5)
    probs = np.zeros((len(y), len(THREAT_CLASSES)), dtype=np.float64)
    for tr, te in cv.split(blocks[0], y, g):
        hd = CalibratedOvRHead(THREAT_CLASSES, C=C, block_weights=weights).fit([B[tr] for B in blocks], y[tr], g[tr])
        probs[te] = hd.predict_proba([B[te] for B in blocks])
    ovr = {c: round(float(roc_auc_score((y == c).astype(int), probs[:, j])), 4) for j, c in enumerate(THREAT_CLASSES)}
    brier = {c: round(float(brier_score_loss((y == c).astype(int), probs[:, j])), 4) for j, c in enumerate(THREAT_CLASSES)}
    pairs = {}
    for a, b in [("owl", "hawk"), ("owl", "terrestrial"), ("hawk", "terrestrial")]:
        m = (y == a) | (y == b)
        ja, jb = THREAT_CLASSES.index(a), THREAT_CLASSES.index(b)
        sc = probs[m, ja] / np.clip(probs[m, ja] + probs[m, jb], 1e-8, None)
        pairs[f"{a}_vs_{b}"] = round(float(roc_auc_score((y[m] == a).astype(int), sc)), 4)
    return {
        "n": int(len(y)),
        "macro_auc": round(float(np.mean(list(ovr.values()))), 4),
        "ovr_auc": ovr,
        "brier": brier,
        "pair_aucs": pairs,
        "sat_99": round(float(np.mean(probs > 0.99)), 4),
    }


def eval_bin(X, y, g, C=0.05):
    cv = StratifiedGroupKFold(n_splits=5)
    clf = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000, class_weight="balanced"))
    probs = np.zeros(len(y))
    for tr, te in cv.split(X, y, g):
        clf.fit(X[tr], y[tr])
        probs[te] = clf.predict_proba(X[te])[:, 1]
    return round(float(roc_auc_score(y, probs)), 4), round(float(balanced_accuracy_score(y, probs >= 0.5)), 4)


def main():
    run = Run("0102 Perch 2.0 threat benchmark", ["load_perch", "embed_archive", "embed_poe", "evaluate"])

    meta = json.loads((CACHE_DIR / "records.json").read_text())
    npz = np.load(CACHE_DIR / "features.npz")

    # Select expanded strict witnessed American Crow threat set
    sel = []
    for i, r in enumerate(meta):
        if r["slug"] != "american-crow" or not r["witnessed"] or not npz["has_clean"][i]:
            continue
        tc = CTX_TO_THREAT.get(r["context"])
        if not tc:
            continue
        if tc in ("owl", "hawk") and (r["pred_vocal"] or r["max_raptor_conf"] >= 0.05):
            continue
        sel.append((i, tc))

    sel_ids = [meta[i]["id"] for i, _ in sel]
    perch_cache = CACHE_DIR / "perch_threat.npz"
    poe_cache = CACHE_DIR / "poe_perch.npz"

    con = sqlite3.connect(str(DB_PATH))
    id_to_fp = {
        rid: resolve_audio_path(fp)
        for rid, fp in con.execute(
            "SELECT id, file_path FROM recordings WHERE source IN ('xeno_canto', 'macaulay') AND downloaded = 1"
        ).fetchall()
    }
    con.close()

    # Load existing Poe Family metadata from threat_metrics.json (or field.db)
    fdb = sqlite3.connect(str(media.field_db()))
    fdb.row_factory = sqlite3.Row
    poe_caps = fdb.execute("""
        SELECT c.id, c.name, c.crop_start_sec, c.crop_end_sec,
               GROUP_CONCAT(DISTINCT ce.key) AS ctx_keys,
               GROUP_CONCAT(DISTINCT l.call_type) AS lbl_types
        FROM captures c
        LEFT JOIN context_events ce ON ce.capture_id = c.id
        LEFT JOIN labels l ON l.capture_id = c.id
        WHERE c.keep = 1
        GROUP BY c.id ORDER BY c.id
    """).fetchall()
    fdb.close()

    model = None
    have_arch = {}
    if perch_cache.exists():
        d = np.load(perch_cache)
        for rid, emb in zip(d["ids"].tolist(), d["embs"]):
            have_arch[int(rid)] = emb

    need_arch = [rid for rid in sel_ids if rid not in have_arch]
    need_poe = not poe_cache.exists()

    if need_arch or need_poe:
        with run.stage("load_perch"):
            from perch_hoplite.zoo import model_configs
            model = model_configs.load_model_by_name("perch_v2")
    else:
        with run.stage("load_perch") as st:
            st.update(1, 1, extra="cached")

    with run.stage("embed_archive") as st:
        if need_arch:
            for k, rid in enumerate(need_arch, 1):
                fp = id_to_fp.get(rid)
                if fp and fp.exists():
                    y_wav = decode_32k(fp, max_sec=60.0)
                    emb = embed_clip_perch(model, y_wav)
                    if emb is not None:
                        have_arch[rid] = emb
                if k % 20 == 0 or k == len(need_arch):
                    st.update(k, len(need_arch), extra=f"ok={len(have_arch)}")
            ids_arr = np.array(sorted(have_arch.keys()), dtype=np.int64)
            embs_arr = np.stack([have_arch[int(rid)] for rid in ids_arr])
            np.savez_compressed(perch_cache, ids=ids_arr, embs=embs_arr)
        else:
            st.update(len(sel_ids), len(sel_ids), extra="cached")

    with run.stage("embed_poe") as st:
        if need_poe:
            poe_ids, poe_embs = [], []
            for k, c in enumerate(poe_caps, 1):
                try:
                    ap = media.audio_for(c["id"])
                except SystemExit:
                    continue
                y_wav = decode_32k(ap, max_sec=90.0, start_sec=c["crop_start_sec"], end_sec=c["crop_end_sec"])
                emb = embed_clip_perch(model, y_wav)
                if emb is not None:
                    poe_ids.append(c["id"])
                    poe_embs.append(emb)
                st.update(k, len(poe_caps), extra=f"cap #{c['id']}")
            np.savez_compressed(poe_cache, ids=np.array(poe_ids, dtype=np.int64), embs=np.stack(poe_embs))
        else:
            st.update(len(poe_caps), len(poe_caps), extra="cached")

    # Evaluation
    with run.stage("evaluate"):
        sp_map = json.loads((CACHE_DIR / "speed_feats.json").read_text()) if (CACHE_DIR / "speed_feats.json").exists() else {}
        valid = [(i, tc) for i, tc in sel if meta[i]["id"] in have_arch]
        idxs = [i for i, _ in valid]
        y = np.array([tc for _, tc in valid])
        g = np.array([group_id(meta[i]) for i in idxs])

        X_bn_pool = npz["emb_clean"][idxs]
        X_bn_mean = X_bn_pool[:, :1024]
        X_pc_pool = np.stack([have_arch[meta[i]["id"]] for i in idxs])
        X_pc_mean = X_pc_pool[:, :1536]
        X_pros = npz["prosody"][idxs]
        X_spd = np.array([sp_map.get(str(meta[i]["id"]), [0.0] * 11) for i in idxs], dtype=np.float32)
        X_aux = np.hstack([X_pros, X_spd])

        print(f"\n=== EXPANDED 4-CLASS THREAT DATASET (n={len(y)}, {len(set(g))} recordists): {dict(Counter(y))} ===")
        arms = [
            ("birdnet_pooled_only", [X_bn_pool], 0.05, [1.0]),
            ("birdnet_pooled_plus_pros_speed", [X_bn_pool, X_aux], 0.05, [1.0, 0.35]),
            ("perch_mean_only (1536d)", [X_pc_mean], 0.05, [1.0]),
            ("perch_pooled_only (4608d)", [X_pc_pool], 0.05, [1.0]),
            ("perch_pooled_plus_pros_speed", [X_pc_pool, X_aux], 0.05, [1.0, 0.35]),
            ("perch_plus_birdnet_pooled", [X_pc_pool, X_bn_pool], 0.05, [1.0, 0.7]),
            ("perch_plus_birdnet_plus_pros_speed", [X_pc_pool, X_bn_pool, X_aux], 0.05, [1.0, 0.7, 0.35]),
        ]
        results = {}
        print("\n=== HEAD-TO-HEAD 5-FOLD RECORDIST-GROUPED CV (PLATT-CALIBRATED OvR) ===")
        for name, blks, C, wts in arms:
            res = cv_eval(blks, y, g, C=C, weights=wts)
            results[name] = res
            print(
                f"  {name:36s} | macro={res['macro_auc']:.4f} | "
                f"owl={res['ovr_auc']['owl']:.3f} hawk={res['ovr_auc']['hawk']:.3f} "
                f"ter={res['ovr_auc']['terrestrial']:.3f} non={res['ovr_auc']['non_threat']:.3f} | "
                f"o/h={res['pair_aucs']['owl_vs_hawk']:.3f} o/t={res['pair_aucs']['owl_vs_terrestrial']:.3f} h/t={res['pair_aucs']['hawk_vs_terrestrial']:.3f}"
            )

        # Speed-matched & orthogonalized Owl vs Hawk on Perch vs BirdNET!
        oh_mask = (y == "owl") | (y == "hawk")
        y_oh = (y[oh_mask] == "owl").astype(int)
        g_oh = g[oh_mask]
        X_bn_oh = X_bn_mean[oh_mask]
        X_pc_oh = X_pc_mean[oh_mask]
        X_pcp_oh = X_pc_pool[oh_mask]
        X_pr_oh = X_pros[oh_mask]
        X_sp_oh = X_spd[oh_mask]

        # 1-to-1 speed matching on (peak_rate_med, peak_rate_p90, mod_centroid)
        cov_sp = X_sp_oh[:, [0, 1, 5]]
        Xs = StandardScaler().fit_transform(cov_sp)
        pos_i, neg_i = np.where(y_oh == 1)[0], np.where(y_oh == 0)[0]
        D = np.sqrt(np.mean((Xs[pos_i, None, :] - Xs[None, neg_i, :]) ** 2, axis=2))
        ri, ci = linear_sum_assignment(D)
        m_sp = np.array([int(pos_i[a]) for a, b in zip(ri, ci) if D[a, b] <= 0.6] + [int(neg_i[b]) for a, b in zip(ri, ci) if D[a, b] <= 0.6])

        print(f"\n=== STRICT OWL vs HAWK: PERCH 2.0 vs BIRDNET (RAW n={len(y_oh)} & SPEED-MATCHED n={len(m_sp)}) ===")
        for label, X in [
            ("BirdNET mean (1024d)", X_bn_oh),
            ("Perch 2.0 mean (1536d)", X_pc_oh),
            ("Perch 2.0 pooled (4608d)", X_pcp_oh),
            ("Perch + BirdNET mean (2560d)", np.hstack([X_pc_oh, X_bn_oh])),
        ]:
            a_raw, _ = eval_bin(X, y_oh, g_oh, 0.05)
            a_sm, _ = eval_bin(X[m_sp], y_oh[m_sp], g_oh[m_sp], 0.05)
            # In-fold orthogonalization against speed + crow_frac + duty_cycle + duration
            Z = np.column_stack([X_sp_oh[:, [0, 1, 2, 5]], X_pr_oh[:, [0, 1, 5]]])
            cv = StratifiedGroupKFold(n_splits=5)
            probs = np.zeros(len(y_oh))
            for tr, te in cv.split(X, y_oh, g_oh):
                sz = StandardScaler().fit(Z[tr])
                sx = StandardScaler().fit(X[tr])
                reg = Ridge(alpha=10.0).fit(sz.transform(Z[tr]), sx.transform(X[tr]))
                Rtr = sx.transform(X[tr]) - reg.predict(sz.transform(Z[tr]))
                Rte = sx.transform(X[te]) - reg.predict(sz.transform(Z[te]))
                probs[te] = LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced").fit(Rtr, y_oh[tr]).predict_proba(Rte)[:, 1]
            a_orth = round(float(roc_auc_score(y_oh, probs)), 4)
            print(f"  {label:30s} | raw={a_raw:.4f} | speed_matched={a_sm:.4f} | orth_residual={a_orth:.4f}")

        # Poe Family zero-shot test with Perch 2.0 pooled!
        pd = np.load(poe_cache)
        poe_emb_map = {int(cid): emb for cid, emb in zip(pd["ids"].tolist(), pd["embs"])}
        poe_prev = {r["capture_id"]: r for r in json.loads((HERE / "threat_metrics.json").read_text())["poe_family_eval"]}

        perch_head = CalibratedOvRHead(THREAT_CLASSES, C=0.05, block_weights=[1.0]).fit([X_pc_pool], y, g)
        stranger_ids = {87, 88, 113, 154, 155, 156, 158}
        benign_ids = {69, 89, 94, 95, 96, 97, 104, 105, 106, 114, 116}

        poe_res = []
        for cid, emb in sorted(poe_emb_map.items()):
            if cid not in poe_prev or poe_prev[cid]["n_crow_segs"] == 0:
                continue
            pr = perch_head.predict_proba([emb[None, :]])[0]
            poe_res.append({"id": cid, "probs": {c: round(float(pr[j]), 3) for j, c in enumerate(THREAT_CLASSES)}})

        s_r = [r for r in poe_res if r["id"] in stranger_ids]
        b_r = [r for r in poe_res if r["id"] in benign_ids]
        yt = np.array([1] * len(s_r) + [0] * len(b_r))
        print(f"\n=== POE FAMILY ZERO-SHOT: PERCH 2.0 POOLED (n={len(poe_res)} crow-detected) ===")
        for c in THREAT_CLASSES:
            sc = np.array([r["probs"][c] for r in s_r + b_r])
            print(f"  Stranger vs Benign AUC on P({c:10s}) = {roc_auc_score(yt, sc):.4f} "
                  f"(stranger med={np.median([r['probs'][c] for r in s_r]):.3f}, benign med={np.median([r['probs'][c] for r in b_r]):.3f})")
        owl_fp = sum(1 for r in poe_res if r["probs"]["owl"] >= 0.5)
        print(f"  Owl false alarms (P_owl >= 0.5): {owl_fp}/{len(poe_res)}")

        # Save Perch head + benchmark metrics
        out_model = DATA_DIR / "models" / "american-crow" / "threat_perch_clf.joblib"
        joblib.dump({"model": perch_head, "classes": THREAT_CLASSES, "backbone": "perch_v2", "cv": results["perch_pooled_only (4608d)"]}, out_model)
        (HERE / "perch_threat_metrics.json").write_text(json.dumps({
            "class_counts": dict(Counter(y)),
            "cv_arms": results,
            "poe_perch_eval": poe_res,
        }, indent=2))

    run.note("Perch 2.0 threat benchmark complete")


if __name__ == "__main__":
    main()
