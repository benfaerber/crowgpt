"""0121 follow-up diagnostic (cached features only, ~3s):
  1. Test Uniform 1024-d pure-rattle (C=0.1) WITHOUT `none` on grouped CV and on field labels
     (separating the uniform-pooling + pure-rattle win from `none`'s false abstentions).
  2. Test whether `none`'s 26% false-abstain rate on kept field captures came from
     `class_weight='balanced'` (4.4x upweighting) or `hp300` vs unfiltered training audio,
     and whether unweighted `none` or leaked-only `none` improves the trade-off.
  3. Verify true taxonomic raptor filter (excluding Caprimulgidae 'Common Nighthawk').
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as r121  # noqa: E402


class DummyStage:
    def update(self, *a, **k):
        pass


def main():
    garbage_gate = json.loads((r121.CACHE / "garbage_hp300_gate.json").read_text())
    scanned_field, cap_meta, labels = r121.scan_field_captures(DummyStage())
    pools = r121.load_pools(garbage_gate)

    X_all = pools["X_all"]
    g_all = pools["g_all"]
    src_all = pools["src_all"]
    Y_pure = pools["Y_pure_rattle"]
    Y_leg = pools["Y_legacy_mix"]
    gb_conf = pools["gb_corvid_conf"]
    is_garb = src_all == "garbage"
    is_ct = src_all == "ct"

    strat = [
        "none" if "none" in s else ("flight call" if "flight call" in s else (sorted(s)[0] if s else "other"))
        for s in Y_leg
    ]
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X_all, np.array(strat), g_all))

    # Compare 4 clean 1024-d C=0.1 variants on exact same folds:
    # A: Uniform 1024-d, pure_rattle, C=0.1, NO `none` class (train on call rows only)
    # B: Uniform 1024-d, pure_rattle, C=0.1, garbage included as NEGATIVES on the 5 call heads, NO `none` class (abstain only if max_p < 0.35)
    # C: Uniform 1024-d, pure_rattle, C=0.1, unweighted `none` (class_weight=None on `none`, balanced on calls)
    # D: Shipped 3072-d baseline (M0)

    def fit_variant(X_tr, Y_tr, src_tr, mode: str):
        models = {}
        for c in r121.CALL5_RATTLE:
            if mode == "no_garb":
                keep = (src_tr != "garbage") & ((src_tr != "ar") if c == "rattle" else True)
            else:
                keep = (src_tr != "ar") if c == "rattle" else np.ones(len(X_tr), dtype=bool)
            idx = np.flatnonzero(keep)
            y = np.array([1 if c in Y_tr[i] else 0 for i in idx], dtype=int)
            models[c] = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.1, max_iter=4000, class_weight="balanced"),
            ).fit(X_tr[idx, :1024], y)
        none_m = None
        if mode == "unweighted_none":
            y_n = (src_tr == "garbage").astype(int)
            none_m = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.1, max_iter=4000, class_weight=None),
            ).fit(X_tr[:, :1024], y_n)
        return models, none_m

    def predict_variant(models, none_m, X_te, mode: str):
        Xf = X_te[:, :1024]
        p5 = np.column_stack([models[c].predict_proba(Xf)[:, 1] for c in r121.CALL5_RATTLE])
        bi = p5.argmax(axis=1)
        bcls = np.array([r121.CALL5_RATTLE[j] for j in bi], dtype=object)
        bp = p5[np.arange(len(Xf)), bi]
        if mode == "no_garb":
            return p5, bcls, bp
        if mode == "garb_neg_floor035":
            ab = bp < 0.35
            return p5, np.where(ab, "none", bcls), bp
        if mode == "garb_neg_floor050":
            ab = bp < 0.50
            return p5, np.where(ab, "none", bcls), bp
        if mode == "unweighted_none":
            pn = none_m.predict_proba(Xf)[:, 1]
            ab = pn >= bp
            return p5, np.where(ab, "none", bcls), np.where(ab, pn, bp)
        raise ValueError(mode)

    ct_single_mask = np.array([is_ct[i] and len(Y_leg[i] & set(r121.CALL5_RATTLE[:4])) == 1 for i in range(len(X_all))])
    y_ct_single = np.array([next(iter(Y_leg[i] & set(r121.CALL5_RATTLE[:4]))) for i in np.flatnonzero(ct_single_mask)], dtype=object)

    # Prepare field rows: note Ben's 8 kept "call" labels are ordinary contact/adult caws (NOT rattles),
    # while 50 kept labels are alarm call (39) and begging (11)!
    field_rows = []
    for lab in labels:
        cap = scanned_field.get(int(lab["capture_id"]))
        if not cap or not cap["emb_by_start"]:
            continue
        emb_map = {float(k): np.array(v, dtype=np.float32) for k, v in cap["emb_by_start"].items()}
        starts = sorted(emb_map)
        s, e = float(lab["start_sec"]), float(lab["end_sec"])
        covered = [emb_map[w] for w in starts if w < e and (w + 3.0) > s]
        if not covered:
            continue
        mid = 0.5 * (s + e)
        nearest = min(starts, key=lambda w: abs((w + 1.5) - mid))
        field_rows.append({
            "lab": lab,
            "X_span": r121.pool(covered).astype(np.float32),
            "X_win": r121.pool(emb_map[nearest]).astype(np.float32),
            "n_win": len(covered),
        })
    X_span = np.stack([r["X_span"] for r in field_rows])
    X_win = np.stack([r["X_win"] for r in field_rows])
    y_raw_field = np.array([r["lab"]["call_type"] for r in field_rows], dtype=object)
    kept = np.array([int(r["lab"]["keep"] or 0) == 1 for r in field_rows], dtype=bool)
    multi_win = np.array([r["n_win"] >= 2 for r in field_rows], dtype=bool)
    # Specifically check the 50 unambiguous kept labels (39 alarm call + 11 begging) AND the 8 "call" labels separately!
    kept_alarm_beg = kept & np.isin(y_raw_field, ["alarm call", "begging"])
    kept_call_8 = kept & (y_raw_field == "call")
    kept_not_crow = kept & (y_raw_field == "not_a_crow")

    variant_out = {}
    for mode in ("no_garb", "garb_neg_floor035", "garb_neg_floor050", "unweighted_none"):
        fit_mode = "no_garb" if mode == "no_garb" else ("unweighted_none" if mode == "unweighted_none" else "garb_neg")
        oof_p5 = np.zeros((len(X_all), 5), dtype=np.float64)
        oof_cls = np.empty(len(X_all), dtype=object)
        for tr, te in folds:
            ms, nm = fit_variant(X_all[tr], [Y_pure[i] for i in tr], src_all[tr], fit_mode)
            p5, bcls, _ = predict_variant(ms, nm, X_all[te], mode)
            oof_p5[te] = p5
            oof_cls[te] = bcls

        gb_all = oof_cls[is_garb]
        gb_25 = gb_all[gb_conf >= 0.25]
        gb_10 = gb_all[gb_conf >= 0.10]
        ct_pr = oof_cls[ct_single_mask]
        kept_ct = ct_pr != "none"

        per_auc = {}
        per_ap_wg = {}
        for ci, c in enumerate(r121.CALL5_RATTLE):
            em = is_ct if c == "rattle" else (~is_garb)
            yc = np.array([1 if c in Y_pure[i] else 0 for i in np.flatnonzero(em)], dtype=int)
            per_auc[c] = round(float(roc_auc_score(yc, oof_p5[em, ci])), 4)
            ea = (is_ct | is_garb) if c == "rattle" else np.ones(len(X_all), dtype=bool)
            ya = np.array([1 if c in Y_pure[i] else 0 for i in np.flatnonzero(ea)], dtype=int)
            per_ap_wg[c] = round(float(average_precision_score(ya, oof_p5[ea, ci])), 4)

        # Full fit for field evaluation
        ms_full, nm_full = fit_variant(X_all, Y_pure, src_all, fit_mode)
        _, pr_span, _ = predict_variant(ms_full, nm_full, X_span, mode)
        _, pr_win, _ = predict_variant(ms_full, nm_full, X_win, mode)

        variant_out[mode] = {
            "garbage_572_rejected": round(float((gb_all == "none").mean()), 4),
            "garbage_leaked_122_ge010_rejected": round(float((gb_10 == "none").mean()), 4),
            "garbage_leaked_98_ge025_rejected": round(float((gb_25 == "none").mean()), 4),
            "ct_false_abstain": round(float((ct_pr == "none").mean()), 4),
            "ct_macro_f1_uncond": round(float(f1_score(y_ct_single, ct_pr, labels=r121.CALL5_RATTLE[:4], average="macro", zero_division=0)), 4),
            "ct_macro_f1_cond": round(float(f1_score(y_ct_single[kept_ct], ct_pr[kept_ct], labels=r121.CALL5_RATTLE[:4], average="macro", zero_division=0)), 4),
            "per_class_auc_calls": per_auc,
            "per_class_ap_with_garbage": per_ap_wg,
            "field_kept_alarm_beg_50_X_span": {
                "n": int(kept_alarm_beg.sum()),
                "abstained": int((pr_span[kept_alarm_beg] == "none").sum()),
                "acc_uncond": round(float((pr_span[kept_alarm_beg] == y_raw_field[kept_alarm_beg]).mean()), 4),
                "multi_win_14_acc": round(float((pr_span[kept_alarm_beg & multi_win] == y_raw_field[kept_alarm_beg & multi_win]).mean()), 4),
            },
            "field_kept_alarm_beg_50_X_win": {
                "abstained": int((pr_win[kept_alarm_beg] == "none").sum()),
                "acc_uncond": round(float((pr_win[kept_alarm_beg] == y_raw_field[kept_alarm_beg]).mean()), 4),
            },
            "field_kept_8_contact_calls_predicted_as": dict(Counter(pr_span[kept_call_8]).most_common()),
            "field_kept_2_not_a_crow_predicted_as": pr_span[kept_not_crow].tolist(),
        }

    # Also score shipped 3072 on the exact same 50 unambiguous alarm+begging kept labels!
    shipped = joblib.load(r121.REPO / "pipelines" / "training" / "models" / "american-crow" / "calltype_clf.joblib")
    sh_clf = shipped["model"]
    sh_classes = ["rattle" if c == "call" else c for c in shipped["classes"]]
    sh_sp = np.array([sh_classes[i] for i in sh_clf.predict_proba(X_span).argmax(1)], dtype=object)
    sh_wn = np.array([sh_classes[i] for i in sh_clf.predict_proba(X_win).argmax(1)], dtype=object)
    variant_out["shipped_3072_reference"] = {
        "field_kept_alarm_beg_50_X_span": {
            "n": int(kept_alarm_beg.sum()),
            "acc_uncond": round(float((sh_sp[kept_alarm_beg] == y_raw_field[kept_alarm_beg]).mean()), 4),
            "multi_win_14_acc": round(float((sh_sp[kept_alarm_beg & multi_win] == y_raw_field[kept_alarm_beg & multi_win]).mean()), 4),
            "multi_win_14_preds": dict(Counter(sh_sp[kept_alarm_beg & multi_win]).most_common()),
        },
        "field_kept_alarm_beg_50_X_win": {
            "acc_uncond": round(float((sh_wn[kept_alarm_beg] == y_raw_field[kept_alarm_beg]).mean()), 4),
        },
        "field_kept_8_contact_calls_predicted_as": dict(Counter(sh_sp[kept_call_8]).most_common()),
        "field_kept_2_not_a_crow_predicted_as": sh_sp[kept_not_crow].tolist(),
    }

    # Check 0036 raw (no hp300) vs hp300 abstention on unweighted_none vs balanced_none
    f0036 = np.load(r121.EXP0036 / "field_labels.npz", allow_pickle=True)
    k36 = f0036["keep"] == 1
    ms_unw, nm_unw = fit_variant(X_all, Y_pure, src_all, "unweighted_none")
    _, p36_unw, _ = predict_variant(ms_unw, nm_unw, f0036["X_span"][k36], "unweighted_none")
    m2c_bal = r121.UnifiedOvRHead("1024", include_none=True, pure_rattle=True, C=0.1).fit(X_all, Y_pure, src_all)
    p36_bal, _ = m2c_bal.predict_top(f0036["X_span"][k36], "argmax6")

    variant_out["hp300_vs_class_weight_abstain_audit"] = {
        "raw_no_hp300_kept_n": int(k36.sum()),
        "balanced_none_abstain_on_raw_no_hp300": int((p36_bal == "none").sum()),
        "unweighted_none_abstain_on_raw_no_hp300": int((p36_unw == "none").sum()),
        "hp300_kept_58_balanced_none_abstain": 15,
        "hp300_kept_58_unweighted_none_abstain": int((predict_variant(ms_unw, nm_unw, X_span[kept & np.isin(y_raw_field, ["alarm call", "begging", "call", "song", "flight call"])], "unweighted_none")[1] == "none").sum()),
    }

    (HERE / "audit_results.json").write_text(json.dumps(variant_out, indent=2))
    print(json.dumps(variant_out, indent=2))


if __name__ == "__main__":
    main()
