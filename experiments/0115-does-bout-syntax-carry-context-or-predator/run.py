"""0115 — single-bird bout syntax, phrase trajectory, and within-bout caw-order shuffles.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0115-does-bout-syntax-carry-context-or-predator/run.py
"""

from __future__ import annotations

import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import wilcoxon
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"
sys.path.insert(0, str(EXP112))
import sets  # noqa: E402
from scoring import CONTEXTS, GroupedOvR, head  # noqa: E402

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402

CACHE = sets.DATA_DIR / "experiments" / "0115-bout-syntax"
SR = 22050
MAX_AUDIO_S = 300.0
PRECISION = 0.90
MIN_CAWS = 3
BOUT_GAP_S = 1.50
PROSODY_IDX = [0, 1, 2, 3, 5]  # caw_dur_s, attack_frac, peak_to_mean_rms, f0_med_hz, f0_slope_hz_s
PROSODY_NAMES = ("caw_dur_s", "attack_frac", "peak_to_mean_rms", "f0_med_hz", "f0_slope_hz_s")

CADENCE_NAMES = (
    "bout_len_mean", "bout_len_std", "bout_len_max", "frac_caws_in_multibout",
    "multibout_dur_mean", "ici_mean", "ici_median", "ici_iqr", "ici_cv", "interbout_gap_median",
)
ORDER_NAMES = (
    *(f"slope_mean_{n}" for n in PROSODY_NAMES),
    *(f"slope_std_{n}" for n in PROSODY_NAMES),
    "last_minus_first_dur", "last_minus_first_f0", "last_minus_first_attack",
    "step_signed_dur", "step_abs_dur", "step_signed_f0", "step_abs_f0",
    "ici_log_accel",
)
assert len(CADENCE_NAMES) == 10 and len(ORDER_NAMES) == 18


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp103 = load_module("exp103_0115", sets.EXP103 / "extract_caws.py")
exp112_eval = load_module("exp112_0115", EXP112 / "evaluate.py")


class CrowGPTCountCut:
    """90% one-crow precision cut on CrowGPT Dual-AR block 4, fixed on 0109/0112 segments before archive scoring."""

    def __init__(self, reps):
        crowd = exp112_eval.CrowdInsideType(reps)
        X = crowd.features["crowgpt_b4"]
        y = crowd.data.several
        groups = crowd.data.groups
        oof = np.zeros(len(y), dtype=np.float64)
        for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X, y, groups):
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000),
            ).fit(X[tr], y[tr])
            oof[te] = clf.predict_proba(X[te])[:, 1]
        order = np.argsort(oof)
        one = 1 - y[order]
        prec = np.cumsum(one) / np.arange(1, len(one) + 1)
        passing = np.flatnonzero(prec >= PRECISION)
        last = int(passing.max())
        self.threshold = float(oof[order][last + 1]) if last + 1 < len(order) else 1.0
        below = oof < self.threshold
        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000),
        ).fit(X, y)
        self.report = {
            "representation": "crowgpt_b4",
            "threshold_p_several": round(self.threshold, 4),
            "segments_below": int(below.sum()),
            "segments": int(len(oof)),
            "one_crow_precision_below": round(float((1 - y[below]).mean()), 4),
            "one_crow_recall": round(float(below[y == 0].mean()), 4),
        }


def merge_adjacent_windows(starts: list[float], win_s: float = 3.0) -> list[tuple[float, float]]:
    if not starts:
        return []
    ordered = sorted(float(s) for s in starts)
    spans = [[ordered[0], ordered[0] + win_s]]
    for s in ordered[1:]:
        if abs(s - spans[-1][1]) < 0.05:
            spans[-1][1] = s + win_s
        else:
            spans.append([s, s + win_s])
    return [(a, b) for a, b in spans]


