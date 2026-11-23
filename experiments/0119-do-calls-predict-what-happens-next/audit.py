"""0119 post-hoc forensic audit of Primary B (within-window tail/phase & isolated caws)
and S_C1 (3-second silent-pause baseline for begging cessation).

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0119-do-calls-predict-what-happens-next/audit.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import warnings
from pathlib import Path

import tempfile
import joblib
import librosa
import numpy as np
import soundfile as sf
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as r119  # noqa: E402
import scan as s119  # noqa: E402

for _sub in ("pipelines/training", "pipelines/representation", "analyzer/src"):
    sys.path.insert(0, str(r119.REPO / _sub))


class DummyStage:
    def update(self, *args, **kwargs):
        pass


def main():
    catalogue = json.loads((r119.CACHE / "catalogue.json").read_text())
    refs = r119.FrozenReferenceHeads()
    built = r119.build_events(catalogue, refs, DummyStage())

    pB = built["B_pairs"]
    clf_obj = joblib.load(r119.REPO / "pipelines" / "training" / "models" / "american-crow" / "calltype_clf.joblib")
    calltype_clf = clf_obj["model"] if isinstance(clf_obj, dict) and "model" in clf_obj else clf_obj
    ct_classes = list(getattr(calltype_clf, "classes_", []))

    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer

    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        bn_analyzer = Analyzer()

    def embed_buf_3s(buf: np.ndarray) -> np.ndarray | None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tf:
            sf.write(tf.name, buf, r119.SR)
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                rec_obj = Recording(bn_analyzer, tf.name, min_conf=0.01)
                rec_obj.extract_embeddings()
            if rec_obj.embeddings:
                return np.asarray(rec_obj.embeddings[0]["embeddings"], dtype=np.float32)
        return None

    am_c, cor_c, n_caws_l, last_off_l, h1_l, h2_l, wing_low_l = [], [], [], [], [], [], []
    ct_probs = []
    iso_embs, iso_y, iso_g = [], [], []
    # Also test shifting a 3.0s window to END right at last_caw_offset + 0.15s (so neither cont nor stop has a silent right half!)
    aligned_embs, aligned_y, aligned_g = [], [], []

    for pair in pB:
        rec_name = f"r{pair['rec_id']}"
        tbl = r119.load_window_table(rec_name, refs)
        with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
            y_wav, _ = librosa.load(pair["path"], sr=r119.SR, mono=True)
        y_band = s119.sosfiltfilt(s119._SOS, y_wav.astype(np.float32))

        pair_iso = []
        pair_aligned = []
        for label_y, side in ((0, pair["cont"]), (1, pair["stop"])):
            t0 = side["t"]
            idx = int(np.argmin(np.abs(tbl["start"] - t0)))
            am_c.append((label_y, float(tbl["american_crow"][idx])))
            cor_c.append((label_y, float(tbl["corvid"][idx])))

            lo = int(round(t0 * r119.SR))
            hi = min(len(y_wav), int(round((t0 + 3.0) * r119.SR)))
            seg_b = y_band[lo:hi]
            seg_raw = y_wav[lo:hi]
            h1 = float(20 * np.log10(np.sqrt(np.mean(seg_b[: len(seg_b) // 2] ** 2)) + 1e-7))
            h2 = float(20 * np.log10(np.sqrt(np.mean(seg_b[len(seg_b) // 2 :] ** 2)) + 1e-7))
            low_e = float(20 * np.log10(np.sqrt(np.mean((seg_raw - seg_b) ** 2)) + 1e-7))
            h1_l.append((label_y, h1))
            h2_l.append((label_y, h2))
            wing_low_l.append((label_y, low_e))

            found = r119.exp103.segment_caws_in_windows(
                y_wav, r119.SR, [(t0, min(len(y_wav) / r119.SR, t0 + 3.0))], max_caws=100
            )
            n_caws_l.append((label_y, len(found)))
            last_off = max((c["offset"] - t0 for c in found), default=1.5)
            last_off_l.append((label_y, float(last_off)))

            if found:
                c_pick = found[-1]
                c0 = max(0, int(round(c_pick["onset"] * r119.SR)))
                c1 = min(len(y_wav), int(round(c_pick["offset"] * r119.SR)))
                clip = y_wav[c0:c1].astype(np.float32).copy()
                pk = float(np.max(np.abs(clip)))
                if pk > 1e-6:
                    clip = clip / pk * 0.5
                buf = np.zeros(3 * r119.SR, dtype=np.float32)
                L = min(len(clip), len(buf))
                start_put = (len(buf) - L) // 2
                buf[start_put : start_put + L] = clip[:L]
                e_iso = embed_buf_3s(buf)
                if e_iso is not None:
                    pair_iso.append(e_iso)

                # Right-aligned 3.0s real-audio window ending at c_pick["offset"] + 0.10s
                end_sample = min(len(y_wav), int(round((c_pick["offset"] + 0.10) * r119.SR)))
                start_sample = max(0, end_sample - 3 * r119.SR)
                if end_sample - start_sample == 3 * r119.SR:
                    e_al = embed_buf_3s(y_wav[start_sample:end_sample].astype(np.float32))
                    if e_al is not None:
                        pair_aligned.append(e_al)

            e = side["embedding"]
            vec3072 = np.concatenate([e, np.zeros_like(e), e])[None, :]
            ct_probs.append((label_y, calltype_clf.predict_proba(vec3072)[0]))

        if len(pair_iso) == 2:
            iso_embs.extend(pair_iso)
            iso_y.extend([0, 1])
            iso_g.extend([pair["observer"], pair["observer"]])
        if len(pair_aligned) == 2:
            aligned_embs.extend(pair_aligned)
            aligned_y.extend([0, 1])
            aligned_g.extend([pair["observer"], pair["observer"]])

    XB = np.stack([s["embedding"] for p in pB for s in (p["cont"], p["stop"])])
    yB = np.array([0, 1] * len(pB), dtype=int)
    gB = np.array([g for p in pB for g in (p["observer"], p["observer"])])
    foldsB = list(GroupKFold(n_splits=5).split(XB, yB, gB))

    Z_orig = np.array(
        [[s["crow_rms_db"], s["snr_db"], s["p_several"], s["duty_u"]] for p in pB for s in (p["cont"], p["stop"])],
        dtype=np.float32,
    )
    Z_phase = np.array(
        [
            [
                am_c[i][1],
                cor_c[i][1],
                n_caws_l[i][1],
                last_off_l[i][1],
                h1_l[i][1],
                h2_l[i][1],
                h2_l[i][1] - h1_l[i][1],
                wing_low_l[i][1],
            ]
            for i in range(len(yB))
        ],
        dtype=np.float32,
    )
    Z_all = np.hstack([Z_orig, Z_phase])

    names = [
        "am_crow_conf",
        "corvid_conf",
        "n_caws",
        "last_caw_offset_s",
        "h1_db",
        "h2_db",
        "h2_minus_h1_db",
        "subband_low_db",
    ]
    univariate = {}
    for idx_c, nm in enumerate(names):
        v0 = Z_phase[yB == 0, idx_c]
        v1 = Z_phase[yB == 1, idx_c]
        univariate[nm] = {
            "cont_median": round(float(np.median(v0)), 4),
            "stop_median": round(float(np.median(v1)), 4),
            "auc": round(float(roc_auc_score(yB, Z_phase[:, idx_c])), 4),
        }

    ct_arr = np.array([x[1] for x in ct_probs])
    calltype_summary = {}
    for ci, cname in enumerate(ct_classes):
        calltype_summary[cname] = {
            "cont_mean": round(float(ct_arr[yB == 0, ci].mean()), 4),
            "stop_mean": round(float(ct_arr[yB == 1, ci].mean()), 4),
            "auc": round(float(roc_auc_score(yB, ct_arr[:, ci])), 4),
        }

    iso_X = np.stack(iso_embs)
    iso_y_arr = np.array(iso_y, dtype=int)
    iso_g_arr = np.array(iso_g)
    folds_iso = list(GroupKFold(n_splits=5).split(iso_X, iso_y_arr, iso_g_arr))
    iso_auc = float(roc_auc_score(iso_y_arr, r119.oof_scores(iso_X, iso_y_arr, folds_iso, Z=None, C=0.05)))

    al_X = np.stack(aligned_embs)
    al_y_arr = np.array(aligned_y, dtype=int)
    al_g_arr = np.array(aligned_g)
    folds_al = list(GroupKFold(n_splits=5).split(al_X, al_y_arr, al_g_arr))
    al_auc = float(roc_auc_score(al_y_arr, r119.oof_scores(al_X, al_y_arr, folds_al, Z=None, C=0.05)))

    # S_C1 silent-pause baseline
    silent_stops, adult_stops, beg_stops, multi_beg_stops = [], [], [], []
    for rec in catalogue:
        tbl = r119.load_window_table(f"r{rec['id']}", refs)
        if tbl is None:
            continue
        starts = tbl["start"]
        crow_any = tbl["corvid"] >= 0.25
        if int(np.sum(crow_any & (tbl["s_beg"] >= 0.0))) < 2:
            continue
        for i, t in enumerate(starts):
            t_f = float(t)
            if t_f < 9.0:
                continue
            pre_idx = np.flatnonzero((starts >= max(0.0, t_f - 12.0) - 0.08) & (starts < t_f - 0.08))
            if len(pre_idx) < 3:
                continue
            if int(np.sum(crow_any[pre_idx] & (tbl["s_beg"][pre_idx] >= refs.T_beg))) < 2:
                continue
            if int(np.sum(crow_any[pre_idx] & (tbl["s_beg"][pre_idx] >= 0.0))) < 1:
                continue
            ok_tail, _ = r119.live_tail(tbl, i, t_f + 3.0, t_f + 18.0)
            if not ok_tail:
                continue
            post_idx = r119.span_indices(starts, t_f + 3.0, t_f + 18.0)
            if post_idx is None:
                continue
            p_any = int(np.sum((tbl["corvid"][post_idx] >= 0.15) & (tbl["s_beg"][post_idx] >= refs.T_beg)))
            p_cont = int(np.sum((tbl["corvid"][post_idx] >= 0.25) & (tbl["s_beg"][post_idx] >= refs.T_beg)))
            outcome = 1 if p_any == 0 else (0 if p_cont >= 2 else -1)
            if outcome not in (0, 1):
                continue

            if (tbl["american_crow"][i] >= 0.25) and (tbl["raptor"][i] < 0.05) and (tbl["s_beg"][i] < refs.T_beg):
                adult_stops.append(outcome)
            elif tbl["corvid"][i] < 0.15 and tbl["raptor"][i] < 0.05:
                silent_stops.append(outcome)
            elif crow_any[i] and tbl["s_beg"][i] >= 0.0 and tbl["raptor"][i] < 0.05:
                beg_stops.append(outcome)
                if tbl["p_several"][i] >= refs.T_crowd:
                    multi_beg_stops.append(outcome)

    report = {
        "Primary_B_audit": {
            "univariate_phase_and_conf": univariate,
            "phase_conf_only_oof_auc": round(
                float(roc_auc_score(yB, r119.oof_scores(Z_phase, yB, foldsB, Z=None, C=0.05))), 4
            ),
            "birdnet_residualized_on_orig_plus_phase_auc": round(
                float(roc_auc_score(yB, r119.oof_scores(XB, yB, foldsB, Z=Z_all, C=0.05))), 4
            ),
            "calltype_clf_probs": calltype_summary,
            "isolated_last_caw_birdnet_pairs": len(iso_y_arr) // 2,
            "isolated_last_caw_birdnet_auc": round(iso_auc, 4),
            "right_aligned_3s_real_audio_pairs": len(al_y_arr) // 2,
            "right_aligned_3s_real_audio_auc": round(al_auc, 4),
        },
        "S_C1_silent_pause_audit": {
            "ongoing_begging_n": len(beg_stops),
            "ongoing_begging_stop_rate": round(float(np.mean(beg_stops)), 4),
            "multi_bird_begging_n": len(multi_beg_stops),
            "multi_bird_begging_stop_rate": round(float(np.mean(multi_beg_stops)), 4) if multi_beg_stops else None,
            "adult_nonbeg_call_n": len(adult_stops),
            "adult_nonbeg_call_stop_rate": round(float(np.mean(adult_stops)), 4),
            "silent_3s_pause_no_crow_n": len(silent_stops),
            "silent_3s_pause_no_crow_stop_rate": round(float(np.mean(silent_stops)), 4),
        },
    }
    (HERE / "audit_results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
