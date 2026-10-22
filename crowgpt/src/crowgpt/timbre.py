"""Measures for the thing BirdNET cannot hear: whether it sounds like a machine.

BirdNET is not merely saturated here, it is disqualified. 0014 put a 2 kHz
lowpass — audibly wrecked — against a 3 kbps codec round-trip and the lowpass
RETAINED MORE DETECTIONS (0.733 against 0.690) while sitting 3.2x further away
spectrally. A detector trained to answer "is there a crow in this" has no
opinion about whether the crow sounds real, and asking it for one has already
misled this project once.

So these are hand-built and interpretable, and every one of them is a guess
until it earns its place. The acceptance test is written down before the
numbers: a measure is only useful if REAL and CODEC agree while GENERATED
differs from both. A measure that separates real from codec is describing the
tokenizer, and 0014 and 0017 between them already established the tokenizer is
not the problem. A measure that separates nothing gets deleted rather than
reported.

The second test is harder and better: once a listening session is recorded, each
clip has a human answer attached. A measure that cannot predict which clips gave
themselves away is not measuring what Ben is hearing, whatever it correlates
with otherwise.

WHY THE FRAME-STITCH MEASURE COMES FIRST. It is the only one here whose null is
known exactly rather than estimated. EnCodec emits one frame per 320 samples, so
at 24 kHz its grid sits at exactly 75 Hz. Tokens that do not belong next to each
other produce a decoder discontinuity locked to that grid, and real audio has no
reason to prefer any particular frame phase — so a real recording scores zero by
construction, not by measurement. Everything else here has to borrow its null
from the codec arm.

The flux hop is 80 samples, not the obvious 160. At hop 160 the flux series is
sampled at 150 Hz and the 75 Hz target lands exactly on Nyquist, which is the
one frequency a DFT cannot report honestly. 80 puts it at half Nyquist.
"""

import numpy as np
from scipy.signal import stft

CODEC_HOP = 320
FLUX_HOP = 80
FLUX_WINDOW = 256
STITCH_BAND = (40.0, 110.0)
STITCH_GUARD = 3.0


class FrameStitch:
    """Periodicity in the spectral flux at the codec's own frame rate.

    Phase-blind on purpose: it reads the magnitude of the flux spectrum at 75 Hz
    rather than comparing frames either side of a boundary. Boundary-aligned
    comparison needs sample-exact knowledge of where the grid starts, which any
    later placement into ambience destroys.
    """

    name = "stitch_db"

    def measure(self, samples, sr):
        grid_hz = sr / CODEC_HOP
        flux = self._flux(samples, sr)
        if flux.size < 32:
            return {self.name: float("nan")}

        rate = sr / FLUX_HOP
        windowed = (flux - flux.mean()) * np.hanning(flux.size)
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(flux.size, 1.0 / rate)

        target = int(np.argmin(np.abs(freqs - grid_hz)))
        band = (freqs >= STITCH_BAND[0]) & (freqs <= STITCH_BAND[1])
        band &= np.abs(freqs - grid_hz) > STITCH_GUARD
        if not band.any() or spectrum[target] <= 0:
            return {self.name: float("nan")}

        floor = float(np.median(spectrum[band])) or 1e-12
        return {self.name: float(20 * np.log10(spectrum[target] / floor))}

    def _flux(self, samples, sr):
        samples = np.asarray(samples, dtype=np.float64)
        if samples.size < FLUX_WINDOW * 2:
            return np.zeros(0)
        _, _, spectrum = stft(
            samples,
            nperseg=FLUX_WINDOW,
            noverlap=FLUX_WINDOW - FLUX_HOP,
            padded=True,
            boundary="zeros",
        )
        magnitude = np.log(np.abs(spectrum) + 1e-7)
        return np.abs(np.diff(magnitude, axis=1)).mean(axis=0)