def extract_recording_bouts(task: tuple[str, str, list[float]]):
    """Segment single-bird caws across merged contiguous single-bird windows and group into bouts."""
    key, path, single_starts = task
    if not single_starts:
        return key, None, None
    try:
        y, sr = librosa.load(path, sr=SR, mono=True, duration=MAX_AUDIO_S)
    except Exception as exc:  # noqa: BLE001
        return key, None, str(exc)[:200]
    dur_total = len(y) / sr
    valid_starts = [s for s in single_starts if s + sets.WINDOW_S <= dur_total + 0.05]
    if not valid_starts:
        return key, None, None

    merged = merge_adjacent_windows(valid_starts, sets.WINDOW_S)
    spans_bouts = []
    all_caws_44d = []
    window_rates, window_gaps, window_cvs = [], [], []

    # Also compute 0113-exact 47d features over the 3s windows for exact matched S1 comparison
    for ws in valid_starts:
        w_found = exp103.segment_caws_in_windows(y, sr, [(ws, min(dur_total, ws + sets.WINDOW_S))], max_caws=10_000)
        window_rates.append(len(w_found) / sets.WINDOW_S)
        if len(w_found) >= 2:
            iv = np.diff([c["onset"] for c in w_found])
            window_gaps.append(float(np.median(iv)))
            window_cvs.append(float(np.std(iv) / max(float(np.mean(iv)), 1e-6)))

    total_caws = 0
    for span_s, span_e in merged:
        found = exp103.segment_caws_in_windows(y, sr, [(span_s, min(dur_total, span_e))], max_caws=10_000)
        if not found:
            continue
        caw_items = []
        for c in found:
            i0 = max(0, int(round(c["onset"] * sr)))
            i1 = min(len(y), int(round(c["offset"] * sr)))
            v44 = exp103.extract_caw_44d(y[i0:i1], sr)
            all_caws_44d.append(v44)
            caw_items.append({
                "onset": float(c["onset"]),
                "offset": float(c["offset"]),
                "prosody": [float(v44[idx]) for idx in PROSODY_IDX],
            })
        total_caws += len(caw_items)
        # Group into bouts with onset-to-onset <= BOUT_GAP_S
        cur = [caw_items[0]]
        span_bouts = []
        for item in caw_items[1:]:
            if item["onset"] - cur[-1]["onset"] <= BOUT_GAP_S:
                cur.append(item)
            else:
                span_bouts.append(cur)
                cur = [item]
        span_bouts.append(cur)
        spans_bouts.append(span_bouts)

    if total_caws < MIN_CAWS:
        return key, None, None

    bag_47d = np.concatenate([
        np.mean(np.stack(all_caws_44d), axis=0),
        [
            float(np.mean(window_rates)) if window_rates else 0.0,
            float(np.mean(window_gaps)) if window_gaps else 0.0,
            float(np.mean(window_cvs)) if window_cvs else 0.0,
        ],
    ]).astype(np.float32).tolist()

    return key, {
        "n_caws": total_caws,
        "n_single_windows": len(valid_starts),
        "spans_bouts": spans_bouts,
        "bag_47d": bag_47d,
    }, None


