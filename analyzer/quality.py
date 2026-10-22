"""Measured audio quality — how hard a recording was to hear.

Numbers, not judgements, which is why this is not a label: everything in
`label_defs` is a claim about what a call *is* and trains something, while
"noisy" is a property of the recording. The worker writes these per capture;
the experiments quote the same functions so every number in the project sits
on one axis.

The two band measures moved here from experiments/lib/snr.py and must stay
byte-identical — 0004's confidence curve (~2.5 dB of band SNR costs ~0.19 of
BirdNET confidence) was drawn against `band_snr`, and it only keeps meaning
while there is one implementation to quote. lib/snr.py now re-exports these.

Pure DSP: numpy, scipy, soundfile. No BirdNET, no server, no database.
"""

import numpy as np
import soundfile as sf
from scipy.signal import stft

#: Full scale, near enough. Phones hand back int16 whose clipped peak can land
#: at 32767/32768 either side of 1.0 after conversion, so exact equality misses.
CLIP_LEVEL = 0.999

#: Two clipped samples closer than this are the same event — 0009's lesson,
#: kept in 0010: 195 clipped samples read as an overloaded microphone and
#: turned out to be two knocks.
CLIP_GAP_SEC = 0.05


def band_snr(sig, rate):
    """Loud percentile over quiet percentile in the crow band (800-4000 Hz).

    Not a true SNR — it saturates once noise dominates — but it is the axis
    0004's confidence curve was drawn against, so it has to stay identical.
    """
    f, _, Z = stft(sig, fs=rate, nperseg=2048, noverlap=1536)
    band = (f >= 800) & (f <= 4000)
    e = np.sqrt(np.mean(np.abs(Z[band]) ** 2, axis=0))
    return 20 * np.log10(np.percentile(e, 99) / np.percentile(e, 10))


def noise_floor_dbfs(sig, rate, lo, hi):
    """The quiet 10th percentile in a band, absolutely — what masks a call.

    Fractions of total energy cannot answer the masking question: a recording
    that is 89% rumble might have a perfectly clean crow band. This is the
    number that says whether the noise actually reaches up there.
    """
    f, _, Z = stft(sig, fs=rate, nperseg=2048, noverlap=1536)
    band = (f >= lo) & (f < hi)
    e = np.sqrt(np.mean(np.abs(Z[band]) ** 2, axis=0))
    return 20 * np.log10(np.percentile(e, 10) + 1e-12)


def clipping(sig, rate):
    """Clipping events and clipped samples, in that order.

    The event count is the one that means something; the raw sample count is
    kept because it is what says whether an event was a knock (a handful of
    samples) or sustained overload (thousands).
    """
    idx = np.flatnonzero(np.abs(sig) >= CLIP_LEVEL)
    if len(idx) == 0:
        return 0, 0
    events = 1 + int((np.diff(idx) > rate * CLIP_GAP_SEC).sum())
    return events, len(idx)


def _finite_or_none(value):
    """A merged capture holds digital zero in the gaps between its parts, so
    the quiet percentile the SNR divides by can be exactly 0 and the ratio
    infinite — not a number, and not JSON either. None says "no quiet signal
    to measure against"; the guard lives here so band_snr itself stays
    byte-identical to what 0004 calibrated.
    """
    value = float(value)
    return value if np.isfinite(value) else None


def measure(path):
    """Every quality number for one recording. A path in, a dict out.

    Keys match the `capture_quality` columns so the caller stores the dict as
    handed back. Multichannel is meaned down to mono, matching how every
    experiment has measured.
    """
    sig, rate = sf.read(path)
    if sig.ndim > 1:
        sig = sig.mean(axis=1)
    sig = sig.astype(np.float64)
    if len(sig) == 0:
        # A 44-byte WAV is a header and no recording. Refusing beats measuring
        # nothing and calling it quiet.
        raise ValueError("no audio samples to measure")
    events, samples = clipping(sig, rate)
    return {
        "band_snr_db": _finite_or_none(band_snr(sig, rate)),
        "noise_floor_low_dbfs": float(noise_floor_dbfs(sig, rate, 0, 300)),
        "noise_floor_band_dbfs": float(noise_floor_dbfs(sig, rate, 800, 4000)),
        "peak_dbfs": float(20 * np.log10(np.abs(sig).max() + 1e-12)),
        "rms_dbfs": float(20 * np.log10(np.sqrt(np.mean(sig ** 2)) + 1e-12)),
        "clipped_samples": samples,
        "clip_events": events,
    }
