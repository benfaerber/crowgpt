"""0119 step 2: evaluate pre-registered call-consequence pragmatics tests (Primaries A, B, C + secondaries).

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0119-do-calls-predict-what-happens-next/run.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import warnings
from collections import defaultdict
from importlib import util
from pathlib import Path

import joblib
import librosa
import numpy as np
from scipy.stats import wilcoxon
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0119-call-consequences"
WINDOWS = CACHE / "windows"
FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"

EXP103 = REPO / "experiments" / "0103-caw-level-and-posture-controls"
EXP109 = REPO / "experiments" / "0109-can-the-number-of-crows-be-heard"
EXP111 = REPO / "experiments" / "0111-how-often-does-the-begging-head-cry-wolf"

SR = 22050
WINDOW_S = 3.0
MIN_CELL = 20

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp103 = load_module("exp103_0119", EXP103 / "extract_caws.py")
exp109 = load_module("exp109_0119", EXP109 / "run.py")
exp111 = load_module("exp111_0119", EXP111 / "run.py")


def head(C: float = 0.05):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, class_weight="balanced", max_iter=3000))


def holm_adjust(p_map: dict[str, float]) -> dict[str, float]:
    items = sorted(p_map.items(), key=lambda kv: kv[1])
    m = len(items)
    out = {}
    running = 0.0
    for idx, (name, p) in enumerate(items):
        adj = min(1.0, p * (m - idx))
        running = max(running, adj)
        out[name] = round(float(running), 5)
    return out


class FrozenReferenceHeads:
    """Fix T_single, T_crowd, and T_beg strictly on 0109 / 0111 before reading any 0119 window."""

    def __init__(self):
        self.count_head = joblib.load(DATA_DIR / "experiments" / "0109-crow-count" / "count_head.joblib")
        saved = np.load(DATA_DIR / "experiments" / "0109-crow-count" / "segments.npz")
        from corpus import LabelCorpus

        segs = [s for s in LabelCorpus().labeled_segments() if s.flags.get("crowCount") in (1, 2, 4)]
        segs = [s for s, present in zip(segs, saved["present"]) if present]
        data = object.__new__(exp109.CountedSegments)
        data.segments = segs
        data.X = saved["X"].astype(np.float32)
        data.count = np.array([s.flags["crowCount"] for s in segs])
        data.several = (data.count > 1).astype(int)
        data.groups = data._groups()

        oof = np.zeros(len(data.several), dtype=np.float64)
        for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(
            data.X, data.several, data.groups
        ):
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000),
            ).fit(data.X[tr], data.several[tr])
            oof[te] = clf.predict_proba(data.X[te])[:, 1]

        # T_single: largest cut where >= 90% of segments below T_single are one crow (0113 rule)
        asc = np.argsort(oof)
        one = 1 - data.several[asc]
        prec_one = np.cumsum(one) / np.arange(1, len(one) + 1)
        pass_one = np.flatnonzero(prec_one >= 0.90)
        last_one = int(pass_one.max())
        self.T_single = float(oof[asc][last_one + 1]) if last_one + 1 < len(oof) else 1.0

        # T_crowd: smallest cut where >= 80% of segments at/above T_crowd are several crows
        desc = np.argsort(oof)[::-1]
        sev = data.several[desc]
        prec_sev = np.cumsum(sev) / np.arange(1, len(sev) + 1)
        pass_sev = np.flatnonzero((prec_sev >= 0.80) & (np.arange(1, len(sev) + 1) >= 20))
        if len(pass_sev) > 0:
            last_sev = int(pass_sev.max())
            self.T_crowd = float(oof[desc][last_sev])
            crowd_mode = "80pct_several_precision"
        else:
            self.T_crowd = float(np.quantile(oof, 0.85))
            crowd_mode = "oof_q85_fallback"

        above = oof >= self.T_crowd
        below = oof < self.T_single

        self.beg_head = exp111.FrozenBeggingHead()
        self.T_beg = float(self.beg_head.threshold)

        self.report = {
            "T_single": round(self.T_single, 4),
            "one_crow_precision_below_T_single": round(float((1 - data.several[below]).mean()), 4),
            "one_crow_recall_below_T_single": round(float(below[data.several == 0].mean()), 4),
            "T_crowd": round(self.T_crowd, 4),
            "T_crowd_mode": crowd_mode,
            "several_precision_above_T_crowd": round(float(data.several[above].mean()), 4),
            "several_recall_above_T_crowd": round(float(above[data.several == 1].mean()), 4),
            "segments_above_T_crowd": int(above.sum()),
            "T_beg_archive_90pct": round(self.T_beg, 4),
        }

    def p_several(self, emb: np.ndarray) -> np.ndarray:
        return self.count_head.predict_proba(emb.astype(np.float32))[:, 1].astype(np.float32)

    def s_beg(self, emb: np.ndarray) -> np.ndarray:
        return self.beg_head.score(emb.astype(np.float32)).astype(np.float32)


def load_window_table(name: str, refs: FrozenReferenceHeads) -> dict | None:
    p = WINDOWS / f"{name}.npz"
    if not p.exists():
        return None
    d = np.load(p)
    emb = d["embedding"].astype(np.float32)
    if len(emb) == 0:
        return None
    return {
        "file_duration": float(d["file_duration"]),
        "start": d["start"].astype(np.float32),
        "corvid": d["corvid"].astype(np.float32),
        "american_crow": d["american_crow"].astype(np.float32),
        "raptor": d["raptor"].astype(np.float32),
        "other": d["other"].astype(np.float32),
        "embedding": emb,
        "rms_db": d["rms_db"].astype(np.float32),
        "crow_rms_db": d["crow_rms_db"].astype(np.float32),
        "noise_p10_db": d["noise_p10_db"].astype(np.float32),
        "snr_db": d["snr_db"].astype(np.float32),
        "duty_u": d["duty_u"].astype(np.float32),
        "zero_frac": d["zero_frac"].astype(np.float32),
        "p_several": refs.p_several(emb),
        "s_beg": refs.s_beg(emb),
    }


def span_indices(starts: np.ndarray, t0: float, t1: float) -> np.ndarray | None:
    expected = int(round((t1 - t0) / WINDOW_S))
    idx = np.flatnonzero((starts >= t0 - 0.08) & (starts <= t1 - WINDOW_S + 0.08))
    if len(idx) != expected:
        return None
    return idx


def live_tail(tbl: dict, focal_idx: int, t0: float, t1: float) -> tuple[bool, str]:
    if t1 > tbl["file_duration"] - 1.0 + 1e-3:
        return False, "eof_margin"
    post_idx = span_indices(tbl["start"], t0, t1)
    if post_idx is None or len(post_idx) == 0:
        return False, "missing_windows"
    if np.any(tbl["zero_frac"][post_idx] >= 0.05):
        return False, "zero_dropout"
    pre_med = float(np.median(tbl["noise_p10_db"][: focal_idx + 1]))
    post_med = float(np.median(tbl["noise_p10_db"][post_idx]))
    if abs(post_med - pre_med) > 6.0:
        return False, "noise_floor_shift"
    return True, "ok"


def build_events(catalogue: list[dict], refs: FrozenReferenceHeads, stage):
    events_A_pos, events_A_neg = [], []
    pairs_B = []
    events_C = []
    hazard_C_rows = []
    audit = defaultdict(int)

    n_total = len(catalogue)
    for k, rec in enumerate(catalogue, 1):
        if k % 250 == 0 or k == n_total:
            stage.update(k, n_total, extra=f"A+={len(events_A_pos)} B={len(pairs_B)} C={len(events_C)}")

        tbl = load_window_table(f"r{rec['id']}", refs)
        if tbl is None:
            audit["missing_npz"] += 1
            continue

        starts = tbl["start"]
        dur = tbl["file_duration"]
        pure_single = (
            (tbl["american_crow"] >= 0.25)
            & (tbl["other"] < 0.05)
            & (tbl["raptor"] < 0.05)
            & (tbl["p_several"] < refs.T_single)
        )
        crow_any = tbl["corvid"] >= 0.25

        # ---- Primary A: Single-Bird Recruitment (earliest eligible focal window per recording) ----
        rec_a_pos = None
        rec_a_neg = None
        for i, t in enumerate(starts):
            t_f = float(t)
            if t_f < 6.0 or not pure_single[i]:
                continue
            pre_idx = np.flatnonzero((starts >= max(0.0, t_f - 9.0) - 0.08) & (starts < t_f - 0.08))
            if len(pre_idx) < 2:
                continue
            # Pre-span: zero multi-crow windows and raptor < 0.05
            if np.any(tbl["raptor"][pre_idx] >= 0.05):
                continue
            if np.any(crow_any[pre_idx] & (tbl["p_several"][pre_idx] >= refs.T_single)):
                continue
            # Also block any non-crow window that somehow scored high p_several? Pre-reg: "all crow windows have P_several < T_single"
            ok_tail, reason = live_tail(tbl, i, t_f + 3.0, t_f + 24.0)
            if not ok_tail:
                audit[f"A_reject_{reason}"] += 1
                continue
            post_6_24 = span_indices(starts, t_f + 6.0, t_f + 24.0)
            post_3_24 = span_indices(starts, t_f + 3.0, t_f + 24.0)
            if post_6_24 is None or post_3_24 is None:
                continue

            n_crowd = int(np.sum(crow_any[post_6_24] & (tbl["p_several"][post_6_24] >= refs.T_crowd)))
            any_multi = bool(np.any(crow_any[post_3_24] & (tbl["p_several"][post_3_24] >= refs.T_single)))

            ev = {
                "rec_id": rec["id"],
                "path": rec["path"],
                "observer": rec["observer"],
                "t": t_f,
                "idx": int(i),
                "embedding": tbl["embedding"][i],
                "p_several": float(tbl["p_several"][i]),
                "duty_u": float(tbl["duty_u"][i]),
                "crow_rms_db": float(tbl["crow_rms_db"][i]),
                "snr_db": float(tbl["snr_db"][i]),
                "s_beg": float(tbl["s_beg"][i]),
                "post_crowd_windows": n_crowd,
            }
            if n_crowd >= 2 and rec_a_pos is None:
                rec_a_pos = {**ev, "y": 1}
                break
            if not any_multi and rec_a_neg is None:
                rec_a_neg = {**ev, "y": 0}

        if rec_a_pos is not None:
            events_A_pos.append(rec_a_pos)
        elif rec_a_neg is not None:
            events_A_neg.append(rec_a_neg)

        # ---- Primary B: Within-Recording Continuing vs Terminal Single-Bird Call ----
        stop_cand = None
        # Search from latest window backwards for terminal pure single-bird call before >=15s verified silence
        for i in range(len(starts) - 1, -1, -1):
            t_stop = float(starts[i])
            if t_stop < 12.0 or not pure_single[i]:
                continue
            ok_tail, reason = live_tail(tbl, i, t_stop + 3.0, t_stop + 18.0)
            if not ok_tail:
                audit[f"B_reject_{reason}"] += 1
                continue
            post_idx = span_indices(starts, t_stop + 3.0, t_stop + 18.0)
            if post_idx is None:
                continue
            if float(np.max(tbl["corvid"][post_idx])) < 0.10 and float(np.mean(tbl["duty_u"][post_idx])) < 0.05:
                stop_cand = (i, t_stop)
                break

        if stop_cand is not None:
            i_stop, t_stop = stop_cand
            # Pre-declared rule: choose the earliest qualifying continuing pure single-crow window <= t_stop - 12.0s
            cont_cand = None
            for j, t_cont in enumerate(starts):
                t_c = float(t_cont)
                if t_c > t_stop - 12.0 + 1e-3:
                    break
                if not pure_single[j]:
                    continue
                c_post = span_indices(starts, t_c + 3.0, t_c + 18.0)
                if c_post is None:
                    continue
                if int(np.sum(crow_any[c_post])) >= 2:
                    cont_cand = (j, t_c)
                    break
            if cont_cand is not None:
                i_cont, t_cont = cont_cand
                pairs_B.append({
                    "rec_id": rec["id"],
                    "path": rec["path"],
                    "observer": rec["observer"],
                    "t_cont": t_cont,
                    "t_stop": t_stop,
                    "cont": {
                        "t": t_cont,
                        "embedding": tbl["embedding"][i_cont],
                        "crow_rms_db": float(tbl["crow_rms_db"][i_cont]),
                        "snr_db": float(tbl["snr_db"][i_cont]),
                        "p_several": float(tbl["p_several"][i_cont]),
                        "duty_u": float(tbl["duty_u"][i_cont]),
                    },
                    "stop": {
                        "t": t_stop,
                        "embedding": tbl["embedding"][i_stop],
                        "crow_rms_db": float(tbl["crow_rms_db"][i_stop]),
                        "snr_db": float(tbl["snr_db"][i_stop]),
                        "p_several": float(tbl["p_several"][i_stop]),
                        "duty_u": float(tbl["duty_u"][i_stop]),
                    },
                })

        # ---- Primary C & S_C1: Parental Intervention / Begging Cessation ----
        verified_beg = int(np.sum(crow_any & (tbl["s_beg"] >= 0.0))) >= 2
        if verified_beg:
            seen_outcomes: set[int] = set()
            for i, t in enumerate(starts):
                t_f = float(t)
                if t_f < 9.0:
                    continue
                pre_idx = np.flatnonzero((starts >= max(0.0, t_f - 12.0) - 0.08) & (starts < t_f - 0.08))
                if len(pre_idx) < 3:
                    continue
                pre_beg_sens = crow_any[pre_idx] & (tbl["s_beg"][pre_idx] >= refs.T_beg)
                pre_beg_strict = crow_any[pre_idx] & (tbl["s_beg"][pre_idx] >= 0.0)
                if int(np.sum(pre_beg_sens)) < 2 or int(np.sum(pre_beg_strict)) < 1:
                    continue
                ok_tail, reason = live_tail(tbl, i, t_f + 3.0, t_f + 18.0)
                if not ok_tail:
                    audit[f"C_reject_{reason}"] += 1
                    continue
                post_idx = span_indices(starts, t_f + 3.0, t_f + 18.0)
                if post_idx is None:
                    continue

                post_any_beg = int(np.sum((tbl["corvid"][post_idx] >= 0.15) & (tbl["s_beg"][post_idx] >= refs.T_beg)))
                post_cont_beg = int(np.sum((tbl["corvid"][post_idx] >= 0.25) & (tbl["s_beg"][post_idx] >= refs.T_beg)))
                if post_any_beg == 0:
                    outcome = 1  # begging_stopped
                elif post_cont_beg >= 2:
                    outcome = 0  # begging_continued
                else:
                    outcome = -1  # ambiguous single residual window

                is_adult_nonbeg = (
                    (tbl["american_crow"][i] >= 0.25)
                    & (tbl["raptor"][i] < 0.05)
                    & (tbl["s_beg"][i] < refs.T_beg)
                )
                is_ongoing_beg = crow_any[i] & (tbl["s_beg"][i] >= 0.0) & (tbl["raptor"][i] < 0.05)

                if outcome in (0, 1) and (is_adult_nonbeg or is_ongoing_beg):
                    hazard_C_rows.append({
                        "rec_id": rec["id"],
                        "observer": rec["observer"],
                        "t": t_f,
                        "rel_pos": round(t_f / max(dur, 1.0), 4),
                        "rem_dur": round(dur - t_f, 3),
                        "kind": "adult_nonbeg" if is_adult_nonbeg else "ongoing_beg",
                        "stopped": outcome,
                    })

                if is_adult_nonbeg and outcome in (0, 1) and outcome not in seen_outcomes:
                    seen_outcomes.add(outcome)
                    events_C.append({
                        "rec_id": rec["id"],
                        "path": rec["path"],
                        "observer": rec["observer"],
                        "t": t_f,
                        "y": outcome,
                        "embedding": tbl["embedding"][i],
                        "crow_rms_db": float(tbl["crow_rms_db"][i]),
                        "snr_db": float(tbl["snr_db"][i]),
                        "p_several": float(tbl["p_several"][i]),
                        "s_beg": float(tbl["s_beg"][i]),
                        "duty_u": float(tbl["duty_u"][i]),
                    })

    # Pre-declared negative cap for Primary A: at most 4 * n_recruited (seed = 0)
    rng = np.random.default_rng(0)
    max_neg = max(1, 4 * len(events_A_pos))
    if len(events_A_neg) > max_neg:
        keep_idx = sorted(rng.choice(len(events_A_neg), size=max_neg, replace=False).tolist())
        events_A_neg_used = [events_A_neg[i] for i in keep_idx]
    else:
        events_A_neg_used = list(events_A_neg)

    return {
        "A_events": events_A_pos + events_A_neg_used,
        "A_counts": {"pos": len(events_A_pos), "neg_total": len(events_A_neg), "neg_used": len(events_A_neg_used)},
        "B_pairs": pairs_B,
        "C_events": events_C,
        "C_hazard": hazard_C_rows,
        "audit": dict(audit),
    }


def prep_fold_matrices(X: np.ndarray, folds: list[tuple[np.ndarray, np.ndarray]], Z: np.ndarray | None = None):
    prepped = []
    for tr, te in folds:
        if Z is not None:
            z_sc = StandardScaler().fit(Z[tr])
            Z_tr = np.column_stack([np.ones(len(tr)), z_sc.transform(Z[tr])])
            Z_te = np.column_stack([np.ones(len(te)), z_sc.transform(Z[te])])
            coef, *_ = np.linalg.lstsq(Z_tr, X[tr], rcond=None)
            X_tr = X[tr] - Z_tr @ coef
            X_te = X[te] - Z_te @ coef
        else:
            X_tr, X_te = X[tr], X[te]
        x_sc = StandardScaler().fit(X_tr)
        prepped.append((tr, te, x_sc.transform(X_tr), x_sc.transform(X_te)))
    return prepped


def oof_scores_prepped(prepped, y: np.ndarray, C: float = 0.05) -> np.ndarray:
    scores = np.zeros(len(y), dtype=np.float64)
    for tr, te, X_tr, X_te in prepped:
        clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(X_tr, y[tr])
        scores[te] = clf.decision_function(X_te)
    return scores


def oof_scores(X: np.ndarray, y: np.ndarray, folds: list[tuple[np.ndarray, np.ndarray]], Z: np.ndarray | None = None, C: float = 0.05) -> np.ndarray:
    return oof_scores_prepped(prep_fold_matrices(X, folds, Z=Z), y, C=C)


def bootstrap_ci(y: np.ndarray, scores: np.ndarray, groups: np.ndarray, n_boot: int = 2000, seed: int = 0) -> list[float]:
    members = defaultdict(list)
    for idx, g in enumerate(groups):
        members[g].append(idx)
    keys = list(members)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        draw = np.concatenate([members[keys[j]] for j in rng.integers(0, len(keys), len(keys))])
        yd = y[draw]
        if yd.sum() == 0 or yd.sum() == len(yd):
            continue
        vals.append(float(roc_auc_score(yd, scores[draw])))
    if not vals:
        return [0.5, 0.5]
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def observer_permutation(X: np.ndarray, y: np.ndarray, groups: np.ndarray, folds, Z: np.ndarray | None, observed: float, n_perm: int = 400, C: float = 0.05, seed: int = 0) -> dict:
    prepped = prep_fold_matrices(X, folds, Z=Z)
    names = np.array(sorted(set(groups.tolist())))
    maj = []
    for g in names:
        vals, cnts = np.unique(y[groups == g], return_counts=True)
        maj.append(int(vals[np.argmax(cnts)]))
    maj = np.array(maj, dtype=int)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_perm):
        perm = rng.permutation(maj)
        mp = dict(zip(names, perm))
        yp = np.array([mp[g] for g in groups], dtype=int)
        if any(yp[tr].sum() == 0 or yp[tr].sum() == len(tr) for tr, _, _, _ in prepped):
            continue
        if yp.sum() == 0 or yp.sum() == len(yp):
            continue
        sc = oof_scores_prepped(prepped, yp, C=C)
        null.append(float(roc_auc_score(yp, sc)))
    p = (sum(v >= observed for v in null) + 1) / (len(null) + 1)
    return {
        "perm_p": round(float(p), 5),
        "perm_mean": round(float(np.mean(null)) if null else 0.5, 4),
        "perm_n": len(null),
    }


def paired_signflip_permutation(X: np.ndarray, y: np.ndarray, n_pairs: int, folds, Z: np.ndarray | None, observed: float, n_perm: int = 400, C: float = 0.05, seed: int = 0) -> dict:
    """X is stacked [2 * n_pairs] where (2*k, 2*k+1) = (cont=0, stop=1) in the same recording."""
    prepped = prep_fold_matrices(X, folds, Z=Z)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_perm):
        flips = rng.integers(0, 2, size=n_pairs)
        yp = y.copy()
        for k, f in enumerate(flips):
            if f == 1:
                yp[2 * k], yp[2 * k + 1] = 1, 0
        sc = oof_scores_prepped(prepped, yp, C=C)
        null.append(float(roc_auc_score(yp, sc)))
    p = (sum(v >= observed for v in null) + 1) / (len(null) + 1)
    return {
        "perm_p": round(float(p), 5),
        "perm_mean": round(float(np.mean(null)), 4),
        "perm_n": len(null),
    }


def extract_focal_caw44(path_cache: dict[str, np.ndarray], path: str, t: float) -> tuple[np.ndarray | None, float]:
    if path not in path_cache:
        try:
            with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
                y, _ = librosa.load(path, sr=SR, mono=True)
            path_cache[path] = y
        except Exception:  # noqa: BLE001
            path_cache[path] = np.zeros(0, dtype=np.float32)
    y = path_cache[path]
    if len(y) < SR:
        return None, 0.0
    dur_total = len(y) / SR
    found = exp103.segment_caws_in_windows(y, SR, [(t, min(dur_total, t + WINDOW_S))], max_caws=100)
    if not found:
        return None, 0.0
    vecs = []
    for c in found:
        i0 = max(0, int(round(c["onset"] * SR)))
        i1 = min(len(y), int(round(c["offset"] * SR)))
        if i1 - i0 >= int(0.04 * SR):
            vecs.append(exp103.extract_caw_44d(y[i0:i1], SR))
    if not vecs:
        return None, 0.0
    return np.mean(vecs, axis=0).astype(np.float32), float(len(vecs) / WINDOW_S)


def smd_summary(X44: np.ndarray, rates: np.ndarray, y: np.ndarray) -> dict:
    # Indices in extract_caw_44d: 0=caw_dur_s, 1=attack_frac, 3=f0_med_hz, 5=f0_slope_hz_s
    specs = [
        ("caw_dur_s", X44[:, 0]),
        ("attack_frac", X44[:, 1]),
        ("f0_med_hz", X44[:, 3]),
        ("f0_slope_hz_s", X44[:, 5]),
        ("caw_rate_hz", rates),
    ]
    out = {}
    for name, vals in specs:
        pos, neg = vals[y == 1], vals[y == 0]
        sd = float(np.sqrt(0.5 * (np.var(pos) + np.var(neg))) + 1e-8)
        out[name] = {
            "pos_median": round(float(np.median(pos)), 4),
            "neg_median": round(float(np.median(neg)), 4),
            "smd_pos_minus_neg": round(float((np.mean(pos) - np.mean(neg)) / sd), 4),
        }
    return out


def eval_caw44_block(events: list[dict], paired: bool = False) -> dict:
    path_cache: dict[str, np.ndarray] = {}
    if not paired:
        rows, rates = [], []
        for ev in events:
            v, r = extract_focal_caw44(path_cache, ev["path"], ev["t"])
            if v is not None and np.isfinite(v).all():
                rows.append((ev, v, r))
                rates.append(r)
            if len(path_cache) > 64:
                path_cache.clear()
        y = np.array([r[0]["y"] for r in rows], dtype=int)
        if int(y.sum()) < 10 or int((1 - y).sum()) < 10:
            return {"n": len(rows), "pos": int(y.sum()), "status": "too_few_segmented_caws"}
        X = np.stack([r[1] for r in rows])
        rt = np.array(rates, dtype=np.float32)
        groups = np.array([r[0]["observer"] for r in rows])
        folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X, y, groups))
        sc = oof_scores(X, y, folds, Z=None, C=0.1)
        auc = float(roc_auc_score(y, sc))
        return {
            "n": len(rows),
            "pos": int(y.sum()),
            "neg": int((1 - y).sum()),
            "auc_caw44": round(auc, 4),
            "ci95": bootstrap_ci(y, sc, groups),
            "features": smd_summary(X, rt, y),
        }
    else:
        kept_X, kept_y, kept_r, kept_g = [], [], [], []
        n_kept_pairs = 0
        for p in events:
            vc, rc = extract_focal_caw44(path_cache, p["path"], p["cont"]["t"])
            vs, rs = extract_focal_caw44(path_cache, p["path"], p["stop"]["t"])
            if vc is not None and vs is not None and np.isfinite(vc).all() and np.isfinite(vs).all():
                kept_X.extend([vc, vs])
                kept_y.extend([0, 1])
                kept_r.extend([rc, rs])
                kept_g.extend([p["observer"], p["observer"]])
                n_kept_pairs += 1
            if len(path_cache) > 64:
                path_cache.clear()
        if n_kept_pairs < 15:
            return {"pairs": n_kept_pairs, "status": "too_few_segmented_pairs"}
        X = np.stack(kept_X)
        y = np.array(kept_y, dtype=int)
        rt = np.array(kept_r, dtype=np.float32)
        groups = np.array(kept_g)
        folds = list(GroupKFold(n_splits=5).split(X, y, groups))
        sc = oof_scores(X, y, folds, Z=None, C=0.1)
        auc = float(roc_auc_score(y, sc))
        return {
            "pairs": n_kept_pairs,
            "auc_caw44": round(auc, 4),
            "ci95": bootstrap_ci(y, sc, groups),
            "features": smd_summary(X, rt, y),
        }


def eval_hazard_C1(hazard_rows: list[dict]) -> dict:
    adult = [r for r in hazard_rows if r["kind"] == "adult_nonbeg"]
    beg = [r for r in hazard_rows if r["kind"] == "ongoing_beg"]
    if not adult or not beg:
        return {"adult_n": len(adult), "beg_n": len(beg), "status": "empty"}

    p_adult = float(np.mean([r["stopped"] for r in adult]))
    p_beg = float(np.mean([r["stopped"] for r in beg]))
    diff = p_adult - p_beg

    by_obs = defaultdict(list)
    for r in hazard_rows:
        by_obs[r["observer"]].append(r)
    keys = list(by_obs)
    rng = np.random.default_rng(0)
    diffs, pos_adj_diffs = [], []

    # Also position-adjusted OLS: stopped ~ is_adult + rel_pos + rem_dur
    def pos_adj_effect(rows_sub: list[dict]) -> float | None:
        a = [r for r in rows_sub if r["kind"] == "adult_nonbeg"]
        b = [r for r in rows_sub if r["kind"] == "ongoing_beg"]
        if not a or not b:
            return None
        yv = np.array([r["stopped"] for r in rows_sub], dtype=np.float64)
        D = np.column_stack([
            np.ones(len(rows_sub)),
            np.array([1.0 if r["kind"] == "adult_nonbeg" else 0.0 for r in rows_sub]),
            np.array([r["rel_pos"] for r in rows_sub]),
            np.array([r["rem_dur"] for r in rows_sub]),
        ])
        beta, *_ = np.linalg.lstsq(D, yv, rcond=None)
        return float(beta[1])

    adj_obs = pos_adj_effect(hazard_rows)
    for _ in range(2000):
        sample = [r for j in rng.integers(0, len(keys), len(keys)) for r in by_obs[keys[j]]]
        sa = [r["stopped"] for r in sample if r["kind"] == "adult_nonbeg"]
        sb = [r["stopped"] for r in sample if r["kind"] == "ongoing_beg"]
        if sa and sb:
            diffs.append(float(np.mean(sa) - np.mean(sb)))
        ae = pos_adj_effect(sample)
        if ae is not None:
            pos_adj_diffs.append(ae)

    return {
        "adult_nonbeg_checkpoints": len(adult),
        "adult_nonbeg_recordings": len({r["rec_id"] for r in adult}),
        "ongoing_beg_checkpoints": len(beg),
        "ongoing_beg_recordings": len({r["rec_id"] for r in beg}),
        "observers": len(keys),
        "stop_rate_after_adult_nonbeg": round(p_adult, 4),
        "stop_rate_after_ongoing_beg": round(p_beg, 4),
        "delta_stop_rate": round(diff, 4),
        "delta_ci95_observer_boot": [
            round(float(np.percentile(diffs, 2.5)), 4),
            round(float(np.percentile(diffs, 97.5)), 4),
        ] if diffs else [0.0, 0.0],
        "position_adjusted_delta": round(float(adj_obs), 4) if adj_obs is not None else None,
        "position_adjusted_ci95": [
            round(float(np.percentile(pos_adj_diffs, 2.5)), 4),
            round(float(np.percentile(pos_adj_diffs, 97.5)), 4),
        ] if pos_adj_diffs else None,
    }


def eval_capture_104(refs: FrozenReferenceHeads, c_events: list[dict]) -> dict:
    tbl = load_window_table("capture_104", refs)
    if tbl is None:
        return {"status": "capture_104_not_scanned"}

    # Fit Primary C model strictly on corvid.db C_events (if eligible) to score Capture 104 out-of-sample
    model_raw = None
    model_res = None
    z_scaler = None
    z_coef = None
    if len(c_events) >= 20:
        Xc = np.stack([e["embedding"] for e in c_events])
        yc = np.array([e["y"] for e in c_events], dtype=int)
        Zc = np.array([[e["crow_rms_db"], e["snr_db"], e["p_several"], e["s_beg"]] for e in c_events], dtype=np.float32)
        if yc.sum() >= 5 and (len(yc) - yc.sum()) >= 5:
            model_raw = head(0.05).fit(Xc, yc)
            z_scaler = StandardScaler().fit(Zc)
            Z_design = np.column_stack([np.ones(len(Zc)), z_scaler.transform(Zc)])
            z_coef, *_ = np.linalg.lstsq(Z_design, Xc, rcond=None)
            model_res = head(0.05).fit(Xc - Z_design @ z_coef, yc)

    labels = []
    if FIELD_DB.exists():
        db = sqlite3.connect(f"file:{FIELD_DB}?mode=ro", uri=True)
        for s, e, ct, role in db.execute(
            "SELECT start_sec, end_sec, call_type, caller_role FROM labels WHERE capture_id = 104 ORDER BY start_sec"
        ):
            labels.append({"start_sec": s, "end_sec": e, "call_type": ct, "caller_role": role})

    windows_out = []
    for i, st in enumerate(tbl["start"]):
        emb = tbl["embedding"][i : i + 1]
        z_row = np.array([[tbl["crow_rms_db"][i], tbl["snr_db"][i], tbl["p_several"][i], tbl["s_beg"][i]]], dtype=np.float32)
        raw_sc = float(model_raw.decision_function(emb)[0]) if model_raw is not None else None
        if model_res is not None:
            z_d = np.column_stack([np.ones(1), z_scaler.transform(z_row)])
            res_sc = float(model_res.decision_function(emb - z_d @ z_coef)[0])
        else:
            res_sc = None
        windows_out.append({
            "window": f"{float(st):.0f}-{float(st) + 3.0:.0f}s",
            "start": float(st),
            "corvid": round(float(tbl["corvid"][i]), 3),
            "american_crow": round(float(tbl["american_crow"][i]), 3),
            "s_beg": round(float(tbl["s_beg"][i]), 3),
            "p_several": round(float(tbl["p_several"][i]), 3),
            "crow_rms_db": round(float(tbl["crow_rms_db"][i]), 2),
            "snr_db": round(float(tbl["snr_db"][i]), 2),
            "duty_u": round(float(tbl["duty_u"][i]), 3),
            "adult_stop_score_raw": round(raw_sc, 3) if raw_sc is not None else None,
            "adult_stop_score_res": round(res_sc, 3) if res_sc is not None else None,
        })
    return {
        "file_duration": round(tbl["file_duration"], 2),
        "human_labels": labels,
        "windows": windows_out,
    }


def main():
    run = Run("0119 call-consequence pragmatics evaluation", ["events", "primaries", "secondaries"])
    catalogue = json.loads((CACHE / "catalogue.json").read_text())
    refs = FrozenReferenceHeads()

    with run.stage("events") as stage:
        built = build_events(catalogue, refs, stage)

    holm_p_inputs: dict[str, float] = {}
    results: dict = {
        "catalogue_recordings": len(catalogue),
        "reference_thresholds": refs.report,
        "event_counts_and_audit": {
            "A_counts": built["A_counts"],
            "B_pairs": len(built["B_pairs"]),
            "C_events_total": len(built["C_events"]),
            "C_stopped": sum(e["y"] == 1 for e in built["C_events"]),
            "C_continued": sum(e["y"] == 0 for e in built["C_events"]),
            "audit": built["audit"],
        },
    }

    with run.stage("primaries") as stage:
        stage.update(0, 3, extra="Primary A (recruitment)")
        # ---- Primary A ----
        evA = built["A_events"]
        yA = np.array([e["y"] for e in evA], dtype=int)
        nA_pos, nA_neg = int(yA.sum()), int((1 - yA).sum())
        nA_obs_pos = len(set(np.array([e["observer"] for e in evA])[yA == 1].tolist())) if nA_pos else 0
        nA_obs_neg = len(set(np.array([e["observer"] for e in evA])[yA == 0].tolist())) if nA_neg else 0
        if nA_pos >= MIN_CELL and nA_neg >= MIN_CELL and min(nA_obs_pos, nA_obs_neg) >= 3:
            XA = np.stack([e["embedding"] for e in evA])
            ZA = np.array([[e["p_several"], e["duty_u"], e["crow_rms_db"], e["snr_db"]] for e in evA], dtype=np.float32)
            gA = np.array([e["observer"] for e in evA])
            kA = min(5, nA_obs_pos, nA_obs_neg)
            foldsA = list(StratifiedGroupKFold(n_splits=kA, shuffle=True, random_state=0).split(XA, yA, gA))

            scA_res = oof_scores(XA, yA, foldsA, Z=ZA, C=0.05)
            aucA_res = float(roc_auc_score(yA, scA_res))
            permA = observer_permutation(XA, yA, gA, foldsA, ZA, aucA_res, n_perm=400, C=0.05, seed=0)

            scA_raw = oof_scores(XA, yA, foldsA, Z=None, C=0.05)
            scA_nuis = oof_scores(ZA, yA, foldsA, Z=None, C=0.05)
            holm_p_inputs["Primary_A_recruitment"] = permA["perm_p"]
            results["Primary_A_recruitment"] = {
                "eligible_for_holm": True,
                "n": len(yA),
                "recruited_pos": nA_pos,
                "unrecruited_neg": nA_neg,
                "observers": len(set(gA.tolist())),
                "residualized_auc": round(aucA_res, 4),
                "residualized_ci95": bootstrap_ci(yA, scA_res, gA),
                **permA,
                "raw_birdnet_auc": round(float(roc_auc_score(yA, scA_raw)), 4),
                "nuisance_only_auc": round(float(roc_auc_score(yA, scA_nuis)), 4),
                "nuisance_medians": {
                    "p_several_pos_vs_neg": [
                        round(float(np.median(ZA[yA == 1, 0])), 4),
                        round(float(np.median(ZA[yA == 0, 0])), 4),
                    ],
                    "duty_u_pos_vs_neg": [
                        round(float(np.median(ZA[yA == 1, 1])), 4),
                        round(float(np.median(ZA[yA == 0, 1])), 4),
                    ],
                    "snr_db_pos_vs_neg": [
                        round(float(np.median(ZA[yA == 1, 3])), 2),
                        round(float(np.median(ZA[yA == 0, 3])), 2),
                    ],
                },
            }
        else:
            results["Primary_A_recruitment"] = {
                "eligible_for_holm": False,
                "recruited_pos": nA_pos,
                "unrecruited_neg": nA_neg,
                "status": "underpowered_below_20",
            }

        stage.update(1, 3, extra="Primary B (paired cessation)")
        # ---- Primary B ----
        pB = built["B_pairs"]
        if len(pB) >= MIN_CELL:
            XB, yB, ZB, gB = [], [], [], []
            snr_diffs, rms_diffs, p_diffs = [], [], []
            for p in pB:
                c, s = p["cont"], p["stop"]
                XB.extend([c["embedding"], s["embedding"]])
                yB.extend([0, 1])
                ZB.extend([
                    [c["crow_rms_db"], c["snr_db"], c["p_several"], c["duty_u"]],
                    [s["crow_rms_db"], s["snr_db"], s["p_several"], s["duty_u"]],
                ])
                gB.extend([p["observer"], p["observer"]])
                snr_diffs.append(s["snr_db"] - c["snr_db"])
                rms_diffs.append(s["crow_rms_db"] - c["crow_rms_db"])
                p_diffs.append(s["p_several"] - c["p_several"])
            XB = np.stack(XB)
            yB = np.array(yB, dtype=int)
            ZB = np.array(ZB, dtype=np.float32)
            gB = np.array(gB)
            foldsB = list(GroupKFold(n_splits=5).split(XB, yB, gB))

            scB_res = oof_scores(XB, yB, foldsB, Z=ZB, C=0.05)
            aucB_res = float(roc_auc_score(yB, scB_res))
            permB = paired_signflip_permutation(XB, yB, len(pB), foldsB, ZB, aucB_res, n_perm=400, C=0.05, seed=0)

            scB_raw = oof_scores(XB, yB, foldsB, Z=None, C=0.05)
            scB_nuis = oof_scores(ZB, yB, foldsB, Z=None, C=0.05)
            w_snr = wilcoxon(snr_diffs) if any(d != 0 for d in snr_diffs) else None
            w_rms = wilcoxon(rms_diffs) if any(d != 0 for d in rms_diffs) else None
            holm_p_inputs["Primary_B_cessation"] = permB["perm_p"]
            results["Primary_B_cessation"] = {
                "eligible_for_holm": True,
                "paired_recordings": len(pB),
                "windows_scored": len(yB),
                "observers": len(set(gB.tolist())),
                "residualized_auc": round(aucB_res, 4),
                "residualized_ci95": bootstrap_ci(yB, scB_res, gB),
                **permB,
                "raw_birdnet_auc": round(float(roc_auc_score(yB, scB_raw)), 4),
                "nuisance_only_auc": round(float(roc_auc_score(yB, scB_nuis)), 4),
                "S_B1_fly_away_fade_test": {
                    "median_snr_stop_minus_cont_db": round(float(np.median(snr_diffs)), 3),
                    "frac_terminal_quieter_snr": round(float(np.mean(np.array(snr_diffs) < 0)), 4),
                    "wilcoxon_snr_p": round(float(w_snr.pvalue), 6) if w_snr else 1.0,
                    "median_crow_rms_stop_minus_cont_db": round(float(np.median(rms_diffs)), 3),
                    "wilcoxon_rms_p": round(float(w_rms.pvalue), 6) if w_rms else 1.0,
                    "median_p_several_stop_minus_cont": round(float(np.median(p_diffs)), 4),
                },
            }
        else:
            results["Primary_B_cessation"] = {
                "eligible_for_holm": False,
                "paired_recordings": len(pB),
                "status": "underpowered_below_20",
            }

        stage.update(2, 3, extra="Primary C (begging cessation)")
        # ---- Primary C ----
        evC = built["C_events"]
        yC = np.array([e["y"] for e in evC], dtype=int)
        nC_pos, nC_neg = int(yC.sum()), int((1 - yC).sum())
        nC_obs_pos = len(set(np.array([e["observer"] for e in evC])[yC == 1].tolist())) if nC_pos else 0
        nC_obs_neg = len(set(np.array([e["observer"] for e in evC])[yC == 0].tolist())) if nC_neg else 0
        if nC_pos >= MIN_CELL and nC_neg >= MIN_CELL and min(nC_obs_pos, nC_obs_neg) >= 3:
            XC = np.stack([e["embedding"] for e in evC])
            ZC = np.array([[e["crow_rms_db"], e["snr_db"], e["p_several"], e["s_beg"]] for e in evC], dtype=np.float32)
            gC = np.array([e["observer"] for e in evC])
            kC = min(5, nC_obs_pos, nC_obs_neg)
            foldsC = list(StratifiedGroupKFold(n_splits=kC, shuffle=True, random_state=0).split(XC, yC, gC))

            scC_res = oof_scores(XC, yC, foldsC, Z=ZC, C=0.05)
            aucC_res = float(roc_auc_score(yC, scC_res))
            permC = observer_permutation(XC, yC, gC, foldsC, ZC, aucC_res, n_perm=400, C=0.05, seed=0)

            scC_raw = oof_scores(XC, yC, foldsC, Z=None, C=0.05)
            scC_nuis = oof_scores(ZC, yC, foldsC, Z=None, C=0.05)
            holm_p_inputs["Primary_C_begging_cessation"] = permC["perm_p"]
            results["Primary_C_begging_cessation"] = {
                "eligible_for_holm": True,
                "n": len(yC),
                "stopped_pos": nC_pos,
                "continued_neg": nC_neg,
                "observers": len(set(gC.tolist())),
                "residualized_auc": round(aucC_res, 4),
                "residualized_ci95": bootstrap_ci(yC, scC_res, gC),
                **permC,
                "raw_birdnet_auc": round(float(roc_auc_score(yC, scC_raw)), 4),
                "nuisance_only_auc": round(float(roc_auc_score(yC, scC_nuis)), 4),
                "nuisance_medians": {
                    "crow_rms_db_stopped_vs_cont": [
                        round(float(np.median(ZC[yC == 1, 0])), 2),
                        round(float(np.median(ZC[yC == 0, 0])), 2),
                    ],
                    "snr_db_stopped_vs_cont": [
                        round(float(np.median(ZC[yC == 1, 1])), 2),
                        round(float(np.median(ZC[yC == 0, 1])), 2),
                    ],
                    "s_beg_stopped_vs_cont": [
                        round(float(np.median(ZC[yC == 1, 3])), 3),
                        round(float(np.median(ZC[yC == 0, 3])), 3),
                    ],
                },
            }
        else:
            results["Primary_C_begging_cessation"] = {
                "eligible_for_holm": False,
                "stopped_pos": nC_pos,
                "continued_neg": nC_neg,
                "status": "underpowered_below_20",
            }
        stage.update(3, 3)

    holm = holm_adjust(holm_p_inputs) if holm_p_inputs else {}
    for k, adj_p in holm.items():
        results[k]["holm_p"] = adj_p
        results[k]["passes"] = bool(results[k]["residualized_auc"] >= 0.65 and adj_p < 0.05)

    with run.stage("secondaries") as stage:
        stage.update(0, 3, extra="S_caw44 prosody")
        results["S_caw44"] = {
            "A_recruitment": eval_caw44_block(built["A_events"], paired=False),
            "B_cessation": eval_caw44_block(built["B_pairs"], paired=True),
            "C_begging_cessation": eval_caw44_block(built["C_events"], paired=False),
        }
        stage.update(1, 3, extra="S_C1 begging hazard")
        results["S_C1_begging_hazard"] = eval_hazard_C1(built["C_hazard"])
        stage.update(2, 3, extra="S_104 Capture 104 walk")
        results["S_104_capture_104"] = eval_capture_104(refs, built["C_events"])
        stage.update(3, 3)

    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({k: v for k, v in results.items() if k != "S_104_capture_104"}, indent=2))
    run.note(
        " | ".join(
            f"{k}: auc={results[k].get('residualized_auc')} holm_p={results[k].get('holm_p')}"
            for k in ("Primary_A_recruitment", "Primary_B_cessation", "Primary_C_begging_cessation")
        )
    )


if __name__ == "__main__":
    main()
