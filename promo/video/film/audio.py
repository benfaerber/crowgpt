"""What the picture needs from a call: its loudness per frame and its spectrogram."""

import wave

import numpy as np


class Clip:
    BAND_RANGE_HZ = (350.0, 9000.0)
    VOICE_RANGE_HZ = (900.0, 4000.0)
    WINDOW = 1024
    DYNAMIC_RANGE_DB = 45.0

    def __init__(self, path, fps):
        with wave.open(str(path)) as source:
            if source.getsampwidth() != 2 or source.getnchannels() != 1:
                raise ValueError(f"{path} must be 16-bit mono; render.py prepares it that way")
            self.rate = source.getframerate()
            raw = source.readframes(source.getnframes())
        self.samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        self.fps = fps

    @property
    def frames(self):
        return int(np.ceil(len(self.samples) / self.rate * self.fps))

    def envelope(self):
        """Loudness per video frame in the band a caw lives in, above the clip's own floor."""
        hop = self.rate / self.fps
        levels = np.array([
            self._voiced(self.samples[int(i * hop):int((i + 1) * hop)])
            for i in range(self.frames)
        ])
        floor = np.percentile(levels, 20)
        ceiling = np.percentile(levels, 95)
        if ceiling <= floor:
            return np.zeros(len(levels))
        return np.clip((levels - floor) / (ceiling - floor), 0.0, 1.0) ** 0.7

    def _voiced(self, chunk):
        if len(chunk) < 16:
            return 0.0
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(len(chunk))))
        freqs = np.fft.rfftfreq(len(chunk), 1.0 / self.rate)
        low, high = self.VOICE_RANGE_HZ
        return float(np.sqrt(np.mean(spectrum[(freqs >= low) & (freqs < high)] ** 2)))

    def onsets(self, threshold=0.45, gap=8):
        envelope = self.envelope()
        found = []
        for i, level in enumerate(envelope):
            before = envelope[i - 1] if i else 0.0
            rising = level >= threshold > before
            if rising and (not found or i - found[-1] >= gap):
                found.append(i)
        return found

    def spectrogram(self, columns, bands):
        half = self.WINDOW // 2
        padded = np.pad(self.samples, (half, half))
        window = np.hanning(self.WINDOW)
        freqs = np.fft.rfftfreq(self.WINDOW, 1.0 / self.rate)
        edges = np.geomspace(*self.BAND_RANGE_HZ, bands + 1)
        masks = [(freqs >= edges[b]) & (freqs < edges[b + 1]) for b in range(bands)]
        centres = np.linspace(0, len(self.samples) - 1, columns).astype(int)
        grid = np.zeros((columns, bands))
        for column, centre in enumerate(centres):
            magnitude = np.abs(np.fft.rfft(padded[centre:centre + self.WINDOW] * window))
            for band, mask in enumerate(masks):
                grid[column, band] = magnitude[mask].mean() if mask.any() else 0.0
        decibels = 20.0 * np.log10(grid + 1e-9)
        floor = decibels.max() - self.DYNAMIC_RANGE_DB
        return np.clip((decibels - floor) / self.DYNAMIC_RANGE_DB, 0.0, 1.0)
