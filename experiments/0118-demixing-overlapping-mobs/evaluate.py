"""0118 step 2 (CPU/BirdNET): evaluate Stage 0 count-head recovery + Stage 1 Primary A (0103 dev
caw-level owl vs. hawk on separated stems vs. unseparated multi-crow windows) and Primary B
(0104 video perched owl vs. hawk & within-hawk perched vs. flying on BirdNET stem embeddings).

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0118-demixing-overlapping-mobs/evaluate.py
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
from importlib import util
from pathlib import Path

import joblib
import librosa
import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
OUT_DIR = DATA_DIR / "experiments" / "0118-birdmixit"
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"

sys.path.insert(0, str(EXP112))
import sets  # noqa: E402

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

SR_SEP = 22050
SR_BN = 48000
SLOT_BN = 3 * SR_BN
_ANALYZER = None


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp103_ext = load_module("exp103_ext_0118", sets.EXP103 / "extract_caws.py")
exp103_dev = load_module("exp103_dev_0118", sets.EXP103 / "eval_dev.py")
exp104 = load_module("exp104_0118", sets.EXP104 / "eval.py")


def _init_bn():
    global _ANALYZER
    from birdnetlib.analyzer import Analyzer

    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()


def _embed_chunk(waves_22k: np.ndarray) -> np.ndarray:
    """Embed a chunk of 3.0 s 22.05 kHz waveforms with BirdNET by concatenating 48 kHz slots."""
    from birdnetlib import Recording

    if len(waves_22k) == 0:
        return np.zeros((0, 1024), dtype=np.float32)
    slots = []
    for w in waves_22k:
        r48 = librosa.resample(w.astype(np.float32), orig_sr=SR_SEP, target_sr=SR_BN)
        buf = np.zeros(SLOT_BN, dtype=np.float32)
        take = min(len(r48), SLOT_BN)
        buf[:take] = r48[:take]
        slots.append(buf)
    out = np.zeros((len(waves_22k), 1024), dtype=np.float32)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tf:
        sf.write(tf.name, np.concatenate(slots), SR_BN)
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            rec = Recording(_ANALYZER, tf.name, min_conf=0.05)
            rec.extract_embeddings()
        for seg in rec.embeddings or []:
            idx = int(round(float(seg["start_time"]) / 3.0))
            if 0 <= idx < len(waves_22k):
                e = np.asarray(seg["embeddings"], dtype=np.float32)
                if np.isfinite(e).all():
                    out[idx] = e
    return out


def embed_all_birdnet(waves_22k: np.ndarray, chunk_size: int = 32) -> np.ndarray:
    if len(waves_22k) == 0:
        return np.zeros((0, 1024), dtype=np.float32)
    chunks = [(i, waves_22k[i : i + chunk_size]) for i in range(0, len(waves_22k), chunk_size)]
    out = np.zeros((len(waves_22k), 1024), dtype=np.float32)
    with ProcessPoolExecutor(max_workers=8, initializer=_init_bn) as pool:
        futs = {pool.submit(_embed_chunk, c): i for i, c in chunks}
        for fut in as_completed(futs):
            i = futs[fut]
            res = fut.result()
            out[i : i + len(res)] = res
    return out


def extract_caws_from_windows(waves_22k: np.ndarray, rec_ids: np.ndarray, max_per_rec: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Segment caws on 3.0 s waveforms and keep up to 30 highest-SNR caws per recording."""
    by_rec = defaultdict(list)
    for w, rid in zip(waves_22k, rec_ids.tolist()):
        found = exp103_ext.segment_caws_in_windows(w, SR_SEP, [(0.0, 3.0)], max_caws=30)
        for c in found:
            i0 = max(0, int(round(c["onset"] * SR_SEP)))
            i1 = min(len(w), int(round(c["offset"] * SR_SEP)))
            by_rec[int(rid)].append((float(c["snr"]), exp103_ext.extract_caw_44d(w[i0:i1], SR_SEP)))
    X_list, rid_list = [], []
    for rid in sorted(by_rec):
        top = sorted(by_rec[rid], key=lambda t: t[0], reverse=True)[:max_per_rec]
        for _, feat in top:
            X_list.append(feat)
            rid_list.append(rid)
    if not X_list:
        return np.zeros((0, 44), dtype=np.float32), np.zeros(0, dtype=np.int64)
    return np.stack(X_list), np.array(rid_list, dtype=np.int64)


