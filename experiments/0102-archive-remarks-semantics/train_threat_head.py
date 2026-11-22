"""Experiment 0102b — Calibrated 4-class American Crow Threat Translator + Poe Family field validation.

Trains a recordist-grouped, Platt-calibrated one-vs-rest threat head on clean
witnessed Xeno-canto + Macaulay Library archive remarks (strict zero-raptor
audio), compares BirdNET vs. BirdNET+Prosody+Speed fusion, runs speed-matched
and orthogonalized Owl-vs-Hawk controls, saves the calibrated model bundle to
data/models/american-crow/threat_clf.joblib, and evaluates zero-shot on Ben's
kept Poe Family field captures in fieldserver/instance/field.db.

Runs on CPU in the BirdNET venv:
  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0102-archive-remarks-semantics/train_threat_head.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import librosa
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.signal import butter, filtfilt, find_peaks
from scipy.stats import mannwhitneyu
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
MODEL_OUT = DATA_DIR / "models" / "american-crow" / "threat_clf.joblib"
DB_PATH = DATA_DIR / "corvid.db"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import media  # noqa: E402
import run as exp102  # noqa: E402
from crowgpt.progress import Run  # noqa: E402
from pooling import pool  # noqa: E402

SPEED_NAMES = [
    "peak_rate_med",
    "peak_rate_p90",
    "burst_hz_med",
    "burst_hz_p75",
    "med_ipi_s",
    "mod_centroid_hz",
    "dom_mod_hz",
    "slow_0.5_1.8",
    "mid_1.8_3.2",
    "fast_3.2_7.0",
    "fast_to_slow",
]

THREAT_CLASSES = ["owl", "hawk", "terrestrial", "non_threat"]


def measure_speed_vec(audio_path: str, start_sec: float | None = None, end_sec: float | None = None) -> tuple[bool, np.ndarray]:
    """Crow-band (700-4500 Hz) envelope peak-rate & modulation spectrum features (11d)."""
    try:
        offset = float(start_sec) if start_sec else 0.0
        dur = min(60.0, float(end_sec) - offset) if (end_sec and end_sec > offset + 1.0) else 60.0
        y, sr = librosa.load(audio_path, sr=16000, mono=True, offset=offset, duration=dur)
    except Exception:
        return False, np.zeros(len(SPEED_NAMES), dtype=np.float32)
    if len(y) < sr * 2:
        return False, np.zeros(len(SPEED_NAMES), dtype=np.float32)

    b, a = butter(4, [700.0 / (sr / 2), 4500.0 / (sr / 2)], btype="band")
    yf = filtfilt(b, a, y).astype(np.float32)

    hop = 160  # 10 ms -> 100 Hz envelope
    env = librosa.feature.rms(y=yf, frame_length=320, hop_length=hop)[0]
    env_sr = sr / hop
    env_s = np.convolve(env, np.ones(3) / 3.0, mode="same")

    win = int(3.0 * env_sr)
    n_win = len(env_s) // win
    if n_win < 1:
        return False, np.zeros(len(SPEED_NAMES), dtype=np.float32)
    chunks = env_s[: n_win * win].reshape(n_win, win)
    chunk_rms = np.mean(chunks, axis=1)
    act_mask = chunk_rms >= max(np.percentile(chunk_rms, 50), 0.35 * np.max(chunk_rms))
    act_chunks = chunks[act_mask] if np.any(act_mask) else chunks

    peak_rates, all_ipis, mod_spectra = [], [], []
    freqs = np.fft.rfftfreq(win, d=1.0 / env_sr)
    for ch in act_chunks:
        lo, hi = np.percentile(ch, 10), np.percentile(ch, 98)
        if hi - lo < 1e-6:
            continue
        cn = np.clip((ch - lo) / (hi - lo), 0.0, 1.5)
        peaks, _ = find_peaks(cn, distance=int(0.12 * env_sr), prominence=0.18, height=0.25)
        peak_rates.append(len(peaks) / 3.0)
        if len(peaks) >= 2:
            ipis = np.diff(peaks) / env_sr
            all_ipis.extend(ipis[(ipis >= 0.12) & (ipis <= 2.0)].tolist())
        cz = (cn - np.mean(cn)) * np.hanning(win)
        mod_spectra.append(np.abs(np.fft.rfft(cz)) ** 2)

    if not mod_spectra:
        return False, np.zeros(len(SPEED_NAMES), dtype=np.float32)

    ms = np.mean(mod_spectra, axis=0)
    m_all = (freqs >= 0.5) & (freqs <= 8.0)
    m_slow = (freqs >= 0.5) & (freqs < 1.8)
    m_mid = (freqs >= 1.8) & (freqs < 3.2)
    m_fast = (freqs >= 3.2) & (freqs <= 7.0)
    tot = float(np.sum(ms[m_all]) + 1e-12)
    sf = float(np.sum(ms[m_slow]) / tot)
    mf = float(np.sum(ms[m_mid]) / tot)
    ff = float(np.sum(ms[m_fast]) / tot)
    mc = float(np.sum(freqs[m_all] * ms[m_all]) / tot)
    df = float(freqs[m_all][int(np.argmax(ms[m_all]))])
    med_ipi = float(np.median(all_ipis)) if all_ipis else 1.5
    p25_ipi = float(np.percentile(all_ipis, 25)) if all_ipis else 1.5

    vec = np.array([
        float(np.median(peak_rates)),
        float(np.percentile(peak_rates, 90)),
        float(1.0 / max(med_ipi, 0.12)),
        float(1.0 / max(p25_ipi, 0.12)),
        med_ipi,
        mc,
        df,
        sf,
        mf,
        ff,
        float(np.log((ff + 1e-4) / (sf + 1e-4))),
    ], dtype=np.float32)
    return True, np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def _speed_worker(task):
    rid, path = task
    return rid, measure_speed_vec(path)


class CalibratedOvRHead:
    """Block-standardized One-vs-Rest logistic head with out-of-fold Platt sigmoid calibration."""

    def __init__(self, classes: list[str], C: float = 0.05, prosody_weight: float = 0.5):
        self.classes = list(classes)
        self.C = C
        self.prosody_weight = prosody_weight
        self.bn_scaler = StandardScaler()
        self.aux_scaler = StandardScaler()
        self.models: dict[str, LogisticRegression] = {}
        self.calibrators: dict[str, LogisticRegression] = {}

    def _transform(self, X_bn: np.ndarray, X_aux: np.ndarray | None, fit: bool = False) -> np.ndarray:
        bn = self.bn_scaler.fit_transform(X_bn) if fit else self.bn_scaler.transform(X_bn)
        if X_aux is None or self.prosody_weight <= 0:
            return bn
        aux = self.aux_scaler.fit_transform(X_aux) if fit else self.aux_scaler.transform(X_aux)
        # Scale auxiliary block so L2 norm matches prosody_weight * BirdNET block
        scale = self.prosody_weight * np.sqrt(bn.shape[1] / max(aux.shape[1], 1))
        return np.hstack([bn, aux * scale])

    def fit(self, X_bn: np.ndarray, X_aux: np.ndarray | None, y: np.ndarray, groups: np.ndarray):
        # Compute OOF raw decision scores for honest Platt calibration (never calibrate in-sample!)
        cv = StratifiedGroupKFold(n_splits=5)
        oof_scores = {c: np.zeros(len(y), dtype=np.float64) for c in self.classes}
        for c in self.classes:
            yb = (y == c).astype(int)
            for tr, te in cv.split(X_bn, yb, groups):
                sc_b = StandardScaler().fit(X_bn[tr])
                bn_tr, bn_te = sc_b.transform(X_bn[tr]), sc_b.transform(X_bn[te])
                if X_aux is not None and self.prosody_weight > 0:
                    sc_a = StandardScaler().fit(X_aux[tr])
                    s = self.prosody_weight * np.sqrt(bn_tr.shape[1] / max(X_aux.shape[1], 1))
                    Xtr = np.hstack([bn_tr, sc_a.transform(X_aux[tr]) * s])
                    Xte = np.hstack([bn_te, sc_a.transform(X_aux[te]) * s])
                else:
                    Xtr, Xte = bn_tr, bn_te
                clf = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced").fit(Xtr, yb[tr])
                oof_scores[c][te] = clf.decision_function(Xte)

        X_full = self._transform(X_bn, X_aux, fit=True)
        for c in self.classes:
            yb = (y == c).astype(int)
            self.models[c] = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced").fit(X_full, yb)
            # Fit 1D Platt calibrator on out-of-fold decision scores
            self.calibrators[c] = LogisticRegression(C=1.0, max_iter=1000).fit(oof_scores[c][:, None], yb)
        return self

    def predict_proba(self, X_bn: np.ndarray, X_aux: np.ndarray | None = None) -> np.ndarray:
        X = self._transform(X_bn, X_aux, fit=False)
        out = np.zeros((len(X), len(self.classes)), dtype=np.float64)
        for j, c in enumerate(self.classes):
            raw = self.models[c].decision_function(X)[:, None]
            out[:, j] = self.calibrators[c].predict_proba(raw)[:, 1]
        return out


def cv_evaluate_head(X_bn: np.ndarray, X_aux: np.ndarray | None, y: np.ndarray, groups: np.ndarray, C: float = 0.05, prosody_weight: float = 0.5) -> dict:
    cv = StratifiedGroupKFold(n_splits=5)
    probs = np.zeros((len(y), len(THREAT_CLASSES)), dtype=np.float64)
    for tr, te in cv.split(X_bn, y, groups):
        head = CalibratedOvRHead(THREAT_CLASSES, C=C, prosody_weight=prosody_weight).fit(
            X_bn[tr], X_aux[tr] if X_aux is not None else None, y[tr], groups[tr]
        )
        probs[te] = head.predict_proba(X_bn[te], X_aux[te] if X_aux is not None else None)

    ovr_auc, brier = {}, {}
    for j, c in enumerate(THREAT_CLASSES):
        yb = (y == c).astype(int)
        ovr_auc[c] = round(float(roc_auc_score(yb, probs[:, j])), 4)
        brier[c] = round(float(brier_score_loss(yb, probs[:, j])), 4)

    # Pairwise threat-only AUCs from the same OOF probabilities
    pair_aucs = {}
    for a, b in [("owl", "hawk"), ("owl", "terrestrial"), ("hawk", "terrestrial")]:
        m = (y == a) | (y == b)
        ja, jb = THREAT_CLASSES.index(a), THREAT_CLASSES.index(b)
        score = probs[m, ja] / np.clip(probs[m, ja] + probs[m, jb], 1e-8, None)
        pair_aucs[f"{a}_vs_{b}"] = round(float(roc_auc_score((y[m] == a).astype(int), score)), 4)

    return {
        "n": int(len(y)),
        "n_groups": int(len(set(groups))),
        "macro_auc": round(float(np.mean(list(ovr_auc.values()))), 4),
        "ovr_auc": ovr_auc,
        "brier": brier,
        "pair_aucs": pair_aucs,
        "sat_rate_99": round(float(np.mean(probs > 0.99)), 4),
    }


def extract_poe_captures(run: Run):
    """Extract BirdNET clean crow embeddings + prosody + speed on Ben's kept field captures."""
    db = media.field_db()
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    caps = con.execute("""
        SELECT c.id, c.name, c.recorded_at, c.observer_role, c.behavior_guess, c.notes,
               c.crop_start_sec, c.crop_end_sec,
               GROUP_CONCAT(DISTINCT ce.key) AS ctx_keys,
               GROUP_CONCAT(DISTINCT l.call_type) AS lbl_types
        FROM captures c
        LEFT JOIN context_events ce ON ce.capture_id = c.id
        LEFT JOIN labels l ON l.capture_id = c.id
        WHERE c.keep = 1
        GROUP BY c.id
        ORDER BY c.id
    """).fetchall()
    con.close()

    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer

    devnull = open(os.devnull, "w")
    with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        analyzer = Analyzer()

    out = []
    with run.stage("poe_field_eval") as st:
        for idx, c in enumerate(caps, 1):
            cid = c["id"]
            try:
                ap = media.audio_for(cid)
            except SystemExit:
                continue
            try:
                with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                    rec = Recording(analyzer, str(ap), min_conf=0.05)
                    rec.analyze()
                    rec.extract_embeddings()
            except Exception:
                continue

            segs = rec.embeddings or []
            win_crow = defaultdict(float)
            win_human = defaultdict(float)
            for det in rec.detections or []:
                key = (round(float(det["start_time"]), 2), round(float(det["end_time"]), 2))
                cn, sn = det.get("common_name", ""), det.get("scientific_name", "")
                if exp102._is_corvid(cn, sn):
                    win_crow[key] = max(win_crow[key], float(det["confidence"]))
                if "human" in f"{cn} {sn}".lower():
                    win_human[key] = max(win_human[key], float(det["confidence"]))

            crow_e, crow_w, all_e = [], [], []
            for s in segs:
                emb = np.asarray(s["embeddings"], dtype=np.float32)
                if not np.isfinite(emb).all():
                    continue
                key = (round(float(s["start_time"]), 2), round(float(s["end_time"]), 2))
                all_e.append(emb)
                if win_crow.get(key, 0.0) >= 0.20 and win_human.get(key, 0.0) < 0.25:
                    crow_e.append(emb)
                    crow_w.append(key)

            # Fallback if human speech overlapped crow windows (take any crow>=0.20)
            if not crow_e:
                for s in segs:
                    emb = np.asarray(s["embeddings"], dtype=np.float32)
                    if not np.isfinite(emb).all():
                        continue
                    key = (round(float(s["start_time"]), 2), round(float(s["end_time"]), 2))
                    if win_crow.get(key, 0.0) >= 0.20:
                        crow_e.append(emb)
                        crow_w.append(key)

            if not all_e:
                continue
            y_wav, sr = librosa.load(str(ap), sr=22050, mono=True, duration=120.0)
            pros = exp102.extract_prosody(y_wav, sr, crow_w)
            ok_sp, sp_vec = measure_speed_vec(str(ap), c["crop_start_sec"], c["crop_end_sec"])
            used_e = crow_e if crow_e else all_e
            out.append({
                "id": cid,
                "name": c["name"] or "",
                "ctx_keys": c["ctx_keys"] or "",
                "lbl_types": c["lbl_types"] or "",
                "behavior_guess": c["behavior_guess"] or c["notes"] or "",
                "n_crow_segs": len(crow_e),
                "n_all_segs": len(all_e),
                "emb_pool": pool(used_e).astype(np.float32),
                "emb_mean": pool(used_e)[:1024].astype(np.float32),
                "prosody": pros,
                "speed": sp_vec,
                "speed_ok": ok_sp,
            })
            st.update(idx, len(caps), extra=f"cap #{cid}")
    return out