class OnsetSharpness:
    """How fast the attack rises, which is most of what makes a caw a caw.

    `metrics.py` keeps a 5.3 ms analysis scale specifically because onset
    smearing is the first thing a codec loses. A model that hedges its opening
    tokens produces a mushy attack, and a mushy attack does not read as a bird.
    """

    name = "rise_ms"

    def __init__(self, hop_ms=2.0, floor_db=12.0):
        self.hop_ms = hop_ms
        self.floor_db = floor_db

    def measure(self, samples, sr):
        envelope, rate = self._envelope(samples, sr)
        if envelope.size < 8:
            return {self.name: float("nan"), "crest": float("nan")}

        peak = envelope.max()
        if peak <= 0:
            return {self.name: float("nan"), "crest": float("nan")}
        loud = envelope >= peak * 10 ** (-self.floor_db / 20)

        rises = [r for r in (self._rise(envelope, rate, start, end)
                             for start, end in self._runs(loud)) if r is not None]
        rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=np.float64) ** 2)))
        crest = float(peak / rms) if rms > 0 else float("nan")
        return {
            self.name: float(np.median(rises)) if rises else float("nan"),
            "crest": crest,
        }

    def _envelope(self, samples, sr):
        hop = max(1, int(sr * self.hop_ms / 1000))
        samples = np.asarray(samples, dtype=np.float64)
        usable = (samples.size // hop) * hop
        if usable < hop * 8:
            return np.zeros(0), sr / hop
        frames = samples[:usable].reshape(-1, hop)
        return np.sqrt((frames ** 2).mean(axis=1)), sr / hop

    def _runs(self, mask):
        edges = np.diff(mask.astype(np.int8))
        starts = list(np.flatnonzero(edges == 1) + 1)
        ends = list(np.flatnonzero(edges == -1) + 1)
        if mask[0]:
            starts.insert(0, 0)
        if mask[-1]:
            ends.append(mask.size)
        return [(s, e) for s, e in zip(starts, ends) if e - s >= 3]

    def _rise(self, envelope, rate, start, end):
        segment = envelope[start:end]
        top = segment.max()
        if top <= 0:
            return None
        crossed_low = np.flatnonzero(segment >= 0.1 * top)
        crossed_high = np.flatnonzero(segment >= 0.9 * top)
        if not crossed_low.size or not crossed_high.size:
            return None
        span = crossed_high[0] - crossed_low[0]
        return max(0.0, float(span) / rate * 1000)


class HarmonicNoise:
    """Voicing, harmonic-to-noise ratio and pitch jitter.

    A caw is a harmonic burst with structured noise on top. "Robotic" usually
    means either broadband hash between the harmonics or a pitch track that
    steps rather than glides, and jitter is the sub-measure most likely to catch
    the second. HNR may well be swamped by how genuinely noisy corvid calls
    are — if real and generated land on top of each other it should be dropped
    rather than reported.
    """

    name = "jitter"

    def __init__(self, frame_ms=20.0, hop_ms=10.0, floor_db=25.0,
                 f0_range=(200.0, 1500.0), voiced_at=0.35):
        self.frame_ms = frame_ms
        self.hop_ms = hop_ms
        self.floor_db = floor_db
        self.f0_range = f0_range
        self.voiced_at = voiced_at

    def measure(self, samples, sr):
        frames = self._frames(samples, sr)
        if not len(frames):
            return {self.name: float("nan"), "hnr_db": float("nan"),
                    "voiced_fraction": float("nan")}

        low = max(2, int(sr / self.f0_range[1]))
        high = min(frames.shape[1] - 1, int(sr / self.f0_range[0]))
        if high <= low:
            return {self.name: float("nan"), "hnr_db": float("nan"),
                    "voiced_fraction": float("nan")}

        strengths, f0s = [], []
        for frame in frames:
            strength, lag = self._autocorrelation(frame, low, high)
            strengths.append(strength)
            f0s.append(sr / lag if lag else np.nan)

        strengths = np.array(strengths)
        voiced = strengths > self.voiced_at
        clipped = np.clip(strengths[voiced], 1e-6, 1 - 1e-6) if voiced.any() else None
        return {
            self.name: self._jitter(np.array(f0s), voiced),
            "hnr_db": float(np.median(10 * np.log10(clipped / (1 - clipped))))
            if clipped is not None else float("nan"),
            "voiced_fraction": float(voiced.mean()),
        }

    def _frames(self, samples, sr):
        samples = np.asarray(samples, dtype=np.float64)
        size = int(sr * self.frame_ms / 1000)
        hop = int(sr * self.hop_ms / 1000)
        if samples.size < size * 2:
            return np.zeros((0, size))
        starts = range(0, samples.size - size, hop)
        frames = np.stack([samples[s : s + size] for s in starts])
        energy = (frames ** 2).mean(axis=1)
        if not energy.max():
            return np.zeros((0, size))
        return frames[energy >= energy.max() * 10 ** (-self.floor_db / 10)]

    def _autocorrelation(self, frame, low, high):
        frame = frame - frame.mean()
        power = float(frame @ frame)
        if power <= 0:
            return 0.0, 0.0
        correlation = np.correlate(frame, frame, mode="full")[frame.size - 1 :]
        window = correlation[low : high + 1]
        if not window.size:
            return 0.0, 0.0
        best = int(np.argmax(window))
        return float(window[best] / power), low + self._refine(window, best)

    @staticmethod
    def _refine(window, best):
        """Sub-sample lag by fitting a parabola to the peak and its neighbours.

        Without this the lag is an integer number of samples, so at 24 kHz a
        700 Hz f0 can only land on about 34 or 35 samples — a 3% grid. Every
        frame-to-frame change smaller than that reads as exactly zero, and the
        measured jitter came back 0.000 for real and generated audio alike: a
        quantisation artefact wearing the costume of a null result.
        """
        if best <= 0 or best >= window.size - 1:
            return float(best)
        left, peak, right = window[best - 1], window[best], window[best + 1]
        denominator = left - 2 * peak + right
        if denominator == 0:
            return float(best)
        return float(best + 0.5 * (left - right) / denominator)

    def _jitter(self, f0s, voiced):
        values = []
        for start, end in self._runs(voiced):
            track = f0s[start:end]
            track = track[np.isfinite(track)]
            if track.size < 3:
                continue
            values.extend(np.abs(np.diff(track)) / track[:-1])
        return float(np.median(values)) if values else float("nan")

    def _runs(self, mask):
        edges = np.diff(mask.astype(np.int8))
        starts = list(np.flatnonzero(edges == 1) + 1)
        ends = list(np.flatnonzero(edges == -1) + 1)
        if mask.size and mask[0]:
            starts.insert(0, 0)
        if mask.size and mask[-1]:
            ends.append(mask.size)
        return [(s, e) for s, e in zip(starts, ends) if e - s >= 3]


class TimbrePanel:
    """Every measure over a set of clips, ready to compare arm against arm."""

    def __init__(self, measures=None):
        self.measures = measures or [FrameStitch(), OnsetSharpness(), HarmonicNoise()]

    def measure(self, samples, sr):
        out = {}
        for measure in self.measures:
            out.update(measure.measure(samples, sr))
        return out

    def across(self, clips, sr):
        rows = [self.measure(clip, sr) for clip in clips if clip is not None and len(clip)]
        if not rows:
            return {}
        return {key: np.array([row[key] for row in rows]) for key in rows[0]}
