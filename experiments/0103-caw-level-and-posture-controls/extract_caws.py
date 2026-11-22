"""Extract strictly all-non-crow-masked pure-crow windows and individual caw segments for Experiment 0103.

For every strict zero-raptor American Crow owl_mobbing / hawk_mobbing recording in
holdout_2023.json (dev + holdout; audio features extracted blindly without peeking at
holdout metrics):
  1. Run BirdNET (min_conf=0.05) per 3s window.
  2. Keep ONLY pure-crow windows where American Crow / Northwestern Crow >= 0.25 AND
     ZERO non-crow species are detected anywhere in that window at conf >= 0.05.
  3. Record which non-crow species were present (to measure bystander confounding directly).
  4. Segment individual crow caws inside pure-crow windows via crow-band (700-4500 Hz)
     RMS envelope peak detection (duration 80-700 ms, min spacing 180 ms, up to 30
     highest-SNR caws per recording).
  5. Compute pre-declared primary 44-d single-caw acoustic features (`caw_acoustic_44d`)
     strictly inside each caw's [onset, offset] on unit-RMS normalized 600-5000 Hz audio.
  6. Compute exploratory isolated-caw BirdNET embeddings (zero-padded to 3.0s with 10ms
     fades) and recording-level pure-crow BirdNET mean embedding (1024d).

Runs on CPU in the BirdNET venv:
  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0103-caw-level-and-posture-controls/extract_caws.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt, find_peaks

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
OUT_DIR = DATA_DIR / "experiments" / "0103-caw-level"
DB_PATH = DATA_DIR / "corvid.db"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "experiments" / "0102-archive-remarks-semantics"))
from crowgpt.progress import Run  # noqa: E402
import run as exp102  # noqa: E402

CAW_FEATURE_NAMES = (
    "caw_dur_s",
    "attack_frac",
    "peak_to_mean_rms",
    "f0_med_hz",
    "f0_iqr_hz",
    "f0_slope_hz_s",
    "f0_voiced_frac",
    "centroid_med_hz",
    "centroid_std_hz",
    "bandwidth_med_hz",
    "rolloff_med_hz",
    "flatness_med",
    "zcr_med",
    "harmonic_ratio",
    "low_mid_ratio",
    *(f"mfcc_mean_{i}" for i in range(13)),
    *(f"mfcc_std_{i}" for i in range(13)),
    "band_e_0.6_1.5",
    "band_e_1.5_2.8",
    "band_e_2.8_4.5",
)
assert len(CAW_FEATURE_NAMES) == 44

_ANALYZER = None
_DEVNULL = None


def _init_worker():
    global _ANALYZER, _DEVNULL
    _DEVNULL = open(os.devnull, "w")
    from birdnetlib.analyzer import Analyzer

    with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
        _ANALYZER = Analyzer()


def _is_american_crow(common_name: str, sci_name: str) -> bool:
    s = f"{common_name} {sci_name}".lower()
    return ("american crow" in s) or ("northwestern crow" in s) or ("corvus brachyrhynchos" in s)


def extract_caw_44d(caw_y: np.ndarray, sr: int) -> np.ndarray:
    """Compute pre-declared 44-d single-caw waveform features on unit-RMS 600-5000 Hz audio."""
    dur = len(caw_y) / sr
    if len(caw_y) < int(0.06 * sr):
        return np.zeros(44, dtype=np.float32)

    b, a = butter(4, [600.0 / (sr / 2), 5000.0 / (sr / 2)], btype="band")
    yf = filtfilt(b, a, caw_y).astype(np.float32)
    rms_all = float(np.sqrt(np.mean(yf ** 2) + 1e-12))
    yf = yf / max(rms_all, 1e-6)

    # Envelope shape (5 ms hop)
    hop_e = max(1, int(round(0.005 * sr)))
    env = librosa.feature.rms(y=yf, frame_length=hop_e * 2, hop_length=hop_e)[0]
    pk_idx = int(np.argmax(env))
    attack_frac = float(pk_idx / max(len(env) - 1, 1))
    peak_to_mean = float(np.max(env) / max(float(np.mean(env)), 1e-8))

    # F0 contour via YIN
    frame_len = min(1024, max(256, int(2 ** np.floor(np.log2(max(len(yf), 256))))))
    hop_f = 128
    try:
        f0 = librosa.yin(yf, fmin=250.0, fmax=1800.0, sr=sr, frame_length=frame_len, hop_length=hop_f)
        valid = np.isfinite(f0) & (f0 > 260.0) & (f0 < 1750.0)
        voiced_frac = float(np.mean(valid))
        if np.sum(valid) >= 3:
            fv = f0[valid]
            t_v = np.arange(len(f0), dtype=np.float64)[valid] * (hop_f / sr)
            f0_med = float(np.median(fv))
            f0_iqr = float(np.percentile(fv, 75) - np.percentile(fv, 25))
            slope = float(np.polyfit(t_v, fv, 1)[0]) if (t_v[-1] - t_v[0]) > 0.02 else 0.0
        elif np.sum(valid) >= 1:
            fv = f0[valid]
            f0_med, f0_iqr, slope = float(np.median(fv)), 0.0, 0.0
        else:
            f0_med, f0_iqr, slope = 0.0, 0.0, 0.0
    except Exception:
        f0_med, f0_iqr, slope, voiced_frac = 0.0, 0.0, 0.0, 0.0

    # Spectral & harmonic structure
    n_fft = min(512, max(256, frame_len))
    S = np.abs(librosa.stft(yf, n_fft=n_fft, hop_length=hop_f))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=S, sr=sr)[0]
    rolloff = librosa.feature.spectral_rolloff(S=S, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=S + 1e-10)[0]
    zcr = librosa.feature.zero_crossing_rate(yf, frame_length=n_fft, hop_length=hop_f)[0]

    try:
        y_harm, y_perc = librosa.effects.hpss(yf, margin=1.0)
        e_h = float(np.mean(y_harm ** 2))
        e_p = float(np.mean(y_perc ** 2))
        harm_ratio = float(e_h / max(e_h + e_p, 1e-10))
    except Exception:
        harm_ratio = 0.5

    b_lo = (freqs >= 600) & (freqs < 1500)
    b_mi = (freqs >= 1500) & (freqs < 2800)
    b_hi = (freqs >= 2800) & (freqs <= 4500)
    P = S ** 2
    e_lo = float(np.mean(P[b_lo, :])) if np.any(b_lo) else 0.0
    e_mi = float(np.mean(P[b_mi, :])) if np.any(b_mi) else 0.0
    e_hi = float(np.mean(P[b_hi, :])) if np.any(b_hi) else 0.0
    e_tot = max(e_lo + e_mi + e_hi, 1e-12)
    low_mid_ratio = float(np.log((e_lo + 1e-10) / (e_mi + e_hi + 1e-10)))

    mfccs = librosa.feature.mfcc(y=yf, sr=sr, n_mfcc=13, n_fft=n_fft, hop_length=hop_f, fmin=500, fmax=5500)
    vec = np.array([
        dur,
        attack_frac,
        peak_to_mean,
        f0_med,
        f0_iqr,
        slope,
        voiced_frac,
        float(np.median(centroid)),
        float(np.std(centroid)),
        float(np.median(bandwidth)),
        float(np.median(rolloff)),
        float(np.median(flatness)),
        float(np.median(zcr)),
        harm_ratio,
        low_mid_ratio,
        *np.mean(mfccs, axis=1).tolist(),
        *np.std(mfccs, axis=1).tolist(),
        e_lo / e_tot,
        e_mi / e_tot,
        e_hi / e_tot,
    ], dtype=np.float32)
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def segment_caws_in_windows(y: np.ndarray, sr: int, windows: list[tuple[float, float]], max_caws: int = 30) -> list[dict]:
    """Deterministic crow-band RMS peak + onset/offset segmentation strictly inside pure-crow windows."""
    if not windows or len(y) < int(0.5 * sr):
        return []
    b, a = butter(4, [700.0 / (sr / 2), 4500.0 / (sr / 2)], btype="band")
    yf = filtfilt(b, a, y).astype(np.float32)

    hop = max(1, int(round(0.010 * sr)))  # 10 ms
    env = librosa.feature.rms(y=yf, frame_length=hop * 2, hop_length=hop)[0]
    env_sr = sr / hop
    env_s = np.convolve(env, np.ones(3) / 3.0, mode="same")

    candidates = []
    for ws, we in windows:
        i0 = max(0, int(round((ws + 0.05) * env_sr)))
        i1 = min(len(env_s), int(round((we - 0.05) * env_sr)))
        if i1 - i0 < int(0.4 * env_sr):
            continue
        seg = env_s[i0:i1]
        p10, p25, p98 = np.percentile(seg, [10, 25, 98])
        dyn = float(p98 - p10)
        if dyn < 1e-5:
            continue
        height = max(p25 * 2.2, p10 + 0.20 * dyn)
        prom = 0.15 * dyn
        peaks, _ = find_peaks(seg, distance=max(1, int(round(0.18 * env_sr))), height=height, prominence=prom)
        for pk in peaks:
            pk_val = float(seg[pk])
            thr = p10 + 0.25 * (pk_val - p10)
            l_idx = pk
            while l_idx > 0 and seg[l_idx] > thr:
                l_idx -= 1
            r_idx = pk
            while r_idx < len(seg) - 1 and seg[r_idx] > thr:
                r_idx += 1
            t_on = (i0 + l_idx) / env_sr
            t_off = (i0 + r_idx) / env_sr
            dur = t_off - t_on
            if 0.08 <= dur <= 0.70:
                snr = float((pk_val - p10) / max(p25, 1e-6))
                candidates.append({"onset": round(t_on, 4), "offset": round(t_off, 4), "dur": round(dur, 4), "snr": snr})

    # Deduplicate overlapping segments and keep up to max_caws highest-SNR caws
    candidates.sort(key=lambda c: c["snr"], reverse=True)
    kept = []
    for cand in candidates:
        if any(not (cand["offset"] <= k["onset"] or cand["onset"] >= k["offset"]) for k in kept):
            continue
        kept.append(cand)
        if len(kept) >= max_caws:
            break
    kept.sort(key=lambda c: c["onset"])
    return kept


def process_one(task: tuple[int, str]) -> dict:
    rid, audio_path = task
    from birdnetlib import Recording

    try:
        with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
            rec = Recording(_ANALYZER, audio_path, min_conf=0.05)
            rec.analyze()
            rec.extract_embeddings()
    except Exception as ex:
        return {"id": rid, "ok": False, "error": str(ex)}

    segs = rec.embeddings or []
    if not segs:
        return {"id": rid, "ok": False, "error": "no embeddings"}

    win_crow = defaultdict(float)
    win_noncrow = defaultdict(list)
    bystander_species = Counter()
    for det in rec.detections or []:
        key = (round(float(det["start_time"]), 2), round(float(det["end_time"]), 2))
        cn, sn = det.get("common_name", ""), det.get("scientific_name", "")
        c = float(det["confidence"])
        if _is_american_crow(cn, sn):
            win_crow[key] = max(win_crow[key], c)
        else:
            win_noncrow[key].append((cn, c))
            bystander_species[cn] += 1

    all_crow_w, pure_crow_w = [], []
    all_crow_e, pure_crow_e = [], []
    for s in segs:
        emb = np.asarray(s["embeddings"], dtype=np.float32)
        if not np.isfinite(emb).all():
            continue
        key = (round(float(s["start_time"]), 2), round(float(s["end_time"]), 2))
        if win_crow.get(key, 0.0) >= 0.25:
            all_crow_w.append(key)
            all_crow_e.append(emb)
            if not win_noncrow.get(key):
                pure_crow_w.append(key)
                pure_crow_e.append(emb)

    # Load audio (full recording up to 300s so late pure-crow windows are never dropped!)
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=300.0)
        dur_s = float(librosa.get_duration(path=audio_path))
    except Exception as ex:
        return {"id": rid, "ok": False, "error": f"load failed: {ex}"}

    # Recording-level density covariates (computed strictly on pure-crow windows for density matching)
    pure_frac = float(len(pure_crow_w) / max(len(segs), 1))
    pros_pure = exp102.extract_prosody(y, sr, pure_crow_w) if pure_crow_w else np.zeros(len(exp102.PROSODY_NAMES), dtype=np.float32)
    duty_cycle = float(pros_pure[5])

    # Segment individual caws strictly inside pure-crow windows
    caws = segment_caws_in_windows(y, sr, pure_crow_w, max_caws=30)
    caw_feats = []
    caw_bn_embs = []
    # Exploratory: isolated single-caw BirdNET embeddings (concatenated into 3.0s slots in one temp wav!)
    if caws:
        sr_bn = 48000
        slot_len = 3 * sr_bn
        slots = []
        for c in caws:
            i0 = max(0, int(round(c["onset"] * sr)))
            i1 = min(len(y), int(round(c["offset"] * sr)))
            seg_y = y[i0:i1]
            caw_feats.append(extract_caw_44d(seg_y, sr))

            # Build isolated 3.0s zero-padded slot with 10ms fade-in/out for BirdNET
            p0 = max(0, int(round((c["onset"] - 0.02) * sr)))
            p1 = min(len(y), int(round((c["offset"] + 0.02) * sr)))
            iso = librosa.resample(y[p0:p1], orig_sr=sr, target_sr=sr_bn).astype(np.float32)
            iso_rms = float(np.sqrt(np.mean(iso ** 2) + 1e-12))
            iso = np.clip(iso / max(iso_rms, 1e-6) * 0.12, -0.95, 0.95)
            fade = min(int(0.010 * sr_bn), len(iso) // 4)
            if fade > 1:
                iso[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
                iso[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
            buf = np.zeros(slot_len, dtype=np.float32)
            st_i = max(0, (slot_len - len(iso)) // 2)
            take = min(len(iso), slot_len)
            buf[st_i : st_i + take] = iso[:take]
            slots.append(buf)

        # One BirdNET pass on the concatenated isolated-caw slots
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tf:
                sf.write(tf.name, np.concatenate(slots), sr_bn)
                with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
                    iso_rec = Recording(_ANALYZER, tf.name, min_conf=0.05)
                    iso_rec.extract_embeddings()
                iso_segs = iso_rec.embeddings or []
                for idx_c in range(len(caws)):
                    if idx_c < len(iso_segs):
                        e = np.asarray(iso_segs[idx_c]["embeddings"], dtype=np.float32)
                        caw_bn_embs.append(e if np.isfinite(e).all() else np.zeros(1024, dtype=np.float32))
                    else:
                        caw_bn_embs.append(np.zeros(1024, dtype=np.float32))
        except Exception:
            caw_bn_embs = [np.zeros(1024, dtype=np.float32) for _ in caws]

    return {
        "id": rid,
        "ok": True,
        "duration_s": round(dur_s, 2),
        "n_segs": len(segs),
        "n_all_crow_w": len(all_crow_w),
        "n_pure_crow_w": len(pure_crow_w),
        "pure_crow_frac": round(pure_frac, 4),
        "duty_cycle": round(duty_cycle, 4),
        "n_caws": len(caws),
        "bystander_species": dict(bystander_species.most_common(12)),
        "emb_pure_mean": np.mean(np.stack(pure_crow_e), axis=0).astype(np.float32) if pure_crow_e else None,
        "emb_allcrow_mean": np.mean(np.stack(all_crow_e), axis=0).astype(np.float32) if all_crow_e else None,
        "caws": caws,
        "caw_feats": np.stack(caw_feats).astype(np.float32) if caw_feats else np.zeros((0, 44), dtype=np.float32),
        "caw_bn_embs": np.stack(caw_bn_embs).astype(np.float32) if caw_bn_embs else np.zeros((0, 1024), dtype=np.float32),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ho = json.loads((HERE / "holdout_2023.json").read_text())
    all_ids = sorted(set(ho["dev_ids"] + ho["holdout_ids"]))

    con = sqlite3.connect(str(DB_PATH))
    id_to_info = {}
    for rid, fp, date, lat, lng, src, rec, raw in con.execute(
        "SELECT id, file_path, date, lat, lng, source, recordist, raw "
        "FROM recordings WHERE source IN ('xeno_canto', 'macaulay') AND downloaded = 1"
    ).fetchall():
        d_raw = json.loads(raw or "{}")
        tm = d_raw.get("time") or d_raw.get("obsTime") or ""
        id_to_info[rid] = {
            "file_path": str(exp102.resolve_audio_path(fp)),
            "date": (date or "")[:10],
            "time": str(tm),
            "lat": lat,
            "lng": lng,
            "source": src or "",
            "recordist": rec or "",
        }
    con.close()

    lbls = {r["id"]: r for r in json.loads((REPO / "experiments/0102-archive-remarks-semantics/labels.json").read_text())}
    tasks = [(rid, id_to_info[rid]["file_path"]) for rid in all_ids if rid in id_to_info and Path(id_to_info[rid]["file_path"]).exists()]

    run = Run("0103 pure-crow masking + caw segmentation", ["extract"])
    results = []
    with run.stage("extract") as st, ProcessPoolExecutor(max_workers=8, initializer=_init_worker) as ex:
        futs = [ex.submit(process_one, t) for t in tasks]
        for k, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if k % 10 == 0 or k == len(tasks):
                st.update(k, len(tasks))

    results.sort(key=lambda r: r["id"])
    rec_rows = []
    emb_pure, emb_all, has_pure = [], [], []
    caw_rows, caw_X, caw_bn = [], [], []
    z1024 = np.zeros(1024, dtype=np.float32)

    ho_set = set(ho["holdout_ids"])
    for r in results:
        if not r.get("ok"):
            continue
        rid = r["id"]
        info = id_to_info[rid]
        split = "holdout" if rid in ho_set else "dev"
        rec_rows.append({
            "id": rid,
            "split": split,
            "context": lbls[rid]["context"],
            "date": info["date"],
            "time": info["time"],
            "lat": info["lat"],
            "lng": info["lng"],
            "source": info["source"],
            "recordist": info["recordist"],
            "duration_s": r["duration_s"],
            "n_segs": r["n_segs"],
            "n_all_crow_w": r["n_all_crow_w"],
            "n_pure_crow_w": r["n_pure_crow_w"],
            "pure_crow_frac": r["pure_crow_frac"],
            "duty_cycle": r["duty_cycle"],
            "n_caws": r["n_caws"],
            "bystander_species": r["bystander_species"],
        })
        has_pure.append(r["emb_pure_mean"] is not None)
        emb_pure.append(r["emb_pure_mean"] if r["emb_pure_mean"] is not None else z1024)
        emb_all.append(r["emb_allcrow_mean"] if r["emb_allcrow_mean"] is not None else z1024)

        for idx_c, c in enumerate(r["caws"]):
            caw_rows.append({
                "rec_id": rid,
                "split": split,
                "context": lbls[rid]["context"],
                "recordist": info["recordist"],
                "onset": c["onset"],
                "offset": c["offset"],
                "dur": c["dur"],
                "snr": round(c["snr"], 3),
            })
        if len(r["caw_feats"]) > 0:
            caw_X.append(r["caw_feats"])
            caw_bn.append(r["caw_bn_embs"])

    (OUT_DIR / "recordings.json").write_text(json.dumps(rec_rows, indent=2, ensure_ascii=False))
    (OUT_DIR / "caws.json").write_text(json.dumps(caw_rows, indent=2, ensure_ascii=False))
    np.savez_compressed(
        OUT_DIR / "features.npz",
        emb_pure_mean=np.stack(emb_pure),
        emb_allcrow_mean=np.stack(emb_all),
        has_pure=np.array(has_pure, dtype=bool),
        caw_acoustic_44d=np.vstack(caw_X) if caw_X else np.zeros((0, 44), dtype=np.float32),
        caw_birdnet_1024d=np.vstack(caw_bn) if caw_bn else np.zeros((0, 1024), dtype=np.float32),
    )

    dev_pure = [r for r in rec_rows if r["split"] == "dev" and r["n_pure_crow_w"] > 0]
    dev_caws = [c for c in caw_rows if c["split"] == "dev"]
    ho_pure = [r for r in rec_rows if r["split"] == "holdout" and r["n_pure_crow_w"] > 0]
    ho_caws = [c for c in caw_rows if c["split"] == "holdout"]
    msg = (
        f"extracted {len(rec_rows)} recs: dev pure={len(dev_pure)} ({dict(Counter(r['context'] for r in dev_pure))}, caws={len(dev_caws)}) | "
        f"holdout pure={len(ho_pure)} ({dict(Counter(r['context'] for r in ho_pure))}, caws={len(ho_caws)})"
    )
    run.note(msg)
    print(msg)


if __name__ == "__main__":
    main()