def holm_pair(p_a: float | None, p_b: float | None) -> tuple[float | None, float | None]:
    if p_a is None or p_b is None:
        return p_a, p_b
    if p_a <= p_b:
        ha = min(1.0, 2 * p_a)
        return round(ha, 4), round(max(ha, min(1.0, p_b)), 4)
    hb = min(1.0, 2 * p_b)
    return round(max(hb, min(1.0, p_a)), 4), round(hb, 4)


def main():
    run = Run("0118 BirdMixIT evaluation", ["stage0_count", "primary_a_dev0103", "primary_b_vid0104"])

    stage0 = json.loads((OUT_DIR / "stage0_metrics.json").read_text())
    s0_audio = np.load(OUT_DIR / "stage0_audio.npz")
    count_head = joblib.load(DATA_DIR / "experiments" / "0109-crow-count" / "count_head.joblib")

    with run.stage("stage0_count") as st:
        mix_embs = embed_all_birdnet(s0_audio["mixes_0db"])
        stem1_embs = embed_all_birdnet(s0_audio["top2_0db"][:, 0, :])
        stem2_embs = embed_all_birdnet(s0_audio["top2_0db"][:, 1, :])
        p_mix = count_head.predict_proba(mix_embs)[:, 1]
        p_s1 = count_head.predict_proba(stem1_embs)[:, 1]
        p_s2 = count_head.predict_proba(stem2_embs)[:, 1]
        stage0["birdnet_count_head_0db"] = {
            "mixture_p_several_median": round(float(np.median(p_mix)), 4),
            "stem1_p_several_median": round(float(np.median(p_s1)), 4),
            "stem2_p_several_median": round(float(np.median(p_s2)), 4),
            "frac_stems_below_mixture": round(float(np.mean(0.5 * (p_s1 + p_s2) < p_mix)), 4),
        }
        st.update(1, 1)

    # Primary A: 0103 dev multi-crow windows — separated stems vs unseparated multi-crow windows
    with run.stage("primary_a_dev0103") as st:
        d103 = np.load(OUT_DIR / "dev0103_stems.npz")
        recs_103 = {r["id"]: r for r in json.loads((sets.CAW_CACHE / "recordings.json").read_text())}

        X_sep, rid_sep = extract_caws_from_windows(d103["stem_waves"], d103["stem_rec_ids"])
        y_sep = np.array([1 if recs_103[r]["context"] == "owl_mobbing" else 0 for r in rid_sep])
        g_sep = np.array([exp103_dev.group_key(recs_103[r]) for r in rid_sep])
        res_sep = exp103_dev.eval_caw_cv(X_sep, y_sep, rid_sep, g_sep, C=0.1, n_perm=400, seed=42)

        X_raw, rid_raw = extract_caws_from_windows(d103["raw_waves"], d103["win_rec_ids"])
        y_raw = np.array([1 if recs_103[r]["context"] == "owl_mobbing" else 0 for r in rid_raw])
        g_raw = np.array([exp103_dev.group_key(recs_103[r]) for r in rid_raw])
        res_raw = exp103_dev.eval_caw_cv(X_raw, y_raw, rid_raw, g_raw, C=0.1, n_perm=400, seed=43)

        primary_a = {
            "status": "binding_primary" if stage0["gate_passes_2db"] else "exploratory_post_failed_gate",
            "multi_crow_windows": int(len(d103["raw_waves"])),
            "kept_stems": int(len(d103["stem_waves"])),
            "separated_stems_caw_44d": res_sep,
            "unseparated_same_windows_caw_44d": res_raw,
            "delta_weighted_auc": round(
                float(res_sep["primary_weighted_per_caw_auc"] - res_raw["primary_weighted_per_caw_auc"]), 4
            ),
        }
        st.update(1, 1)

    # Primary B: 0104 video set — BirdNET stem embeddings
    with run.stage("primary_b_vid0104") as st:
        v104 = np.load(OUT_DIR / "vid0104_stems.npz")
        single_idx = json.loads((OUT_DIR / "vid0104_single_indices.json").read_text())
        stem_embs = embed_all_birdnet(v104["stem_waves"])
        stems_by_key = defaultdict(list)
        for k, emb in zip(v104["stem_keys"].tolist(), stem_embs):
            if np.any(emb != 0.0):
                stems_by_key[str(k)].append(emb)

        cs = exp104.ClipSet()
        demixed_vec = {}
        stems_only_vec = {}
        for c in cs.clips:
            vkey = f"v{c.key}"
            parts = []
            if sets.WindowTable.exists(vkey):
                wt = sets.WindowTable(vkey)
                for wi in single_idx.get(c.key, []):
                    parts.append(wt.embedding[wi])
            s_parts = stems_by_key.get(c.key, [])
            if s_parts:
                stems_only_vec[c.key] = np.mean(np.stack(s_parts), axis=0)
            all_parts = parts + s_parts
            if all_parts:
                demixed_vec[c.key] = np.mean(np.stack(all_parts), axis=0)
            else:
                demixed_vec[c.key] = cs.emb[c.row]

        gt = exp104.GroupedTest(C=0.05)
        owl_st = cs.cap_per_channel(cs.cell("owl", "perched", strict=True))
        hawk_st = cs.cap_per_channel(cs.cell("hawk", "perched", strict=True))
        hawk_p = cs.cap_per_channel(cs.cell("hawk", "perched", strict=False))
        hawk_f = cs.cap_per_channel(cs.cell("hawk", "flying", strict=False))

        def _score_cell(pos, neg, vec_map):
            p = [c for c in pos if c.key in vec_map]
            n = [c for c in neg if c.key in vec_map]
            X = np.stack([vec_map[c.key] for c in p + n])
            y = np.array([1] * len(p) + [0] * len(n))
            g = np.array([c.channel for c in p + n])
            return gt.run(X, y, g, permute=True)

        demix_perched = _score_cell(owl_st, hawk_st, demixed_vec)
        orig_perched = _score_cell(owl_st, hawk_st, {c.key: cs.emb[c.row] for c in cs.clips})
        demix_hawk_pf = _score_cell(hawk_p, hawk_f, demixed_vec)
        orig_hawk_pf = _score_cell(hawk_p, hawk_f, {c.key: cs.emb[c.row] for c in cs.clips})

        primary_b = {
            "status": "binding_primary" if stage0["gate_passes_2db"] else "exploratory_post_failed_gate",
            "perched_owl_vs_perched_hawk_strict": {
                "demixed": demix_perched,
                "unseparated_0104": orig_perched,
                "delta_auc": round(float(demix_perched["auc"] - orig_perched["auc"]), 4),
            },
            "within_hawk_perched_vs_flying_nonstrict": {
                "demixed": demix_hawk_pf,
                "unseparated_0104": orig_hawk_pf,
                "delta_auc": round(float(demix_hawk_pf["auc"] - orig_hawk_pf["auc"]), 4),
            },
        }
        st.update(1, 1)

    ha, hb = holm_pair(
        primary_a["separated_stems_caw_44d"].get("perm_p"),
        primary_b["perched_owl_vs_perched_hawk_strict"]["demixed"].get("perm_p"),
    )
    primary_a["holm_p"] = ha
    primary_b["perched_owl_vs_perched_hawk_strict"]["holm_p"] = hb

    report = {
        "Stage0_conspecific_2crow_gate": stage0,
        "Primary_A_0103_dev_caw_owl_vs_hawk": primary_a,
        "Primary_B_0104_video_stem_birdnet": primary_b,
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    run.note(
        f"Gate={stage0['gate_passes_2db']} (0dB best-stem={stage0['mix_0db_primary']['best_stem_sisdri_median_db']} dB, "
        f"part={stage0['mix_0db_primary']['partition_sisdri_median_db']} dB); "
        f"0103 caw AUC={primary_a['separated_stems_caw_44d']['primary_weighted_per_caw_auc']}; "
        f"0104 perched AUC={primary_b['perched_owl_vs_perched_hawk_strict']['demixed']['auc']}"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
