"""0118 step 1 (GPU/TF): run Google Research BirdMixIT 4-source separation on:
  - Stage 0: 100 synthetic 0 dB + 50 synthetic +3 dB conspecific 2-crow mixtures (from 0109 crowCount==1)
  - Stage 1a: multi-crow pure windows of 0103 dev strict owl/hawk recordings
  - Stage 1b: multi-crow pure windows of 0104 eligible raptor-mobbing video clips

    pipelines/representation/perch/.venv/bin/python \
        experiments/0118-demixing-overlapping-mobs/separate.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from itertools import combinations, permutations
from pathlib import Path

os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import librosa  # noqa: E402
import numpy as np  # noqa: E402
from scipy.signal import butter, filtfilt  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
MODEL_DIR = DATA_DIR / "models" / "bird_mixit" / "output_sources4"
OUT_DIR = DATA_DIR / "experiments" / "0118-birdmixit"
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"

sys.path.insert(0, str(EXP112))
import sets  # noqa: E402

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402

SR = 22050
WIN_SAMPLES = int(3.0 * SR)
B_BAND, A_BAND = butter(4, [700.0 / (SR / 2), 4500.0 / (SR / 2)], btype="band")


def sisdr(ref: np.ndarray, est: np.ndarray, eps: float = 1e-8) -> float:
    r = ref.astype(np.float64) - np.mean(ref)
    e = est.astype(np.float64) - np.mean(est)
    r_energy = float(np.dot(r, r)) + eps
    alpha = float(np.dot(e, r)) / r_energy
    target = alpha * r
    noise = e - target
    return float(10.0 * np.log10((np.dot(target, target) + eps) / (np.dot(noise, noise) + eps)))


def crow_band_rms(wave: np.ndarray) -> float:
    yf = filtfilt(B_BAND, A_BAND, wave).astype(np.float32)
    return float(np.sqrt(np.mean(yf ** 2) + 1e-12))


def select_top_stems(stems_4: np.ndarray, min_rel_rms: float = 0.15, max_stems: int = 2) -> list[np.ndarray]:
    """Select up to top-2 stems by 700-4500 Hz RMS energy (>= 15% of loudest stem)."""
    energies = [crow_band_rms(stems_4[k]) for k in range(stems_4.shape[0])]
    best = max(energies)
    if best < 1e-6:
        return [stems_4[int(np.argmax(energies))]]
    ranked = sorted(range(len(energies)), key=lambda i: energies[i], reverse=True)
    kept = [stems_4[i] for i in ranked[:max_stems] if energies[i] >= min_rel_rms * best]
    return kept or [stems_4[ranked[0]]]


class BirdMixITSeparator:
    def __init__(self):
        import tensorflow.compat.v1 as tf1

        tf1.disable_v2_behavior()
        self.tf1 = tf1
        self.graph = tf1.Graph()
        with self.graph.as_default():
            saver = tf1.train.import_meta_graph(str(MODEL_DIR / "inference.meta"))
            self.in_t = self.graph.get_tensor_by_name("input_audio/receiver_audio:0")
            self.out_t = self.graph.get_tensor_by_name("denoised_waveforms:0")
            cfg = tf1.ConfigProto()
            cfg.gpu_options.allow_growth = True
            cfg.gpu_options.per_process_gpu_memory_fraction = 0.25
            self.sess = tf1.Session(graph=self.graph, config=cfg)
            saver.restore(self.sess, str(MODEL_DIR / "model.ckpt-3223090"))
            # Check batch support once
            test_b = np.zeros((2, 1, WIN_SAMPLES), dtype=np.float32)
            try:
                out_b = self.sess.run(self.out_t, feed_dict={self.in_t: test_b})
                self.batch_ok = out_b.shape == (2, 4, WIN_SAMPLES)
            except Exception:  # noqa: BLE001
                self.batch_ok = False

    def separate_batch(self, waves: np.ndarray, batch_size: int = 16) -> np.ndarray:
        """waves: (N, T) -> returns (N, 4, T)."""
        N, T = waves.shape
        out = np.zeros((N, 4, T), dtype=np.float32)
        if self.batch_ok:
            for i in range(0, N, batch_size):
                chunk = waves[i : i + batch_size, None, :]
                out[i : i + batch_size] = self.sess.run(self.out_t, feed_dict={self.in_t: chunk})
        else:
            for i in range(N):
                out[i] = self.sess.run(self.out_t, feed_dict={self.in_t: waves[i : i + 1, None, :]})[0]
        return out


def build_crowgpt_counter():
    """Reload 0115's threshold and fit the exact crowgpt_b4 count model on 0109/0112 segments."""
    from corpus import LabelCorpus

    cut_info = json.loads((DATA_DIR / "experiments" / "0115-bout-syntax" / "crowgpt_b4_cut.json").read_text())
    threshold = float(cut_info["threshold_p_several"])

    crowgpt = np.load(sets.CACHE / "crowgpt.npz")
    cg_map = dict(zip(crowgpt["ids"].tolist(), crowgpt["layers"]))
    saved = np.load(DATA_DIR / "experiments" / "0109-crow-count" / "segments.npz")
    present = saved["present"]
    cat = sets.SpanCatalogue()
    segments = [s for s in LabelCorpus().labeled_segments() if s.flags.get("crowCount") in (1, 2, 4)]
    X_rows, y_rows = [], []
    one_crow_windows = {}
    multi_in_window = set()
    for seg, span_id, p in zip(segments, cat.segment_span, present):
        if not p:
            continue
        if seg.flags["crowCount"] > 1:
            multi_in_window.add(span_id)
        elif span_id not in one_crow_windows:
            start = 3.0 * (int(seg.start) // 3)
            one_crow_windows[span_id] = (str(seg.file_id), str(seg.audio_path), float(start))
        row = cg_map.get(span_id)
        if row is not None:
            X_rows.append(row[3].astype(np.float32))
            y_rows.append(1 if seg.flags["crowCount"] > 1 else 0)
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000),
    ).fit(np.stack(X_rows), np.array(y_rows))
    clean_one_crow = [v for k, v in sorted(one_crow_windows.items()) if k not in multi_in_window]
    return clf, threshold, cg_map, clean_one_crow


