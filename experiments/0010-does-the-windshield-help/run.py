"""Does the furry windshield on the VideoMic Me-C earn its place?

Better controlled than 0009, which compared two microphones across three days.
Here the microphone is identical — `USB_HEADSET`, honoured, 48 kHz on all four
captures — and the only deliberate change is the deadcat:

    without   102, 103   2026-07-29 afternoon
    with      104, 105   2026-07-29 later

Foam does three separable things, and lumping them together is how a windshield
gets credited for something it did not do (0005 dropped one from the shopping
list for exactly that reason — the noise "obviously" wind turned out to be
traffic in the crow band):

  1. WIND on the capsule — overwhelmingly sub-200 Hz, gusty over seconds.
  2. HANDLING — a hand or cable knock, which arrives as a transient. 0009 found
     two per recording in 102 and 103, each 1-21 ms and touching full scale.
     If the deadcat damps mechanical shock, that count should fall.
  3. HIGH FREQUENCY — foam absorbs treble. This is the *cost*, and it lands
     above the caw band, so it should be visible above 8 kHz and absent at
     1-4 kHz. If the crow band moves, something other than the windshield did
     it.

Prediction stated before measuring: fewer transients, lower rumble, a small
high-frequency loss, and the 800-4000 Hz band roughly unchanged.

Run: pipelines/representation/.venv-birdnet/bin/python run.py
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import stft

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import audio_for, field_db  # noqa: E402
from lib.snr import band_snr  # noqa: E402
from lib.snr import noise_floor_dbfs as floor_dbfs  # noqa: E402

DB = field_db()

WITHOUT = [102, 103]
WITH = [104, 105]

BANDS = {"<200": (0, 200), "200-800": (200, 800),
         "800-4k": (800, 4000), "4k-8k": (4000, 8000), "8k+": (8000, 20000)}


def spectrum(sig, rate):
    f, _, Z = stft(sig, fs=rate, nperseg=2048, noverlap=1536)
    return f, np.abs(Z)


def transients(sig, rate):
    """Clipping events, not clipped samples — 0009's lesson.

    195 samples reads as an overloaded microphone and turns out to be two
    knocks. Grouping by a 50 ms gap is what makes the count mean something.
    """
    idx = np.flatnonzero(np.abs(sig) >= 0.999)
    if len(idx) == 0:
        return 0, 0
    events = 1 + int((np.diff(idx) > rate * 0.05).sum())
    return events, len(idx)


def gustiness(sig, rate):
    """Wind is gusty; an engine is steady. 0005's discriminator.

    Standard deviation over mean of sub-200 Hz energy, second by second. A
    windshield should flatten this if wind was ever the problem.
    """
    f, mag = spectrum(sig, rate)
    low = (f >= 0) & (f < 200)
    e = np.sqrt(np.mean(mag[low] ** 2, axis=0))
    per_sec = [e[i:i + 30].mean() for i in range(0, len(e) - 30, 30)]
    return float(np.std(per_sec) / (np.mean(per_sec) + 1e-12))


def crow_conf(capture_id):
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT MAX(d.crow_conf) FROM detected_calls d "
        "JOIN analysis_results ar ON ar.id = d.analysis_id "
        "WHERE ar.capture_id = ? AND ar.id = "
        "(SELECT MAX(id) FROM analysis_results WHERE capture_id = ?)",
        (capture_id, capture_id)).fetchone()
    con.close()
    return rows[0] if rows and rows[0] is not None else 0.0


def measure(capture_id):
    x, rate = sf.read(audio_for(capture_id))
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x.astype(np.float64)
    f, mag = spectrum(x, rate)
    power = np.mean(mag ** 2, axis=1)
    total = power.sum()
    events, samples = transients(x, rate)
    return {
        "id": capture_id,
        "seconds": len(x) / rate,
        "p99": 20 * np.log10(np.percentile(np.abs(x), 99) + 1e-12),
        "events": events, "clipped": samples,
        "snr": band_snr(x, rate),
        "rumble": floor_dbfs(x, rate, 0, 200),
        "gust": gustiness(x, rate),
        "bands": {k: 10 * np.log10(power[(f >= lo) & (f < hi)].sum() / total + 1e-20)
                  for k, (lo, hi) in BANDS.items()},
        "crow": crow_conf(capture_id),
    }


def show(title, ids):
    print(f"\n{title}")
    print(f"  {'id':>4} {'sec':>6} {'99th':>7} {'events':>7} {'clip':>5} "
          f"{'band SNR':>9} {'rumble':>8} {'gust':>6} {'BirdNET':>8}")
    rows = [measure(c) for c in ids]
    for m in rows:
        print(f"  {m['id']:>4} {m['seconds']:>6.1f} {m['p99']:>7.1f} "
              f"{m['events']:>7} {m['clipped']:>5} {m['snr']:>9.1f} "
              f"{m['rumble']:>8.1f} {m['gust']:>6.2f} {m['crow']:>8.3f}")
    return rows


def main():
    off = show("WITHOUT the windshield (102, 103)", WITHOUT)
    on = show("WITH the windshield (104, 105)", WITH)

    def mean(rows, key):
        return sum(r[key] for r in rows) / len(rows)

    print("\nWITH minus WITHOUT")
    for key, label, unit in (("events", "clipping events", ""),
                             ("snr", "band SNR", "dB"),
                             ("rumble", "sub-200 Hz floor", "dB"),
                             ("gust", "gustiness", ""),
                             ("p99", "99th pct level", "dB")):
        print(f"  {label:<20} {mean(on, key) - mean(off, key):+7.2f} {unit}")

    print("\nSpectral balance, share of total power in dB (with minus without)")
    for band in BANDS:
        delta = mean(on, "bands")[band] - mean(off, "bands")[band] \
            if False else (sum(r["bands"][band] for r in on) / len(on)
                           - sum(r["bands"][band] for r in off) / len(off))
        print(f"  {band:>8}  {delta:+6.2f} dB")

    print("\n  n=2 against n=2, one afternoon. The transient count is the only"
          "\n  measure here robust to that — the rest can move for any reason.")


if __name__ == "__main__":
    main()
