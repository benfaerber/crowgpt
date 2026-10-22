"""Does BirdNET's confidence track how much background sits behind a call?

Method: take the call BirdNET was most certain about, mix in progressively more
of the *same recording's own* street noise, and re-score. Using the recording's
background rather than synthetic hiss matters — it has the spectrum a
directional microphone would actually be rejecting.

If confidence falls with added noise, then noise rejection buys detections and a
directional mic is worth money. If it holds, the quiet calls are missed for some
other reason and no microphone fixes it.
"""

import contextlib
import datetime
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import audio_for  # noqa: E402
from lib.snr import band_snr  # noqa: E402

from birdnetlib import Recording  # noqa: E402
from birdnetlib.analyzer import Analyzer  # noqa: E402

CAPTURE = 88
CONFIDENT_CALL = (3.0, 6.0)    # scored 0.976 as recorded
MISSED_CALL = (14.0, 17.0)     # the one the pipeline dropped
QUIET_STRETCH = (19.5, 21.5)   # street, no bird
LAT, LON = 40.77, -111.88  # site, ~1 km rounded on purpose
WHEN = datetime.datetime(2026, 7, 26)
GAINS = (0.0, 0.5, 1.0, 2.0, 3.5, 5.0, 8.0)


def main() -> None:
    rate, data = wavfile.read(audio_for(CAPTURE))
    x = data.astype(np.float64) / 32768.0
    cut = lambda a, b: x[int(a * rate):int(b * rate)]

    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        analyzer = Analyzer()

    out = Path(os.environ.get("TMPDIR", "/tmp")) / "snr-vs-confidence"
    out.mkdir(exist_ok=True)

    def score(sig, tag):
        path = out / f"{tag}.wav"
        wavfile.write(path, rate, (np.clip(sig, -1, 1) * 32767).astype(np.int16))
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            rec = Recording(analyzer, str(path), min_conf=0.01,
                            lat=LAT, lon=LON, date=WHEN)
            rec.analyze()
        crow = [d["confidence"] for d in rec.detections if "Crow" in d["common_name"]]
        return max(crow) if crow else 0.0

    call = cut(*CONFIDENT_CALL)
    quiet = cut(*QUIET_STRETCH)
    noise = np.tile(quiet, int(np.ceil(len(call) / len(quiet))))[:len(call)]

    print(f"capture {CAPTURE}, the confident call at "
          f"{CONFIDENT_CALL[0]:.0f}-{CONFIDENT_CALL[1]:.0f}s, buried in its own street\n")
    print(f"{'added street':>14}  {'band SNR':>9}  {'BirdNET':>8}")
    for gain in GAINS:
        mixed = call + noise * gain
        print(f"{gain:>13.1f}x  {band_snr(mixed, rate):>9.1f}  {score(mixed, f'g{gain:g}'):>8.3f}")

    missed = cut(*MISSED_CALL)
    print(f"\nthe missed call as recorded: SNR {band_snr(missed, rate):.1f} dB "
          f"-> {score(missed, 'missed'):.3f}")
    print("\nNote: the SNR column saturates once noise dominates — it is a "
          "percentile ratio, not a true SNR. The added-noise column is the axis.")


if __name__ == "__main__":
    main()