def compute_bout_features(spans_bouts: list[list[list[dict]]], rng: np.random.Generator | None = None) -> tuple[np.ndarray, np.ndarray] | None:
    """Compute (cadence_10d, order_18d). When rng is given, permutes caw scalars and ICIs within each bout."""
    all_bouts = [b for sb in spans_bouts for b in sb]
    multi_bouts = [b for b in all_bouts if len(b) >= 2]
    if not multi_bouts:
        return None

    lengths = np.array([len(b) for b in all_bouts], dtype=np.float64)
    total_caws = float(lengths.sum())
    multi_caws = float(sum(len(b) for b in multi_bouts))

    all_icis = []
    multi_durs = []
    interbout_gaps = []
    for sb in spans_bouts:
        for bi, b in enumerate(sb):
            if len(b) >= 2:
                onsets = np.array([c["onset"] for c in b], dtype=np.float64)
                all_icis.extend(np.diff(onsets).tolist())
                multi_durs.append(float(b[-1]["offset"] - b[0]["onset"]))
            if bi + 1 < len(sb):
                gap = float(sb[bi + 1][0]["onset"] - b[-1]["offset"])
                if 0.0 < gap <= 10.0:
                    interbout_gaps.append(gap)

    icis = np.array(all_icis, dtype=np.float64)
    ici_iqr = float(np.percentile(icis, 75) - np.percentile(icis, 25)) if len(icis) >= 2 else 0.0
    ici_cv = float(np.std(icis) / max(float(np.mean(icis)), 1e-6)) if len(icis) >= 2 else 0.0
    cadence = np.array([
        float(np.mean(lengths)),
        float(np.std(lengths)),
        float(np.max(lengths)),
        float(multi_caws / max(total_caws, 1.0)),
        float(np.mean(multi_durs)),
        float(np.mean(icis)),
        float(np.median(icis)),
        ici_iqr,
        ici_cv,
        float(np.median(interbout_gaps)) if interbout_gaps else 0.0,
    ], dtype=np.float32)

    slopes = []
    deltas = []
    steps_dur_s, steps_dur_a, steps_f0_s, steps_f0_a = [], [], [], []
    ici_accels = []

    for b in multi_bouts:
        K = len(b)
        P = np.array([c["prosody"] for c in b], dtype=np.float64)  # (K, 5)
        onsets = np.array([c["onset"] for c in b], dtype=np.float64)
        b_icis = np.diff(onsets)  # (K - 1,)
        if rng is not None:
            P = P[rng.permutation(K)]
            if len(b_icis) >= 2:
                b_icis = b_icis[rng.permutation(len(b_icis))]

        t_norm = np.linspace(0.0, 1.0, K)
        t_c = t_norm - t_norm.mean()
        denom = float(np.sum(t_c ** 2)) or 1.0
        b_slopes = (t_c @ (P - P.mean(axis=0))) / denom  # (5,)
        slopes.append(b_slopes)
        deltas.append([P[-1, 0] - P[0, 0], P[-1, 3] - P[0, 3], P[-1, 1] - P[0, 1]])

        d_dur = np.diff(P[:, 0])
        d_f0 = np.diff(P[:, 3])
        steps_dur_s.extend(d_dur.tolist())
        steps_dur_a.extend(np.abs(d_dur).tolist())
        steps_f0_s.extend(d_f0.tolist())
        steps_f0_a.extend(np.abs(d_f0).tolist())
        if len(b_icis) >= 2:
            ici_accels.extend(np.log((b_icis[1:] + 1e-3) / (b_icis[:-1] + 1e-3)).tolist())

    slopes_arr = np.vstack(slopes)  # (M, 5)
    deltas_arr = np.vstack(deltas)  # (M, 3)
    order = np.array([
        *np.mean(slopes_arr, axis=0).tolist(),
        *(np.std(slopes_arr, axis=0).tolist() if len(slopes_arr) >= 2 else [0.0] * 5),
        *np.mean(deltas_arr, axis=0).tolist(),
        float(np.mean(steps_dur_s)),
        float(np.mean(steps_dur_a)),
        float(np.mean(steps_f0_s)),
        float(np.mean(steps_f0_a)),
        float(np.mean(ici_accels)) if ici_accels else 0.0,
    ], dtype=np.float32)
    return np.nan_to_num(cadence, 0.0), np.nan_to_num(order, 0.0)


