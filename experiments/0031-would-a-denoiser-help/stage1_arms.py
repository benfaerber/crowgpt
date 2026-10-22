"""Stage 1: build every arm as a 48 kHz WAV. Runs in this folder's CPU-only venv.

Split from stage 2 because the denoiser needs torch and the analyzer needs
birdnetlib, and those live in different environments. Every arm is written at
48 kHz so stage 2 hands the analyzer identical containers and the only
difference is what happened to the samples.

    nice -n 19 env CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=8 .venv/bin/python stage1_arms.py
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt, resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import audio_for  # noqa: E402

import denoise_lib  # noqa: E402

MOWER = [94, 95, 96, 97]
RATE = 48000
HIGHPASS_HZ = 300
TARGET_PEAK_DBFS = -3.0
OUT = Path(__file__).resolve().parent / "work" / "arms"


def load(capture_id):
    x, sr = sf.read(audio_for(capture_id), always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != RATE:
        x = resample_poly(x, RATE, sr)
    return x.astype(np.float64)


def highpass(sig, cutoff=HIGHPASS_HZ):
    b, a = butter(4, cutoff, btype="highpass", fs=RATE)
    return filtfilt(b, a, sig)


def band_limit(sig):
    """16 kHz round trip with no denoising — the control that separates the
    model from its own 8 kHz ceiling. Without this arm a confidence change
    cannot be attributed to denoising rather than to the lost bandwidth, which
    is the trap 0020 caught."""
    return resample_poly(resample_poly(sig, 16000, RATE), RATE, 16000)


def denoise(model, sig):
    """Gain-stage, denoise at 16 kHz, restore level and rate.

    The normalisation is not cosmetic: Demucs.forward divides by (floor + std)
    with floor=1e-3, and this corpus sits close enough to that floor to be
    under-driven by ~6 dB. The identical gain is undone afterwards so the arm
    is comparable to the others in absolute level.
    """
    peak = np.abs(sig).max()
    gain = (10 ** (TARGET_PEAK_DBFS / 20)) / peak if peak > 0 else 1.0
    at_16k = resample_poly(sig * gain, 16000, RATE)
    cleaned = denoise_lib.denoise(model, at_16k.astype(np.float32))
    return resample_poly(cleaned.astype(np.float64), RATE, 16000) / gain


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    model = denoise_lib.load_model()
    print(f"model: {denoise_lib.model_path().name} @ {model.sample_rate} Hz, "
          f"hash-verified\n")

    for cid in MOWER:
        raw = load(cid)
        hp = highpass(raw)
        arms = {
            "raw": raw,
            "hp300": hp,
            "band16": band_limit(raw),
            "denoise": denoise(model, raw),
            "hp300_denoise": denoise(model, hp),
        }
        for name, sig in arms.items():
            n = min(len(sig), len(raw))
            path = OUT / f"{cid}-{name}.wav"
            sf.write(path, np.clip(sig[:n], -1, 1).astype(np.float32), RATE)
        peaks = "  ".join(
            f"{k}={20 * np.log10(np.abs(v).max() + 1e-12):.1f}" for k, v in arms.items())
        print(f"capture {cid}: {len(raw) / RATE:5.1f}s   peak dBFS  {peaks}")

    print(f"\nwrote {len(MOWER) * 5} arm files to {OUT}")


if __name__ == "__main__":
    main()
