"""Is a lawn mower 30 ft away ruining these recordings?

Four captures made in front of the recordist's apartment with mowers running:
four crows on the ground, one on a wire. The pipeline called almost all of it
"alarm call", which the recordist doubted — birds foraging on the ground do not
usually stay put through their own alarm.

Three questions, because "is the noise a problem" is three different questions:

1. WHERE does the mower sit? Rumble under the crow band is ugly on a meter and
   harmless to a call; energy inside 800-4000 Hz masks. 0005 made exactly this
   mistake worth avoiding — a wash that "looked like wind" turned out to be
   piling into the crow band, which is why it mattered.

2. HOW BAD is the band SNR, on the scale 0004 already calibrated? That
   experiment mapped band SNR to BirdNET confidence on this very microphone, so
   these captures can be placed on a curve rather than guessed at.

3. Does the mower CHANGE THE VERDICT? High-pass at 300 Hz — well below a caw's
   ~1.6 kHz fundamental, so the call is untouched — and re-run the real
   analyzer. If the call types move, the rumble was driving the model. If they
   hold, the mower is not what makes these read as alarm.

Run: pipelines/representation/.venv-birdnet/bin/python run.py
"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.io import wavfile
from scipy.signal import butter, filtfilt, stft

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.media import audio_for, field_db  # noqa: E402
from lib.snr import band_snr, noise_floor_dbfs  # noqa: E402

MOWER = [94, 95, 96, 97]
REFERENCE = 88  # rooftop, no mower, 15-29 dB band SNR (experiment 0001)
LAT, LON = 40.77, -111.88  # site, ~1 km rounded on purpose
HIGHPASS_HZ = 300

# Bands chosen to separate the two mechanisms: a mower is a low-frequency
# machine, a caw lives at 1-4 kHz. 800-4000 is 0004's SNR band, kept identical
# so the numbers are comparable across experiments.
BANDS = {"<300": (0, 300), "300-800": (300, 800),
         "800-4k": (800, 4000), "4k-12k": (4000, 12000)}


def load(capture_id):
    x, sr = sf.read(audio_for(capture_id), always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x.astype(np.float64), sr


def band_fractions(sig, rate):
    f, _, Z = stft(sig, fs=rate, nperseg=2048, noverlap=1536)
    power = np.mean(np.abs(Z) ** 2, axis=1)
    total = power.sum()
    return {k: power[(f >= lo) & (f < hi)].sum() / total
            for k, (lo, hi) in BANDS.items()}


def highpass(sig, rate, cutoff=HIGHPASS_HZ):
    b, a = butter(4, cutoff, btype="highpass", fs=rate)
    return filtfilt(b, a, sig)


def analyze_signal(sig, rate, tmp, tag, analyze):
    path = tmp / f"{tag}.wav"
    wavfile.write(path, rate, (np.clip(sig, -1, 1) * 32767).astype(np.int16))
    return analyze(path, lat=LAT, lon=LON)


def main():
    import os
    import tempfile

    from analyzer import analyze

    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "mower"
    tmp.mkdir(parents=True, exist_ok=True)

    print("1. WHERE THE ENERGY IS  (fraction of total power per band)\n")
    print(f"{'capture':>9}  {'peak dBFS':>10}  " +
          "  ".join(f"{k:>8}" for k in BANDS))
    signals = {}
    for cid in MOWER + [REFERENCE]:
        x, sr = load(cid)
        signals[cid] = (x, sr)
        fr = band_fractions(x, sr)
        peak = 20 * np.log10(np.abs(x).max() + 1e-12)
        tag = f"{cid}" + (" ref" if cid == REFERENCE else "")
        print(f"{tag:>9}  {peak:>10.1f}  " +
              "  ".join(f"{fr[k] * 100:>7.1f}%" for k in BANDS))

    print("\n2. DOES IT REACH THE CROW BAND?  "
          "(quiet-percentile level, absolute)\n")
    print(f"{'capture':>9}  {'floor <300Hz':>13}  {'floor 800-4k':>13}  "
          f"{'band SNR':>9}")
    ref_floor = noise_floor_dbfs(*signals[REFERENCE], 800, 4000)
    for cid in MOWER + [REFERENCE]:
        x, sr = signals[cid]
        low = noise_floor_dbfs(x, sr, 0, 300)
        crow = noise_floor_dbfs(x, sr, 800, 4000)
        tag = f"{cid}" + (" ref" if cid == REFERENCE else "")
        print(f"{tag:>9}  {low:>12.1f}  {crow:>12.1f}  {band_snr(x, sr):>8.1f}")
    print(f"\n  reference crow-band floor: {ref_floor:.1f} dBFS — the column "
          f"above is what the mower adds to it")

    print(f"\n3. DOES REMOVING IT CHANGE THE VERDICT?  "
          f"(high-pass {HIGHPASS_HZ} Hz, below the ~1.6 kHz fundamental)\n")
    for cid in MOWER:
        x, sr = signals[cid]
        filtered = highpass(x, sr)
        print(f"  capture {cid}:  band SNR {band_snr(x, sr):.1f} -> "
              f"{band_snr(filtered, sr):.1f} dB after filtering")
        for label, sig in (("as recorded", x), ("high-passed", filtered)):
            regions = analyze_signal(sig, sr, tmp, f"{cid}-{label[:4]}", analyze)
            if not regions:
                print(f"    {label:>12}: no corvid regions")
                continue
            for r in regions:
                print(f"    {label:>12}: {r['start']:5.1f}-{r['end']:5.1f}s  "
                      f"{r['species']:<25} crow={r['crow_conf']:.3f}  "
                      f"{str(r['call_type']):<11} "
                      f"p={r['confidence'] if r['confidence'] is not None else 0:.3f}"
                      + ("  [candidate]" if r["candidate"] else ""))
        print()

    call_type_confidence_vs_species()


def call_type_confidence_vs_species():
    """Where is the head most certain, and does that track anything real?

    Noticed while reading section 3: every p=1.000 sits on a region BirdNET was
    least sure was a crow at all. If that holds across the corpus the head is
    not measuring confidence, it is saturating — a logistic regression on
    standardised embeddings will happily return 1.000 for input that falls
    outside everything it was trained on, and archive recordings are not what a
    phone in a street produces.
    """
    import sqlite3

    db = field_db()
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT confidence, crow_conf, call_type FROM detected_calls "
        "WHERE confidence IS NOT NULL AND crow_conf IS NOT NULL").fetchall()
    con.close()

    p = np.array([r[0] for r in rows])
    crow = np.array([r[1] for r in rows])
    print("4. IS THE CALL-TYPE CONFIDENCE MEASURING ANYTHING?  "
          f"(every detection on the server, n={len(rows)})\n")
    print(f"  call-type p vs species confidence: r = {np.corrcoef(p, crow)[0, 1]:+.3f}")
    print(f"  p == 1.000 exactly: {(p >= 0.9995).sum()} of {len(p)} "
          f"({(p >= 0.9995).mean() * 100:.0f}%)")

    saturated, rest = crow[p >= 0.9995], crow[p < 0.9995]
    if len(saturated) and len(rest):
        print(f"  mean species conf where p==1.000: {saturated.mean():.3f}")
        print(f"  mean species conf elsewhere:      {rest.mean():.3f}")
    print("\n  r near zero is the finding: call-type p carries no information "
          "about\n  whether the region is even a crow. The saturated third "
          "skews to *lower*\n  species confidence, which is the opposite of "
          "what a calibrated head does.")


if __name__ == "__main__":
    main()