class Residualised(GroupedOvR):
    def __init__(self, labels, groups, covariate, C=0.1):
        super().__init__(labels, groups, C=C)
        self.covariate = covariate

    def scores(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros((len(X), len(self.classes)))
        z = np.column_stack([np.ones(len(X)), self.covariate])
        for tr, te in self.folds:
            beta, *_ = np.linalg.lstsq(z[tr], X[tr], rcond=None)
            Xr = X - z @ beta
            for k, c in enumerate(self.classes):
                out[te, k] = head(self.C).fit(Xr[tr], (self.labels[tr] == c).astype(int)).decision_function(Xr[te])
        return out


def binary_grouped_cv(X: np.ndarray, y: np.ndarray, groups: np.ndarray, C: float = 0.1, n_perm: int = 400, seed: int = 0) -> dict:
    n_splits = min(5, int(y.sum()), int((1 - y).sum()), len(set(groups)))
    if n_splits < 2:
        return {"n": int(len(y)), "pos": int(y.sum()), "neg": int((1 - y).sum()), "auc": None}

    def _auc(target: np.ndarray) -> float | None:
        scores = np.zeros(len(target))
        for tr, te in StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=0).split(X, target, groups):
            if len(set(target[tr])) < 2:
                return None
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=C, class_weight="balanced", max_iter=3000),
            ).fit(X[tr], target[tr])
            scores[te] = clf.decision_function(X[te])
        return float(roc_auc_score(target, scores))

    obs = _auc(y)
    out = {
        "n": int(len(y)),
        "pos": int(y.sum()),
        "neg": int((1 - y).sum()),
        "groups": int(len(set(groups))),
        "auc": None if obs is None else round(obs, 4),
    }
    if obs is None or n_perm <= 0:
        return out
    uniq = np.array(sorted(set(groups)))
    maj = np.array([int(round(float(np.mean(y[groups == g])))) for g in uniq])
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_perm):
        mp = dict(zip(uniq, rng.permutation(maj)))
        py = np.array([mp[g] for g in groups])
        val = _auc(py)
        if val is not None:
            null.append(val)
    out["perm_p"] = round((sum(v >= obs for v in null) + 1) / (len(null) + 1), 4)
    out["perm_mean"] = round(float(np.mean(null)), 4) if null else None
    return out


