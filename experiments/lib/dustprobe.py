"""The blowing-dust probe, extracted from 0069's run.py for reuse.

Per-burst acoustic features aggregated per clip; the load-bearing one is
pitch strength — 0069 measured dust-labelled clips at 0.388 against 0.508
for clean-labelled and 0.518 for real, AUC 0.699 (marginal: n = 30, and a
hair under the pre-registered 0.7 bar, so treat the score as an opinion
with error bars, not a verdict). Bursts come from the caller's Segmenter
so every experiment stays on 0024's segmentation.

Two caveats that bound what the score may be compared against, both
measured rather than suspected:

- **Never across decoder states.** 0070: the finetuned decoder shifts
  pitch strength −0.03 on everything, real round-trips included — decoder
  character, not audible dust (0063's ears preferred it on those very
  round-trips). Within one decoder the ordering stands.
- **Never as an absolute rate.** The Youden threshold flags a third of
  real round-tripped bouts as dusty (0070). Only relative orderings
  within one condition mean anything.
"""
import numpy as np

FEATURES = ("pitch_strength", "flatness", "centroid_hz", "attack_ms")
MIN_BURST_S = 0.05

#: 0069's Youden point on its labelled clips: pitch strength at or below
#: this reads as dusty. Carried here so later experiments count "dusty"
#: the same way; resharpen when a sitting grows the labelled set.
DUST_FEATURE = "pitch_strength"
DUST_THRESHOLD = 0.4105


def bursts_of(seg, audio, sample_rate):
    db, fps = seg.envelope(audio, sample_rate)
    floor = np.percentile(db, seg.floor_pctl)
    out = []
    for a, b in seg.bursts(db, fps, floor):
        lo, hi = int(a / fps * sample_rate), int(b / fps * sample_rate)
        if (hi - lo) / sample_rate >= MIN_BURST_S:
            out.append(audio[lo: hi])
    return out


def pitch_strength(burst, sample_rate):
    """Peak normalised autocorrelation in the 60-1200 Hz F0 lag range."""
    x = burst - burst.mean()
    if not x.any():
        return 0.0
    lags = np.arange(int(sample_rate / 1200), int(sample_rate / 60) + 1)
    n = len(x)
    spectrum = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(spectrum * np.conj(spectrum))[: n]
    ac /= ac[0] + 1e-12
    lags = lags[lags < n]
    return float(ac[lags].max()) if len(lags) else 0.0


def spectral(burst, sample_rate):
    window = np.hanning(len(burst))
    power = np.abs(np.fft.rfft(burst * window)) ** 2
    freqs = np.fft.rfftfreq(len(burst), 1 / sample_rate)
    band = (freqs >= 100) & (freqs <= 8000)
    p = power[band] + 1e-20
    flatness = float(np.exp(np.mean(np.log(p))) / p.mean())
    centroid = float((freqs[band] * p).sum() / p.sum())
    return flatness, centroid


def attack_ms(burst, sample_rate):
    envelope = np.abs(burst)
    kernel = max(1, int(0.005 * sample_rate))
    envelope = np.convolve(envelope, np.ones(kernel) / kernel, mode="same")
    peak_i = int(np.argmax(envelope))
    peak = envelope[peak_i]
    if peak <= 0:
        return 0.0
    before = envelope[: peak_i + 1]
    over10 = np.nonzero(before >= 0.1 * peak)[0]
    over90 = np.nonzero(before >= 0.9 * peak)[0]
    if not len(over10) or not len(over90):
        return 0.0
    return float((over90[0] - over10[0]) / sample_rate * 1000)


def clip_features(seg, audio, sample_rate):
    bursts = bursts_of(seg, audio, sample_rate)
    if not bursts:
        return None
    rows = []
    for burst in bursts:
        flatness, centroid = spectral(burst, sample_rate)
        rows.append((pitch_strength(burst, sample_rate), flatness, centroid,
                     attack_ms(burst, sample_rate)))
    return {name: float(np.mean([r[i] for r in rows]))
            for i, name in enumerate(FEATURES)} | {"n_bursts": len(bursts)}


def is_dusty(features):
    return features[DUST_FEATURE] <= DUST_THRESHOLD


def auc(pos, neg):
    """Rank AUC: P(random positive scores above random negative)."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return None
    wins = (pos[:, None] > neg[None, :]).sum() \
        + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(wins / (len(pos) * len(neg)))