def eval_synthetic_mixtures(sep: BirdMixITSeparator, pool_clips: list[tuple[str, np.ndarray]], n_mix: int, snr_db: float, seed: int):
    rng = np.random.default_rng(seed)
    pairs = []
    attempts = 0
    while len(pairs) < n_mix and attempts < n_mix * 50:
        attempts += 1
        i, j = int(rng.integers(0, len(pool_clips))), int(rng.integers(0, len(pool_clips)))
        if pool_clips[i][0] != pool_clips[j][0]:
            pairs.append((i, j))

    gain1 = float(10.0 ** (snr_db / 20.0))
    s1_list, s2_list, mix_list = [], [], []
    for i, j in pairs:
        w1, w2 = pool_clips[i][1], pool_clips[j][1]
        s1 = (w1 / max(float(np.sqrt(np.mean(w1 ** 2))), 1e-6)) * (0.04 * gain1)
        s2 = (w2 / max(float(np.sqrt(np.mean(w2 ** 2))), 1e-6)) * 0.04
        s1_list.append(s1.astype(np.float32))
        s2_list.append(s2.astype(np.float32))
        mix_list.append((s1 + s2).astype(np.float32))

    mixes = np.stack(mix_list)
    stems = sep.separate_batch(mixes)  # (N, 4, T)

    in_sisdr, best_sisdri, part_sisdri = [], [], []
    top2_stems = np.zeros((len(pairs), 2, WIN_SAMPLES), dtype=np.float32)

    all_idx = {0, 1, 2, 3}
    non_empty_subsets = [set(c) for r in (1, 2, 3) for c in combinations(range(4), r)]

    for k in range(len(pairs)):
        s1, s2, m, y = s1_list[k], s2_list[k], mixes[k], stems[k]
        base = 0.5 * (sisdr(s1, m) + sisdr(s2, m))
        in_sisdr.append(base)

        best_pair = max(0.5 * (sisdr(s1, y[a]) + sisdr(s2, y[b])) for a, b in permutations(range(4), 2))
        best_sisdri.append(best_pair - base)

        best_part = max(
            0.5 * (
                sisdr(s1, np.sum([y[a] for a in A], axis=0))
                + sisdr(s2, np.sum([y[b] for b in (all_idx - A)], axis=0))
            )
            for A in non_empty_subsets
        )
        part_sisdri.append(best_part - base)

        sel = select_top_stems(y, min_rel_rms=0.0, max_stems=2)
        top2_stems[k, 0] = sel[0]
        top2_stems[k, 1] = sel[1] if len(sel) > 1 else sel[0]

    summary = {
        "n_mixtures": len(pairs),
        "snr_db": snr_db,
        "input_sisdr_median_db": round(float(np.median(in_sisdr)), 3),
        "best_stem_sisdri_median_db": round(float(np.median(best_sisdri)), 3),
        "best_stem_sisdri_iqr_db": [round(float(np.percentile(best_sisdri, 25)), 3), round(float(np.percentile(best_sisdri, 75)), 3)],
        "best_stem_frac_positive": round(float(np.mean(np.array(best_sisdri) > 0.0)), 3),
        "partition_sisdri_median_db": round(float(np.median(part_sisdri)), 3),
        "partition_sisdri_iqr_db": [round(float(np.percentile(part_sisdri, 25)), 3), round(float(np.percentile(part_sisdri, 75)), 3)],
        "partition_frac_positive": round(float(np.mean(np.array(part_sisdri) > 0.0)), 3),
    }
    return summary, mixes, top2_stems


