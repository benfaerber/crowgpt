"""Does the new microphone buy anything the phone's own did not?

Ben bought a USB microphone and asked whether it was necessary. The corpus can
answer it better than a listening test can, because the two mics have now
recorded the same species at the same distance band from the same balcony.

The comparison, and why it is nearly fair:

    USB_HEADSET   103   20-50 m   The Poe Family on the apartment roofline
    BUILTIN_MIC   88    20-50 m   a crow on a tall building
    BUILTIN_MIC   87    20-50 m   Edgar on a ten-storey building

Same recordist, same neighbourhood, same distance band, same species, three
days apart. What is not controlled: the birds, the weather, and the background
— 87 has a vehicle wash through it, and 103 has whatever a Wednesday afternoon
had. Two recordings against two is not a study. It is enough to see a large
effect and not enough to see a small one, which is stated here rather than
discovered later.

Measured with 0004's band_snr unchanged, so these numbers sit on the same axis
as every earlier experiment — that one mapped band SNR to BirdNET confidence on
the built-in mic (~2.5 dB costs ~0.19), which is what makes a difference here
readable as detections rather than as decibels.

Run: pipelines/representation/.venv-birdnet/bin/python run.py
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import audio_for, field_db  # noqa: E402
from lib.snr import band_snr  # noqa: E402
from lib.snr import noise_floor_dbfs as floor_dbfs  # noqa: E402

DB = field_db()

NEW_MIC = [103]
OLD_MIC = [87, 88]
# 102 is the new mic too, but the bird was never seen and no distance recorded,
# so it cannot join a distance-matched comparison. Reported separately.
UNMATCHED = [102]


def measure(capture_id):
    x, sr = sf.read(audio_for(capture_id))
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x.astype(np.float64)
    return {
        "id": capture_id,
        "seconds": len(x) / sr,
        "peak": 20 * np.log10(np.abs(x).max() + 1e-12),
        "rms": 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12),
        "snr": band_snr(x, sr),
        "floor": floor_dbfs(x, sr, 800, 4000),
        "rumble": floor_dbfs(x, sr, 0, 300),
        "clipped": int((np.abs(x) >= 0.999).sum()),
    }


def detections(capture_id):
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT d.crow_conf FROM detected_calls d "
        "JOIN analysis_results ar ON ar.id = d.analysis_id "
        "WHERE ar.capture_id = ? AND d.crow_conf IS NOT NULL "
        "AND ar.id = (SELECT MAX(id) FROM analysis_results WHERE capture_id = ?)",
        (capture_id, capture_id)).fetchall()
    con.close()
    return [r[0] for r in rows]


def report(title, ids):
    print(f"\n{title}")
    print(f"  {'id':>4} {'sec':>6} {'peak':>7} {'RMS':>7} {'band SNR':>9} "
          f"{'floor 800-4k':>13} {'clip':>5}  BirdNET")
    out = []
    for cid in ids:
        m = measure(cid)
        out.append(m)
        conf = detections(cid)
        best = f"{max(conf):.3f} (n={len(conf)})" if conf else "none"
        print(f"  {m['id']:>4} {m['seconds']:>6.1f} {m['peak']:>7.1f} {m['rms']:>7.1f} "
              f"{m['snr']:>9.1f} {m['floor']:>13.1f} {m['clipped']:>5}  {best}")
    return out


def main():
    new = report("NEW MIC (USB_HEADSET), 20-50 m", NEW_MIC)
    old = report("BUILT-IN MIC, 20-50 m", OLD_MIC)
    report("NEW MIC, distance not recorded — not part of the comparison", UNMATCHED)

    def mean(rows, key):
        return sum(r[key] for r in rows) / len(rows)

    print("\nDIFFERENCE, new minus built-in (matched on distance band)")
    for key, label, unit in (("snr", "band SNR", "dB"),
                             ("floor", "noise floor 800-4k", "dB"),
                             ("peak", "peak level", "dB"),
                             ("rumble", "noise floor <300 Hz", "dB")):
        delta = mean(new, key) - mean(old, key)
        print(f"  {label:<22} {delta:+6.1f} {unit}")

    snr_delta = mean(new, "snr") - mean(old, "snr")
    # 0004's slope, measured on the built-in mic: ~2.5 dB of extra background
    # cost ~0.19 of BirdNET confidence around the range these recordings sit in.
    print(f"\n  At 0004's slope that is worth roughly "
          f"{abs(snr_delta) / 2.5 * 0.19:.2f} of BirdNET confidence, "
          f"{'for' if snr_delta > 0 else 'against'} the new mic.")
    print("\n  n=1 against n=2. Enough to see a large effect, not a small one.")


if __name__ == "__main__":
    main()
