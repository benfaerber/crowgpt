"""Compare the per-source probe captures of the same looping chirp stimulus.

Usage: python3 compare_sources.py [dir-with-probe_*.wav]  (see mobile/README.md)

Locates the 300 ms chirp bursts by fitting the known 600 ms period to the energy
envelope, then reports per source:
  - burst level and gap (noise floor) level, in dBFS
  - burst-to-gap contrast: gating/NS shows up as an inflated contrast
  - drift of burst level across the capture: AGC shows up as a moving gain
  - band levels across the chirp sweep, normalised, i.e. frequency response shape
"""
import os
import sys
import wave

import numpy as np

SR = 48000
PERIOD = 0.6
CHIRP = 0.3
FRAME = 0.010

SOURCES = ["UNPROCESSED", "VOICE_RECOGNITION", "MIC", "CAMCORDER", "VOICE_COMMUNICATION"]
BASE = sys.argv[1] if len(sys.argv) > 1 else "."


def load(path):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def db(x):
    x = np.asarray(x, dtype=np.float64)
    return 20 * np.log10(np.maximum(x, 1e-12))


def frame_rms(x, hop):
    n = len(x) // hop
    return np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))


def align(x):
    """Find the phase offset of the chirp bursts within the period."""
    hop = int(SR * FRAME)
    env = frame_rms(x, hop)
    frames_period = int(PERIOD / FRAME)
    frames_chirp = int(CHIRP / FRAME)
    best, best_offset = -np.inf, 0
    for offset in range(frames_period):
        idx = np.arange(len(env))
        pos = (idx - offset) % frames_period
        burst = env[pos < frames_chirp]
        gap = env[pos >= frames_chirp]
        if len(burst) == 0 or len(gap) == 0:
            continue
        score = burst.mean() - gap.mean()
        if score > best:
            best, best_offset = score, offset
    return env, best_offset, frames_period, frames_chirp


def masks(x):
    env, offset, fp, fc = align(x)
    idx = np.arange(len(env))
    pos = (idx - offset) % fp
    # Trim a frame at each boundary so ramp edges don't leak between classes.
    burst = (pos >= 1) & (pos < fc - 1)
    gap = (pos >= fc + 1) & (pos < fp - 1)
    return env, burst, gap, offset, fp, fc


def band_levels(x, burst_frames, hop):
    """Mean spectrum over burst frames, in octave-ish bands."""
    edges = [200, 400, 800, 1600, 3200, 6400, 9600, 12000]
    windows = []
    for i in np.flatnonzero(burst_frames):
        seg = x[i * hop : (i + 1) * hop]
        if len(seg) == hop:
            windows.append(seg)
    if not windows:
        return {}
    seg = np.array(windows)
    spec = np.abs(np.fft.rfft(seg * np.hanning(hop), axis=1)) ** 2
    freqs = np.fft.rfftfreq(hop, 1 / SR)
    out = {}
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (freqs >= lo) & (freqs < hi)
        out[f"{lo}-{hi}"] = 10 * np.log10(max(spec[:, sel].mean(), 1e-20))
    return out


rows = []
bands_by_source = {}
for name in SOURCES:
    path = os.path.join(BASE, f"probe_{name}.wav")
    if not os.path.exists(path):
        continue
    x = load(path)
    hop = int(SR * FRAME)
    env, burst, gap, offset, fp, fc = masks(x)

    burst_db = db(env[burst])
    gap_db = db(env[gap])

    # Per-cycle burst level, to expose a moving gain.
    cycles = []
    idx = np.arange(len(env))
    pos = (idx - offset) % fp
    cycle_id = (idx - offset) // fp
    for c in np.unique(cycle_id[cycle_id >= 0]):
        sel = burst & (cycle_id == c)
        if sel.sum() > 5:
            cycles.append(db(env[sel]).mean())

    rows.append(
        dict(
            source=name,
            burst=burst_db.mean(),
            gap=gap_db.mean(),
            contrast=burst_db.mean() - gap_db.mean(),
            first=cycles[0] if cycles else float("nan"),
            last=cycles[-1] if cycles else float("nan"),
            drift=(cycles[-1] - cycles[0]) if len(cycles) > 1 else float("nan"),
            spread=(max(cycles) - min(cycles)) if len(cycles) > 1 else float("nan"),
            secs=len(x) / SR,
        )
    )
    bands_by_source[name] = band_levels(x, burst, hop)

print(f"{'source':<21} {'burst':>8} {'gap':>8} {'contrast':>9} {'drift':>7} {'spread':>7} {'len':>6}")
print("-" * 72)
for r in rows:
    print(
        f"{r['source']:<21} {r['burst']:8.1f} {r['gap']:8.1f} {r['contrast']:9.1f} "
        f"{r['drift']:7.2f} {r['spread']:7.2f} {r['secs']:6.1f}s"
    )

print("\nFrequency response during the chirp, each source normalised to its own 800-1600 Hz band (dB):")
bands = list(next(iter(bands_by_source.values())).keys())
print(f"{'source':<21}" + "".join(f"{b:>12}" for b in bands))
print("-" * (21 + 12 * len(bands)))
for name, vals in bands_by_source.items():
    ref = vals["800-1600"]
    print(f"{name:<21}" + "".join(f"{vals[b] - ref:12.1f}" for b in bands))

print("\nAbsolute band levels (dB, uncalibrated but comparable across sources):")
print(f"{'source':<21}" + "".join(f"{b:>12}" for b in bands))
print("-" * (21 + 12 * len(bands)))
for name, vals in bands_by_source.items():
    print(f"{name:<21}" + "".join(f"{vals[b]:12.1f}" for b in bands))