def holm_pair(p_a: float, p_b: float) -> tuple[float, float]:
    if p_a <= p_b:
        return round(min(1.0, 2 * p_a), 4), round(max(min(1.0, 2 * p_a), min(1.0, p_b)), 4)
    hb = min(1.0, 2 * p_b)
    return round(max(hb, min(1.0, p_a)), 4), round(hb, 4)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    run = Run("0115 single-bird bout syntax", ["cut", "bouts", "primaries", "secondaries"])

    reps = exp112_eval.Representations()
    with run.stage("cut") as st:
        cut = CrowGPTCountCut(reps)
        (CACHE / "crowgpt_b4_cut.json").write_text(json.dumps(cut.report, indent=2))
        st.update(1, 1, extra=f"T={cut.threshold:.3f}")

    # Score archive pure windows + also save window classifications for 0118 reuse
    lbl_meta = {r["id"]: r for r in json.loads((sets.EXP102 / "labels.json").read_text())}
    archive_rows = []
    window_splits = {}
    for r in sets.ArchiveSet().recordings:
        if not sets.WindowTable.exists(r.key):
            continue
        table = sets.WindowTable(r.key)
        pure = table.pure() & (table.raptor < 0.05)
        if not pure.any():
            continue
        pure_starts = table.start[pure]
        vecs, valid_s = [], []
        for s in pure_starts:
            v = reps.span("crowgpt_b4", f"{r.key}@{float(s):.2f}")
            if v is not None:
                vecs.append(v)
                valid_s.append(float(s))
        if not vecs:
            continue
        p_sev = cut.model.predict_proba(np.stack(vecs))[:, 1]
        single_s = [s for s, p in zip(valid_s, p_sev) if p < cut.threshold]
        multi_s = [s for s, p in zip(valid_s, p_sev) if p >= cut.threshold]
        window_splits[r.key] = {"single": single_s, "multi": multi_s, "p_several": [round(float(p), 4) for p in p_sev]}
        archive_rows.append({
            "recording": r,
            "single": single_s,
            "multi": multi_s,
            "count_single": float(np.mean([p for p in p_sev if p < cut.threshold])) if single_s else None,
            "count_pure": float(np.mean(p_sev)),
            "trigger": (lbl_meta.get(r.extra["id"]) or {}).get("trigger") or "",
        })
    (CACHE / "archive_window_splits.json").write_text(json.dumps(window_splits))

    bouts_cache = CACHE / "bouts.json"
    if bouts_cache.exists():
        extracted = json.loads(bouts_cache.read_text())
    else:
        tasks = [(row["recording"].key, str(row["recording"].path), row["single"]) for row in archive_rows]
        extracted = {}
        with run.stage("bouts") as st, ProcessPoolExecutor(max_workers=12) as pool:
            futs = [pool.submit(extract_recording_bouts, t) for t in tasks]
            for done, fut in enumerate(as_completed(futs), 1):
                key, out, _ = fut.result()
                if out is not None:
                    extracted[key] = out
                if done % 15 == 0 or done == len(tasks):
                    st.update(done, len(tasks), extra=f"{len(extracted)} with >=3 caws")
        bouts_cache.write_text(json.dumps(extracted))

    # Assemble eligible recordings (>= 3 single-bird caws AND >= 1 multi-caw bout)
    eligible = []
    for row in archive_rows:
        ext = extracted.get(row["recording"].key)
        if not ext:
            continue
        feats = compute_bout_features(ext["spans_bouts"], rng=None)
        if feats is None:
            continue
        cad10, ord18 = feats
        eligible.append({
            **row,
            "ext": ext,
            "cad10": cad10,
            "ord18": ord18,
            "syn28": np.concatenate([cad10, ord18]),
            "bag47": np.array(ext["bag_47d"], dtype=np.float32),
        })

    X_syn28 = np.stack([e["syn28"] for e in eligible])
    X_cad10 = np.stack([e["cad10"] for e in eligible])
    X_ord18 = np.stack([e["ord18"] for e in eligible])
    X_bag47 = np.stack([e["bag47"] for e in eligible])
    labels = np.array([e["recording"].label for e in eligible])
    groups = np.array([e["recording"].group for e in eligible])
    counts_s = np.array([e["count_single"] for e in eligible], dtype=np.float64)

    report = {
        "crowgpt_b4_cut": cut.report,
        "archive_pure_windows": int(sum(len(r["single"]) + len(r["multi"]) for r in archive_rows)),
        "archive_single_windows": int(sum(len(r["single"]) for r in archive_rows)),
        "eligible_recordings": len(eligible),
        "eligible_recordists": int(len(set(groups))),
        "per_context_n": {c: int((labels == c).sum()) for c in CONTEXTS},
    }

    with run.stage("primaries") as st:
        # Primary A: strict zero-raptor single-bird owl vs hawk on bout_syntax_28d
        strict_oh = np.array([
            e["recording"].extra["fine_context"] in ("owl_mobbing", "hawk_mobbing")
            and not e["recording"].extra["pred_vocal"]
            and e["recording"].extra["max_raptor_conf"] < 0.05
            for e in eligible
        ])
        y_oh = np.array([1 if e["recording"].extra["fine_context"] == "owl_mobbing" else 0 for e in eligible])[strict_oh]
        g_oh = groups[strict_oh]
        prim_a = binary_grouped_cv(X_syn28[strict_oh], y_oh, g_oh, C=0.1, n_perm=400, seed=0)
        prim_a["cadence_10d_auc"] = binary_grouped_cv(X_cad10[strict_oh], y_oh, g_oh, C=0.1, n_perm=0)["auc"]
        prim_a["order_18d_auc"] = binary_grouped_cv(X_ord18[strict_oh], y_oh, g_oh, C=0.1, n_perm=0)["auc"]
        prim_a["bag_47d_same_recs_auc"] = binary_grouped_cv(X_bag47[strict_oh], y_oh, g_oh, C=0.1, n_perm=0)["auc"]
        st.update(1, 3)

        # Primary B: 5-context order_18d real temporal order vs 200 within-bout caw-order shuffles
        ovr = GroupedOvR(labels, groups, C=0.1)
        real_ord_scores = ovr.scores(X_ord18)
        real_ord_rep = ovr.report(real_ord_scores)
        real_ord_auc = real_ord_rep["macro_auc"]

        rng = np.random.default_rng(2026)
        shuf_aucs_5ctx = []
        shuf_aucs_oh = []
        real_oh_ord_auc = prim_a["order_18d_auc"]
        for k in range(200):
            X_shuf = np.stack([compute_bout_features(e["ext"]["spans_bouts"], rng=rng)[1] for e in eligible])
            shuf_aucs_5ctx.append(float(ovr.macro(ovr.scores(X_shuf))))
            oh_val = binary_grouped_cv(X_shuf[strict_oh], y_oh, g_oh, C=0.1, n_perm=0)["auc"]
            if oh_val is not None:
                shuf_aucs_oh.append(float(oh_val))
            if (k + 1) % 25 == 0:
                st.update(1 + int(2 * (k + 1) / 200), 3, extra=f"shuffle {k + 1}/200")

        shuf_mean = float(np.mean(shuf_aucs_5ctx))
        shuf_p = (sum(v >= real_ord_auc for v in shuf_aucs_5ctx) + 1) / (len(shuf_aucs_5ctx) + 1)
        holm_a, holm_b = holm_pair(prim_a["perm_p"], shuf_p)
        prim_a["holm_p"] = holm_a
        prim_a["passes"] = bool(prim_a["auc"] is not None and prim_a["auc"] >= 0.65 and holm_a < 0.05)

        prim_b = {
            "real_order_18d": real_ord_rep,
            "shuffled_within_bout_mean_auc": round(shuf_mean, 4),
            "shuffled_within_bout_p95_auc": round(float(np.percentile(shuf_aucs_5ctx, 95)), 4),
            "real_minus_shuffled": round(real_ord_auc - shuf_mean, 4),
            "shuffle_p": round(shuf_p, 4),
            "holm_p": holm_b,
            "passes": bool((real_ord_auc - shuf_mean) >= 0.03 and holm_b < 0.05),
        }
        report["PRIMARY_A_owl_vs_hawk_bout_syntax_28d"] = prim_a
        report["PRIMARY_B_within_bout_order_shuffle_5ctx"] = prim_b
        report["S4_within_bout_order_shuffle_owl_vs_hawk"] = {
            "real_order_18d_auc": real_oh_ord_auc,
            "shuffled_mean_auc": round(float(np.mean(shuf_aucs_oh)), 4),
            "real_minus_shuffled": round(float(real_oh_ord_auc - np.mean(shuf_aucs_oh)), 4),
            "shuffle_p": round((sum(v >= real_oh_ord_auc for v in shuf_aucs_oh) + 1) / (len(shuf_aucs_oh) + 1), 4),
        }

    with run.stage("secondaries") as st:
        # S1: 5-context comparison + crowd residualised
        ovr = GroupedOvR(labels, groups, C=0.1)
        res_ovr = Residualised(labels, groups, counts_s, C=0.1)
        report["S1_five_context_comparison"] = {
            "bout_syntax_28d": ovr.report(ovr.scores(X_syn28)),
            "cadence_10d": ovr.report(ovr.scores(X_cad10)),
            "bag_47d_same_recs": ovr.report(ovr.scores(X_bag47)),
            "bout_syntax_28d_crowd_removed": res_ovr.report(res_ovr.scores(X_syn28)),
            "bag_47d_crowd_removed": res_ovr.report(res_ovr.scores(X_bag47)),
        }
        st.update(1, 3)

        # S2: Great Horned Owl vs Barred Owl within strict single-bird owl mobbing
        gho_barred = []
        for idx, e in enumerate(eligible):
            if not strict_oh[idx] or e["recording"].extra["fine_context"] != "owl_mobbing":
                continue
            trig = e["trigger"].lower()
            if "great horned" in trig or "bubo virginianus" in trig:
                gho_barred.append((idx, 1))
            elif "barred" in trig or "strix varia" in trig:
                gho_barred.append((idx, 0))
        if len(gho_barred) >= 10:
            gb_idx = np.array([i for i, _ in gho_barred])
            gb_y = np.array([lab for _, lab in gho_barred])
            report["S2_great_horned_vs_barred_owl_single_bird"] = {
                "bout_syntax_28d": binary_grouped_cv(X_syn28[gb_idx], gb_y, groups[gb_idx], C=0.1, n_perm=400, seed=1),
                "bag_47d": binary_grouped_cv(X_bag47[gb_idx], gb_y, groups[gb_idx], C=0.1, n_perm=400, seed=2),
            }
        else:
            report["S2_great_horned_vs_barred_owl_single_bird"] = {"n": len(gho_barred), "note": "too few"}
        st.update(2, 3)

        # S3: Within-recording early (<=15s) vs sustained (>15s) single-bird bout comparison on raptor mobbing
        early_ici, late_ici, early_dur, late_dur, early_f0, late_f0 = [], [], [], [], [], []
        for e in eligible:
            if e["recording"].label != "raptor_mobbing":
                continue
            all_bouts = [b for sb in e["ext"]["spans_bouts"] for b in sb if len(b) >= 2]
            eb = [b for b in all_bouts if b[0]["onset"] < 15.0]
            lb = [b for b in all_bouts if b[0]["onset"] >= 15.0]
            if not eb or not lb:
                continue
            e_icis = [np.median(np.diff([c["onset"] for c in b])) for b in eb]
            l_icis = [np.median(np.diff([c["onset"] for c in b])) for b in lb]
            early_ici.append(float(np.mean(e_icis)))
            late_ici.append(float(np.mean(l_icis)))
            early_dur.append(float(np.mean([c["prosody"][0] for b in eb for c in b])))
            late_dur.append(float(np.mean([c["prosody"][0] for b in lb for c in b])))
            early_f0.append(float(np.mean([c["prosody"][3] for b in eb for c in b])))
            late_f0.append(float(np.mean([c["prosody"][3] for b in lb for c in b])))

        def _paired_stat(a: list[float], b: list[float]) -> dict:
            if len(a) < 8:
                return {"n_paired_recordings": len(a)}
            arr_a, arr_b = np.array(a), np.array(b)
            diff = arr_b - arr_a
            _, p = wilcoxon(arr_a, arr_b)
            return {
                "n_paired_recordings": len(a),
                "early_median": round(float(np.median(arr_a)), 4),
                "sustained_median": round(float(np.median(arr_b)), 4),
                "sustained_minus_early_median": round(float(np.median(diff)), 4),
                "wilcoxon_p": round(float(p), 4),
            }

        report["S3_early_15s_vs_sustained_within_recording"] = {
            "ici_s": _paired_stat(early_ici, late_ici),
            "caw_dur_s": _paired_stat(early_dur, late_dur),
            "f0_med_hz": _paired_stat(early_f0, late_f0),
        }
        st.update(3, 3)

    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    run.note(
        f"PrimaryA owl/hawk={report['PRIMARY_A_owl_vs_hawk_bout_syntax_28d']['auc']} "
        f"(Holm p={report['PRIMARY_A_owl_vs_hawk_bout_syntax_28d']['holm_p']}); "
        f"PrimaryB order_diff={report['PRIMARY_B_within_bout_order_shuffle_5ctx']['real_minus_shuffled']} "
        f"(Holm p={report['PRIMARY_B_within_bout_order_shuffle_5ctx']['holm_p']})"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
