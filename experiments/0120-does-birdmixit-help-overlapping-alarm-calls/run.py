"""0120 step 2 (CPU/BirdNET): embed separated stems and evaluate pre-declared arms on
0036/overlap_wall.py's exact recording-grouped CV.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0120-does-birdmixit-help-overlapping-alarm-calls/run.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0120-birdmixit-alarms"
EXP0036 = REPO / "experiments" / "0036-what-would-more-labels-buy" / "results"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

T_SINGLE = 0.5826
SR_SEP = 22050
SR_BN = 48000
SLOT_BN = 3 * SR_BN
FLAGS = ["alert", "begging", "softSong", "rattle", "mob"]
_ANALYZER = None


def _init_bn():
    global _ANALYZER
    from birdnetlib.analyzer import Analyzer

    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()


def _embed_chunk(waves_22k: np.ndarray) -> np.ndarray:
    from birdnetlib import Recording

    if len(waves_22k) == 0:
        return np.zeros((0, 1024), dtype=np.float32)
    slots = []
    for w in waves_22k:
        wf = w.astype(np.float32)
        pk = float(np.max(np.abs(wf)))
        if pk > 1e-6 and pk < 0.02:
            wf = wf * (0.05 / pk)
        r48 = librosa.resample(wf, orig_sr=SR_SEP, target_sr=SR_BN)
        buf = np.zeros(SLOT_BN, dtype=np.float32)
        take = min(len(r48), SLOT_BN)
        buf[:take] = r48[:take]
        slots.append(buf)
    out = np.zeros((len(waves_22k), 1024), dtype=np.float32)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tf:
        sf.write(tf.name, np.concatenate(slots), SR_BN)
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            rec = Recording(_ANALYZER, tf.name, min_conf=0.01)
            rec.extract_embeddings()
        for seg in rec.embeddings or []:
            idx = int(round(float(seg["start_time"]) / 3.0))
            if 0 <= idx < len(waves_22k):
                e = np.asarray(seg["embeddings"], dtype=np.float32)
                if np.isfinite(e).all():
                    out[idx] = e
    return out


def embed_stems(stage) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    emb_cache = CACHE / "stem_embeddings.npz"
    stems = np.load(CACHE / "stems_22k.npz")
    wkeys = stems["wkeys"].tolist()
    if emb_cache.exists():
        d = np.load(emb_cache)
        ks = d["wkeys"].tolist()
        stage.update(1, 1, extra="reused stem_embeddings.npz")
        return dict(zip(ks, d["emb1"])), dict(zip(ks, d["emb2"]))

    s1 = stems["stem1"].astype(np.float32)
    s2 = stems["stem2"].astype(np.float32)
    all_waves = np.concatenate([s1, s2], axis=0)
    chunk_sz = 24
    chunks = [all_waves[i : i + chunk_sz] for i in range(0, len(all_waves), chunk_sz)]
    out_chunks = [None] * len(chunks)

    stage.update(0, len(chunks), extra="embedding stems with BirdNET")
    with ProcessPoolExecutor(max_workers=12, initializer=_init_bn) as pool:
        futs = {pool.submit(_embed_chunk, ch): idx for idx, ch in enumerate(chunks)}
        for done, fut in enumerate(as_completed(futs), 1):
            out_chunks[futs[fut]] = fut.result()
            if done % 5 == 0 or done == len(chunks):
                stage.update(done, len(chunks))

    embs = np.concatenate(out_chunks, axis=0)
    e1, e2 = embs[: len(wkeys)], embs[len(wkeys) :]
    np.savez_compressed(emb_cache, wkeys=np.array(wkeys), emb1=e1, emb2=e2)
    return dict(zip(wkeys, e1)), dict(zip(wkeys, e2))


def clf(C: float = 1.0):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000, class_weight="balanced"))


def build_feature_matrix(X_mix: np.ndarray, row_wkeys: list[str], e1_map: dict, e2_map: dict, gate_mask: np.ndarray) -> np.ndarray:
    """[e_mix (1024), 0.5*(e_s1+e_s2) (1024), |e_s1-e_s2| (1024)] when gated, else [e_mix, e_mix, 0]."""
    N = len(X_mix)
    out = np.zeros((N, 3072), dtype=np.float32)
    out[:, :1024] = X_mix
    out[:, 1024:2048] = X_mix
    for i in range(N):
        if gate_mask[i]:
            wk = row_wkeys[i]
            v1 = e1_map.get(wk)
            v2 = e2_map.get(wk)
            if v1 is not None and v2 is not None and np.any(v1 != 0):
                out[i, 1024:2048] = 0.5 * (v1 + v2)
                out[i, 2048:3072] = np.abs(v1 - v2)
    return out


def score_stratum(y: np.ndarray, proba: np.ndarray, pred: np.ndarray) -> dict:
    neg = recall_score(y, pred, pos_label=0, zero_division=0)
    pos = recall_score(y, pred, pos_label=1, zero_division=0)
    return {
        "n": int(len(y)),
        "n_positive": int(y.sum()),
        "prevalence": round(float(y.mean()), 4),
        "average_precision": round(float(average_precision_score(y, proba)), 4),
        "roc_auc": round(float(roc_auc_score(y, proba)), 4),
        "pos_recall": round(float(pos), 4),
        "balanced_accuracy": round(float((neg + pos) / 2.0), 4),
    }


def evaluate_arm_matrix(X_feat: np.ndarray, flags: list[dict], groups: np.ndarray, counts: np.ndarray, C: float = 1.0) -> tuple[dict, dict]:
    strata = {"one_crow": counts == 1, "two_or_more": counts >= 2}
    report = {}
    oof_store = {}
    for flag in FLAGS:
        asked = np.array([flag in f for f in flags])
        y = np.array([1 if f.get(flag) else 0 for f, a in zip(flags, asked) if a])
        Xa, ga, ca = X_feat[asked], groups[asked], counts[asked]
        proba = np.zeros(len(y), dtype=np.float64)
        pred = np.zeros(len(y), dtype=int)
        for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(Xa, y, ga):
            m = clf(C=C).fit(Xa[tr], y[tr])
            proba[te] = m.predict_proba(Xa[te])[:, 1]
            pred[te] = m.predict(Xa[te])
        entry = {"n_positive_total": int(y.sum())}
        for sname, mask in strata.items():
            sub = ca == 1 if sname == "one_crow" else ca >= 2
            entry[sname] = score_stratum(y[sub], proba[sub], pred[sub])
        report[flag] = entry
        oof_store[flag] = {"y": y, "proba": proba, "pred": pred, "groups": ga, "counts": ca}
    return report, oof_store


def evaluate_arm_b_blend(X_mix: np.ndarray, row_wkeys: list[str], e1_map: dict, e2_map: dict, gate_mask: np.ndarray, flags: list[dict], groups: np.ndarray, counts: np.ndarray, C: float = 1.0, agg: str = "max") -> tuple[dict, dict]:
    report = {}
    oof_store = {}
    for flag in FLAGS:
        asked = np.array([flag in f for f in flags])
        y = np.array([1 if f.get(flag) else 0 for f, a in zip(flags, asked) if a])
        Xa, ga, ca = X_mix[asked], groups[asked], counts[asked]
        wka = [wk for wk, a in zip(row_wkeys, asked) if a]
        gma = gate_mask[asked]
        proba = np.zeros(len(y), dtype=np.float64)
        pred = np.zeros(len(y), dtype=int)
        for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(Xa, y, ga):
            m_all = clf(C=C).fit(Xa[tr], y[tr])
            # Single-crow voice model fit on one-crow training rows (fallback to m_all if sparse)
            one_tr = tr[ca[tr] == 1]
            m_one = clf(C=C).fit(Xa[one_tr], y[one_tr]) if len(one_tr) >= 50 and 0 < y[one_tr].sum() < len(one_tr) else m_all
            p_mix = m_all.predict_proba(Xa[te])[:, 1]
            for local_i, idx in enumerate(te):
                pm = float(p_mix[local_i])
                if gma[idx]:
                    v1 = e1_map.get(wka[idx])
                    v2 = e2_map.get(wka[idx])
                    if v1 is not None and v2 is not None and np.any(v1 != 0):
                        ps = m_one.predict_proba(np.stack([v1, v2]))[:, 1]
                        p_stem = float(np.max(ps) if agg == "max" else np.mean(ps))
                        pm = 0.5 * pm + 0.5 * p_stem
                proba[idx] = pm
                pred[idx] = 1 if pm >= 0.5 else 0
        entry = {"n_positive_total": int(y.sum())}
        for sname in ("one_crow", "two_or_more"):
            sub = ca == 1 if sname == "one_crow" else ca >= 2
            entry[sname] = score_stratum(y[sub], proba[sub], pred[sub])
        report[flag] = entry
        oof_store[flag] = {"y": y, "proba": proba, "pred": pred, "groups": ga, "counts": ca}
    return report, oof_store


def direct_mob_vs_alert(X_feat: np.ndarray, flags: list[dict], groups: np.ndarray, counts: np.ndarray, C: float = 1.0) -> dict:
    """Exclusive mob vs exclusive alert, fit across all segments, scored on one_crow and two_or_more."""
    keep, y_list = [], []
    for i, f in enumerate(flags):
        m = bool(f.get("mob"))
        a = bool(f.get("alert"))
        if m != a:
            keep.append(i)
            y_list.append(1 if m else 0)
    idx = np.array(keep, dtype=int)
    X_sub, y_sub, g_sub, c_sub = X_feat[idx], np.array(y_list, dtype=int), groups[idx], counts[idx]
    proba = np.zeros(len(y_sub), dtype=np.float64)
    pred = np.zeros(len(y_sub), dtype=int)
    for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X_sub, y_sub, g_sub):
        m = clf(C=C).fit(X_sub[tr], y_sub[tr])
        proba[te] = m.predict_proba(X_sub[te])[:, 1]
        pred[te] = m.predict(X_sub[te])
    return {
        "one_crow": score_stratum(y_sub[c_sub == 1], proba[c_sub == 1], pred[c_sub == 1]),
        "two_or_more": score_stratum(y_sub[c_sub >= 2], proba[c_sub >= 2], pred[c_sub >= 2]),
    }


def bootstrap_delta_alarm_ap(base_oof: dict, cand_oof: dict, n_boot: int = 2000, seed: int = 0) -> dict:
    # Recording-clustered bootstrap over unique groups in two_or_more for alert and mob
    all_groups = sorted(
        set(base_oof["alert"]["groups"][base_oof["alert"]["counts"] >= 2].tolist())
        | set(base_oof["mob"]["groups"][base_oof["mob"]["counts"] >= 2].tolist())
    )
    by_flag_group = {}
    for flag in ("alert", "mob"):
        d = base_oof[flag]
        mask2 = d["counts"] >= 2
        g_map = defaultdict(list)
        for pos_idx in np.flatnonzero(mask2):
            g_map[str(d["groups"][pos_idx])].append(int(pos_idx))
        by_flag_group[flag] = g_map

    obs_base = 0.5 * (
        average_precision_score(base_oof["alert"]["y"][base_oof["alert"]["counts"] >= 2], base_oof["alert"]["proba"][base_oof["alert"]["counts"] >= 2])
        + average_precision_score(base_oof["mob"]["y"][base_oof["mob"]["counts"] >= 2], base_oof["mob"]["proba"][base_oof["mob"]["counts"] >= 2])
    )
    obs_cand = 0.5 * (
        average_precision_score(cand_oof["alert"]["y"][cand_oof["alert"]["counts"] >= 2], cand_oof["alert"]["proba"][cand_oof["alert"]["counts"] >= 2])
        + average_precision_score(cand_oof["mob"]["y"][cand_oof["mob"]["counts"] >= 2], cand_oof["mob"]["proba"][cand_oof["mob"]["counts"] >= 2])
    )

    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(n_boot):
        picked = [all_groups[j] for j in rng.integers(0, len(all_groups), len(all_groups))]
        aps_b, aps_c = [], []
        ok = True
        for flag in ("alert", "mob"):
            rows = [r for g in picked for r in by_flag_group[flag].get(g, ())]
            if not rows:
                ok = False
                break
            arr = np.array(rows, dtype=int)
            yb = base_oof[flag]["y"][arr]
            if yb.sum() == 0 or yb.sum() == len(yb):
                ok = False
                break
            aps_b.append(average_precision_score(yb, base_oof[flag]["proba"][arr]))
            aps_c.append(average_precision_score(yb, cand_oof[flag]["proba"][arr]))
        if ok:
            deltas.append(float(0.5 * (aps_c[0] + aps_c[1]) - 0.5 * (aps_b[0] + aps_b[1])))

    return {
        "baseline_mean_alarm_ap_2plus": round(float(obs_base), 4),
        "candidate_mean_alarm_ap_2plus": round(float(obs_cand), 4),
        "delta_mean_alarm_ap_2plus": round(float(obs_cand - obs_base), 4),
        "ci95": [
            round(float(np.percentile(deltas, 2.5)), 4),
            round(float(np.percentile(deltas, 97.5)), 4),
        ],
    }


def summarize_arm(rep: dict) -> dict:
    one_mean = float(np.mean([rep[f]["one_crow"]["average_precision"] for f in FLAGS]))
    two_alarm_ap = 0.5 * (rep["alert"]["two_or_more"]["average_precision"] + rep["mob"]["two_or_more"]["average_precision"])
    two_alarm_bacc = 0.5 * (rep["alert"]["two_or_more"]["balanced_accuracy"] + rep["mob"]["two_or_more"]["balanced_accuracy"])
    return {
        "two_or_more_mean_alarm_AP": round(two_alarm_ap, 4),
        "two_or_more_mean_alarm_bal_acc": round(two_alarm_bacc, 4),
        "two_or_more_alert_AP": rep["alert"]["two_or_more"]["average_precision"],
        "two_or_more_mob_AP": rep["mob"]["two_or_more"]["average_precision"],
        "two_or_more_alert_bal_acc": rep["alert"]["two_or_more"]["balanced_accuracy"],
        "two_or_more_mob_bal_acc": rep["mob"]["two_or_more"]["balanced_accuracy"],
        "one_crow_5flag_mean_AP": round(one_mean, 4),
    }


def main():
    run = Run("0120 BirdMixIT alarm evaluation", ["embed_stems", "evaluate"])
    keyed = np.load(EXP0036 / "crowtools_keyed.npz", allow_pickle=True)
    flags_map = {r["key"]: r["flags"] for r in json.loads((EXP0036 / "crowtools_flags.json").read_text())}
    groups = keyed["groups"]
    starts = keyed["starts"]
    X1024 = keyed["X"][:, :1024].astype(np.float32)
    flags = [flags_map[f"{g}-{s}"] for g, s in zip(groups, starts)]
    counts = np.array([int(f.get("crowCount") or 0) for f in flags], dtype=int)

    p_sev = np.load(CACHE / "p_several_oof.npy")
    row_wkeys = json.loads((CACHE / "row_wkeys.json").read_text())

    with run.stage("embed_stems") as stage:
        e1_map, e2_map = embed_stems(stage)

    gate_oof = p_sev >= T_SINGLE
    gate_oracle = counts >= 2

    with run.stage("evaluate") as stage:
        stage.update(0, 6, extra="baseline unseparated")
        X_arm_a = build_feature_matrix(X1024, row_wkeys, e1_map, e2_map, gate_oof)
        X_arm_c = build_feature_matrix(X1024, row_wkeys, e1_map, e2_map, gate_oracle)

        base_rep, base_oof = evaluate_arm_matrix(X1024, flags, groups, counts, C=1.0)
        stage.update(1, 6, extra="Arm A gated C=1.0")
        arma_rep, arma_oof = evaluate_arm_matrix(X_arm_a, flags, groups, counts, C=1.0)
        stage.update(2, 6, extra="Arm A & Baseline C=0.05")
        base_c05_rep, base_c05_oof = evaluate_arm_matrix(X1024, flags, groups, counts, C=0.05)
        arma_c05_rep, arma_c05_oof = evaluate_arm_matrix(X_arm_a, flags, groups, counts, C=0.05)
        stage.update(3, 6, extra="Arm B blend")
        armb_max_rep, armb_max_oof = evaluate_arm_b_blend(X1024, row_wkeys, e1_map, e2_map, gate_oof, flags, groups, counts, C=1.0, agg="max")
        armb_mean_rep, armb_mean_oof = evaluate_arm_b_blend(X1024, row_wkeys, e1_map, e2_map, gate_oof, flags, groups, counts, C=1.0, agg="mean")
        stage.update(4, 6, extra="Arm C oracle")
        armc_rep, armc_oof = evaluate_arm_matrix(X_arm_c, flags, groups, counts, C=1.0)
        armc_c05_rep, _ = evaluate_arm_matrix(X_arm_c, flags, groups, counts, C=0.05)

        stage.update(5, 6, extra="direct mob vs alert + bootstrap")
        boot_a = bootstrap_delta_alarm_ap(base_oof, arma_oof)
        boot_a_c05 = bootstrap_delta_alarm_ap(base_c05_oof, arma_c05_oof)
        boot_b_max = bootstrap_delta_alarm_ap(base_oof, armb_max_oof)
        boot_b_mean = bootstrap_delta_alarm_ap(base_oof, armb_mean_oof)

        direct = {
            "baseline_C1.0": direct_mob_vs_alert(X1024, flags, groups, counts, C=1.0),
            "arm_A_gated_C1.0": direct_mob_vs_alert(X_arm_a, flags, groups, counts, C=1.0),
            "baseline_C0.05": direct_mob_vs_alert(X1024, flags, groups, counts, C=0.05),
            "arm_A_gated_C0.05": direct_mob_vs_alert(X_arm_a, flags, groups, counts, C=0.05),
            "arm_C_oracle_C0.05": direct_mob_vs_alert(X_arm_c, flags, groups, counts, C=0.05),
        }

        base_sum = summarize_arm(base_rep)
        arma_sum = summarize_arm(arma_rep)
        armb_max_sum = summarize_arm(armb_max_rep)
        armb_mean_sum = summarize_arm(armb_mean_rep)

        def passes_ship_bar(boot_res: dict, cand_sum: dict, ref_sum: dict) -> bool:
            return bool(
                boot_res["delta_mean_alarm_ap_2plus"] >= 0.030
                and boot_res["ci95"][0] > 0.0
                and (ref_sum["one_crow_5flag_mean_AP"] - cand_sum["one_crow_5flag_mean_AP"]) <= 0.010
            )

        ship_a = passes_ship_bar(boot_a, arma_sum, base_sum)
        ship_b_max = passes_ship_bar(boot_b_max, armb_max_sum, base_sum)
        ship_b_mean = passes_ship_bar(boot_b_mean, armb_mean_sum, base_sum)

        results = {
            "gating_diagnostics": {
                "n_segments": int(len(counts)),
                "true_two_or_more": int((counts >= 2).sum()),
                "oof_gated_ge_0.5826": int(gate_oof.sum()),
                "recall_on_true_two_or_more": round(float(gate_oof[counts >= 2].mean()), 4),
                "false_gate_on_one_crow": round(float(gate_oof[counts == 1].mean()), 4),
                "separated_unique_windows": int(len(e1_map)),
            },
            "summaries": {
                "baseline_C1.0": base_sum,
                "arm_A_gated_mix_plus_stems_C1.0": arma_sum,
                "arm_B_gated_stem_max_proba_C1.0": armb_max_sum,
                "arm_B_gated_stem_mean_proba_C1.0": armb_mean_sum,
                "arm_C_oracle_C1.0": summarize_arm(armc_rep),
                "secondary_C0.05": {
                    "baseline_C0.05": summarize_arm(base_c05_rep),
                    "arm_A_gated_C0.05": summarize_arm(arma_c05_rep),
                    "arm_C_oracle_C0.05": summarize_arm(armc_c05_rep),
                },
            },
            "primary_bootstrap_deltas": {
                "arm_A_vs_baseline_C1.0": boot_a,
                "arm_B_max_vs_baseline_C1.0": boot_b_max,
                "arm_B_mean_vs_baseline_C1.0": boot_b_mean,
                "secondary_arm_A_vs_baseline_C0.05": boot_a_c05,
            },
            "direct_mob_vs_alert_contrast": direct,
            "ship_gate_verdict": {
                "bar_delta_mean_alarm_AP": 0.030,
                "arm_A_passes": ship_a,
                "arm_B_max_passes": ship_b_max,
                "arm_B_mean_passes": ship_b_mean,
                "ship_birdmixit_into_analyzer": bool(ship_a or ship_b_max or ship_b_mean),
            },
            "per_flag_full": {
                "baseline_C1.0": base_rep,
                "arm_A_gated_C1.0": arma_rep,
                "arm_B_max_C1.0": armb_max_rep,
                "arm_B_mean_C1.0": armb_mean_rep,
                "arm_C_oracle_C1.0": armc_rep,
            },
        }
        stage.update(6, 6)

    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({k: v for k, v in results.items() if k != "per_flag_full"}, indent=2))
    run.note(
        f"Arm A delta={boot_a['delta_mean_alarm_ap_2plus']} | Arm B max={boot_b_max['delta_mean_alarm_ap_2plus']} | ship={results['ship_gate_verdict']['ship_birdmixit_into_analyzer']}"
    )


if __name__ == "__main__":
    main()