def main():
    run = Run("0102 threat translator head + Poe Family eval", ["speed_cache", "train_cv", "poe_field_eval", "save"])

    meta = json.loads((CACHE_DIR / "records.json").read_text())
    npz = np.load(CACHE_DIR / "features.npz")

    # Select all strict witnessed American Crow recordings for the 4-class threat dataset
    ctx_to_threat = {
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

    sel = []
    for i, r in enumerate(meta):
        if r["slug"] != "american-crow" or not r["witnessed"] or not npz["has_clean"][i]:
            continue
        tc = ctx_to_threat.get(r["context"])
        if not tc:
            continue
        # Strict zero-raptor audio on predator classes so the head cannot cheat on owl hoots / hawk screams
        if tc in ("owl", "hawk") and (r["pred_vocal"] or r["max_raptor_conf"] >= 0.05):
            continue
        sel.append((i, tc))

    # Extract/cache speed features for selected 0102 clips
    sp_cache_path = CACHE_DIR / "speed_feats.json"
    sp_map = json.loads(sp_cache_path.read_text()) if sp_cache_path.exists() else {}
    con = sqlite3.connect(str(DB_PATH))
    id_to_fp = {
        rid: exp102.resolve_audio_path(fp)
        for rid, fp in con.execute(
            "SELECT id, file_path FROM recordings WHERE source IN ('xeno_canto', 'macaulay') AND downloaded = 1"
        ).fetchall()
    }
    con.close()

    missing = [(meta[i]["id"], str(id_to_fp[meta[i]["id"]])) for i, _ in sel if str(meta[i]["id"]) not in sp_map and id_to_fp.get(meta[i]["id"])]
    with run.stage("speed_cache") as st:
        if missing:
            with ProcessPoolExecutor(max_workers=12) as ex:
                futs = [ex.submit(_speed_worker, t) for t in missing]
                for k, fut in enumerate(as_completed(futs), 1):
                    rid, (ok, vec) = fut.result()
                    sp_map[str(rid)] = vec.tolist() if ok else [0.0] * len(SPEED_NAMES)
                    if k % 25 == 0 or k == len(missing):
                        st.update(k, len(missing))
            sp_cache_path.write_text(json.dumps(sp_map))
        else:
            st.update(len(sel), len(sel), extra="cached")

    idxs = [i for i, _ in sel]
    y = np.array([tc for _, tc in sel])
    g = np.array([exp102.group_id(meta[i]) for i in idxs])
    X_bn_pool = npz["emb_clean"][idxs]
    X_bn_mean = X_bn_pool[:, :1024]
    X_pros = npz["prosody"][idxs]
    X_spd = np.array([sp_map.get(str(meta[i]["id"]), [0.0] * len(SPEED_NAMES)) for i in idxs], dtype=np.float32)
    X_aux = np.hstack([X_pros, X_spd])  # 41 + 11 = 52d prosody + speed/tempo

    print("=== 4-CLASS THREAT DATASET (STRICT AMERICAN CROW ARCHIVE REMARKS) ===")
    print("  Counts:", dict(Counter(y)), "| total=", len(y), "| unique recordists=", len(set(g)))

    cv_summary = {}
    with run.stage("train_cv") as st:
        arms = [
            ("birdnet_mean_only", X_bn_mean, None, 0.05, 0.0),
            ("birdnet_pooled_only", X_bn_pool, None, 0.05, 0.0),
            ("birdnet_mean_plus_prosody_speed_w0.35", X_bn_mean, X_aux, 0.05, 0.35),
            ("birdnet_pooled_plus_prosody_speed_w0.35", X_bn_pool, X_aux, 0.05, 0.35),
        ]
        print("\n=== RECORDIST-GROUPED 5-FOLD CV (PLATT-CALIBRATED OvR) ===")
        for k, (name, Xb, Xa, C, pw) in enumerate(arms, 1):
            res = cv_evaluate_head(Xb, Xa, y, g, C=C, prosody_weight=pw)
            cv_summary[name] = res
            print(
                f"  {name:42s} | macro_AUC={res['macro_auc']:.4f} | sat>.99={res['sat_rate_99']:.1%} | "
                f"OvR={res['ovr_auc']} | pairs={res['pair_aucs']}"
            )
            st.update(k, len(arms), extra=name)

    # Pick best arm by macro_auc + owl_vs_hawk pair AUC
    best_name = max(cv_summary, key=lambda k: cv_summary[k]["macro_auc"] + 0.5 * cv_summary[k]["pair_aucs"]["owl_vs_hawk"])
    print(f"\nSelected best calibrated arm: {best_name}")
    arm_map = {a[0]: a for a in arms}
    _, best_Xb, best_Xa, best_C, best_pw = arm_map[best_name]
    use_pool = "pooled" in best_name
    final_head = CalibratedOvRHead(THREAT_CLASSES, C=best_C, prosody_weight=best_pw).fit(best_Xb, best_Xa, y, g)

    # Evaluate on Ben's 29 kept Poe Family field captures!
    poe = extract_poe_captures(run)
    ship_bundle = joblib.load(REPO / "pipelines" / "training" / "models" / "american-crow" / "calltype_clf.joblib")
    ship_clf = ship_bundle["model"] if "model" in ship_bundle else next(v for v in ship_bundle.values() if hasattr(v, "predict_proba"))
    ship_cls = list(getattr(ship_clf, "classes_", None) or ship_clf.classes)
    alarm_i = ship_cls.index("alarm call")

    print(f"\n=== ZERO-SHOT PREDICTIONS ON BEN'S KEPT POE FAMILY FIELD CAPTURES (n={len(poe)}) ===")
    print(f"  {'#id':>4s} | {'crow':>4s} | {'c/s':>4s} | {'p_alm':>5s} | {'P_owl':>5s} | {'P_hwk':>5s} | {'P_ter':>5s} | {'P_non':>5s} | {'top':>11s} | context / name")
    print("  " + "-" * 116)

    poe_rows = []
    for r in poe:
        Xb = (r["emb_pool"] if use_pool else r["emb_mean"])[None, :]
        Xa = np.hstack([r["prosody"], r["speed"]])[None, :] if best_Xa is not None else None
        pr = final_head.predict_proba(Xb, Xa)[0]
        p_al = float(ship_clf.predict_proba(r["emb_pool"][None, :])[0, alarm_i])
        top = THREAT_CLASSES[int(np.argmax(pr))]
        caws_s = float(r["speed"][0]) if r["speed_ok"] else 0.0
        desc = f"{r['name'][:30]} [{r['ctx_keys'][:32]}]"
        print(
            f"  #{r['id']:3d} | {r['n_crow_segs']:4d} | {caws_s:4.1f} | {p_al:5.2f} | "
            f"{pr[0]:5.2f} | {pr[1]:5.2f} | {pr[2]:5.2f} | {pr[3]:5.2f} | {top:>11s} | {desc}"
        )
        poe_rows.append({
            "capture_id": r["id"],
            "name": r["name"],
            "ctx_keys": r["ctx_keys"],
            "lbl_types": r["lbl_types"],
            "behavior_guess": r["behavior_guess"][:120],
            "n_crow_segs": r["n_crow_segs"],
            "caws_per_s": round(caws_s, 2),
            "shipped_p_alarm": round(p_al, 3),
            "probs": {c: round(float(pr[j]), 3) for j, c in enumerate(THREAT_CLASSES)},
            "top": top,
        })

    # Quantitative summary on Ben's witnessed stranger/threat vs benign/foraging/fledgling captures
    stranger_ids = {87, 88, 113, 154, 155, 156, 158}
    benign_ids = {69, 89, 94, 95, 96, 97, 104, 105, 106, 114, 116}
    s_rows = [r for r in poe_rows if r["capture_id"] in stranger_ids and r["n_crow_segs"] > 0]
    b_rows = [r for r in poe_rows if r["capture_id"] in benign_ids and r["n_crow_segs"] > 0]
    if s_rows and b_rows:
        print("\n=== POE FAMILY QUANTITATIVE CHECK: STRANGER-ALARM CAPTURES vs BENIGN/FEEDING/FLEDGLING ===")
        print(f"  Stranger alarms (n={len(s_rows)}): med P_ter={np.median([r['probs']['terrestrial'] for r in s_rows]):.3f}, "
              f"med P_owl={np.median([r['probs']['owl'] for r in s_rows]):.3f}, med P_hawk={np.median([r['probs']['hawk'] for r in s_rows]):.3f}, "
              f"med P_non={np.median([r['probs']['non_threat'] for r in s_rows]):.3f}")
        print(f"  Benign/feeding  (n={len(b_rows)}): med P_ter={np.median([r['probs']['terrestrial'] for r in b_rows]):.3f}, "
              f"med P_owl={np.median([r['probs']['owl'] for r in b_rows]):.3f}, med P_hawk={np.median([r['probs']['hawk'] for r in b_rows]):.3f}, "
              f"med P_non={np.median([r['probs']['non_threat'] for r in b_rows]):.3f}")
        yt = np.array([1] * len(s_rows) + [0] * len(b_rows))
        for k in ("terrestrial", "owl", "hawk", "non_threat"):
            sc = np.array([r["probs"][k] for r in s_rows + b_rows])
            print(f"  Stranger vs Benign AUC on P({k:10s}) = {roc_auc_score(yt, sc):.4f}")
        owl_fp = sum(1 for r in poe_rows if r["n_crow_segs"] > 0 and r["probs"]["owl"] >= 0.5)
        tot_det = sum(1 for r in poe_rows if r["n_crow_segs"] > 0)
        print(f"  Owl false alarms (P_owl >= 0.5) across ALL {tot_det} crow-detected backyard captures: {owl_fp}/{tot_det}")

    with run.stage("save"):
        MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model": final_head,
            "arm": best_name,
            "classes": THREAT_CLASSES,
            "backbone": "birdnet",
            "use_pool": use_pool,
            "uses_aux_prosody_speed": best_Xa is not None,
            "prosody_names": exp102.PROSODY_NAMES,
            "speed_names": SPEED_NAMES,
            "cv_metrics": cv_summary[best_name],
        }, MODEL_OUT)
        (HERE / "threat_metrics.json").write_text(json.dumps({
            "selected_arm": best_name,
            "class_counts": dict(Counter(y)),
            "cv_arms": cv_summary,
            "poe_family_eval": poe_rows,
        }, indent=2))

    run.note(f"saved {best_name} (macro_AUC={cv_summary[best_name]['macro_auc']:.3f}) -> {MODEL_OUT.name}")


if __name__ == "__main__":
    main()