def load_window_22k(audio_cache: dict[str, np.ndarray], path: str, start_s: float) -> np.ndarray | None:
    if path not in audio_cache:
        try:
            y, _ = librosa.load(path, sr=SR, mono=True, duration=300.0)
            audio_cache[path] = y
        except Exception:  # noqa: BLE001
            audio_cache[path] = np.zeros(0, dtype=np.float32)
    y = audio_cache[path]
    i0 = int(round(start_s * SR))
    if i0 + WIN_SAMPLES > len(y):
        return None
    return y[i0 : i0 + WIN_SAMPLES].astype(np.float32)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run = Run("0118 BirdMixIT separation", ["stage0_gate", "stage1_dev0103", "stage1_vid0104"])

    sep = BirdMixITSeparator()
    count_clf, threshold, cg_map, one_crow_meta = build_crowgpt_counter()

    # Stage 0: synthetic 2-crow mixtures
    with run.stage("stage0_gate") as st:
        rng_pool = np.random.default_rng(100)
        candidates = [one_crow_meta[i] for i in rng_pool.permutation(len(one_crow_meta))[:320]]
        by_path = defaultdict(list)
        for fid, apath, start_s in candidates:
            by_path[(fid, apath)].append(start_s)
        pool_clips = []
        for (fid, apath), starts in by_path.items():
            if not Path(apath).exists():
                continue
            try:
                y, _ = librosa.load(apath, sr=SR, mono=True)
            except Exception:  # noqa: BLE001
                continue
            for s0 in starts[:2]:
                i0 = int(round(s0 * SR))
                if i0 + WIN_SAMPLES <= len(y):
                    seg = y[i0 : i0 + WIN_SAMPLES]
                    if crow_band_rms(seg) > 1e-3:
                        pool_clips.append((fid, seg.astype(np.float32)))
        st.update(1, 3, extra=f"{len(pool_clips)} clean 1-crow clips")
        sum_0db, mixes_0db, top2_0db = eval_synthetic_mixtures(sep, pool_clips, n_mix=100, snr_db=0.0, seed=0)
        st.update(2, 3, extra=f"0dB part SI-SDRi={sum_0db['partition_sisdri_median_db']} dB")
        sum_3db, _, _ = eval_synthetic_mixtures(sep, pool_clips, n_mix=50, snr_db=3.0, seed=1)
        gate_passes = bool(
            sum_0db["best_stem_sisdri_median_db"] >= 2.0 or sum_0db["partition_sisdri_median_db"] >= 2.0
        )
        stage0 = {
            "clean_one_crow_pool_clips": len(pool_clips),
            "batch_inference_supported": sep.batch_ok,
            "crowgpt_b4_threshold": threshold,
            "mix_0db_primary": sum_0db,
            "mix_3db_secondary": sum_3db,
            "gate_passes_2db": gate_passes,
        }
        (OUT_DIR / "stage0_metrics.json").write_text(json.dumps(stage0, indent=2))
        np.savez_compressed(OUT_DIR / "stage0_audio.npz", mixes_0db=mixes_0db, top2_0db=top2_0db)
        st.update(3, 3, extra=f"gate={'PASS' if gate_passes else 'FAIL'}")

    # Stage 1a: 0103 dev strict recordings — multi-crow pure windows
    with run.stage("stage1_dev0103") as st:
        ho = json.loads((sets.EXP103 / "holdout_2023.json").read_text())
        dev_ids = set(ho["dev_ids"])
        arc_by_id = {r.extra["id"]: r for r in sets.ArchiveSet().recordings}
        dev_windows = []
        audio_cache: dict[str, np.ndarray] = {}
        for rid in sorted(dev_ids):
            rec = arc_by_id.get(rid)
            if rec is None or not sets.WindowTable.exists(rec.key):
                continue
            wt = sets.WindowTable(rec.key)
            pure = wt.pure() & (wt.raptor < 0.05)
            if not pure.any():
                continue
            for s0 in wt.start[pure]:
                row = cg_map.get(f"{rec.key}@{float(s0):.2f}")
                if row is None:
                    continue
                p_sev = float(count_clf.predict_proba(row[3:4].astype(np.float32))[0, 1])
                if p_sev >= threshold:
                    w = load_window_22k(audio_cache, str(rec.path), float(s0))
                    if w is not None:
                        dev_windows.append((rid, float(s0), w))
        audio_cache.clear()

        st.update(1, 2, extra=f"{len(dev_windows)} multi-crow dev windows")
        raw_waves = np.stack([x[2] for x in dev_windows]) if dev_windows else np.zeros((0, WIN_SAMPLES), dtype=np.float32)
        sep_4 = sep.separate_batch(raw_waves) if len(raw_waves) else np.zeros((0, 4, WIN_SAMPLES), dtype=np.float32)

        stem_waves, stem_rec_ids, win_rec_ids = [], [], []
        for idx, (rid, s0, _) in enumerate(dev_windows):
            win_rec_ids.append(rid)
            for sw in select_top_stems(sep_4[idx], min_rel_rms=0.15, max_stems=2):
                stem_waves.append(sw)
                stem_rec_ids.append(rid)

        np.savez_compressed(
            OUT_DIR / "dev0103_stems.npz",
            raw_waves=raw_waves,
            win_rec_ids=np.array(win_rec_ids, dtype=np.int64),
            stem_waves=np.stack(stem_waves) if stem_waves else np.zeros((0, WIN_SAMPLES), dtype=np.float32),
            stem_rec_ids=np.array(stem_rec_ids, dtype=np.int64),
        )
        st.update(2, 2, extra=f"{len(stem_waves)} stems kept")

    # Stage 1b: 0104 video clips — multi-crow pure windows
    with run.stage("stage1_vid0104") as st:
        clip_map = {r.key: r for r in sets.ClipSet().recordings}
        labels_104 = json.loads((sets.EXP104 / "labels.json").read_text())
        vid_multi = []
        vid_single_keys = defaultdict(list)
        audio_cache = {}
        for lb in labels_104:
            if not lb.get("clean_wildlife") or not lb.get("north_america"):
                continue
            vkey = f"v{lb['key']}"
            rec = clip_map.get(vkey)
            if rec is None or not sets.WindowTable.exists(vkey):
                continue
            wt = sets.WindowTable(vkey)
            pure = wt.pure() & (wt.raptor < 0.05)
            if not pure.any():
                continue
            for idx_w, s0 in zip(np.flatnonzero(pure), wt.start[pure]):
                row = cg_map.get(f"{vkey}@{float(s0):.2f}")
                p_sev = float(count_clf.predict_proba(row[3:4].astype(np.float32))[0, 1]) if row is not None else 1.0
                if p_sev < threshold:
                    vid_single_keys[lb["key"]].append(int(idx_w))
                else:
                    w = load_window_22k(audio_cache, str(rec.path), float(s0))
                    if w is not None:
                        vid_multi.append((lb["key"], float(s0), w))
        audio_cache.clear()

        st.update(1, 2, extra=f"{len(vid_multi)} multi-crow 0104 windows")
        v_raw = np.stack([x[2] for x in vid_multi]) if vid_multi else np.zeros((0, WIN_SAMPLES), dtype=np.float32)
        v_sep4 = sep.separate_batch(v_raw) if len(v_raw) else np.zeros((0, 4, WIN_SAMPLES), dtype=np.float32)
        v_stems, v_keys = [], []
        for idx, (ckey, _, _) in enumerate(vid_multi):
            for sw in select_top_stems(v_sep4[idx], min_rel_rms=0.15, max_stems=2):
                v_stems.append(sw)
                v_keys.append(ckey)

        np.savez_compressed(
            OUT_DIR / "vid0104_stems.npz",
            stem_waves=np.stack(v_stems) if v_stems else np.zeros((0, WIN_SAMPLES), dtype=np.float32),
            stem_keys=np.array(v_keys),
        )
        (OUT_DIR / "vid0104_single_indices.json").write_text(json.dumps(vid_single_keys))
        st.update(2, 2, extra=f"{len(v_stems)} video stems kept")

    msg = (
        f"Stage0 0dB: best-stem SI-SDRi={sum_0db['best_stem_sisdri_median_db']} dB, "
        f"partition SI-SDRi={sum_0db['partition_sisdri_median_db']} dB (gate={gate_passes}); "
        f"dev0103 stems={len(stem_waves)}, vid0104 stems={len(v_stems)}"
    )
    run.note(msg)
    print(msg)


if __name__ == "__main__":
    main()
