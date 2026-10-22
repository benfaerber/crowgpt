"""The 300 Hz analysis high-pass: measured twice (0008, 0031), applied once.

The filter lives inside analyze(), so these test the rendering function it
uses and the version string that makes filtered and unfiltered analyses
distinguishable in storage. Quality must keep reading unfiltered audio —
that contract is a docstring and a worker-code comment, not testable here.

    pipelines/representation/.venv-birdnet/bin/python -m pytest analyzer/tests -q
"""

import wave
from pathlib import Path

import numpy as np

from analyzer import birdnet

SR = 48000


def tone_wav(path: Path, seconds=2.0):
    t = np.arange(int(SR * seconds)) / SR
    mixed = 0.4 * np.sin(2 * np.pi * 100 * t) + 0.4 * np.sin(2 * np.pi * 1000 * t)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mixed * 32767).astype(np.int16).tobytes())
    return path


def band_power(samples, hz, width=20):
    spectrum = np.abs(np.fft.rfft(samples)) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1 / SR)
    return float(spectrum[(freqs > hz - width) & (freqs < hz + width)].sum())


def test_the_filter_cuts_the_low_band_and_spares_the_crow(tmp_path):
    src = tone_wav(tmp_path / "tones.wav")
    out = birdnet.highpassed(src)
    try:
        with wave.open(str(out), "rb") as w:
            filtered = np.frombuffer(
                w.readframes(w.getnframes()), dtype=np.int16) / 32767
    finally:
        out.unlink(missing_ok=True)
    with wave.open(str(src), "rb") as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32767

    drop_100 = 10 * np.log10(band_power(raw, 100) / band_power(filtered, 100))
    drop_1k = 10 * np.log10(band_power(raw, 1000) / band_power(filtered, 1000))
    assert drop_100 > 20, f"100 Hz only dropped {drop_100:.1f} dB"
    assert abs(drop_1k) < 3, f"1 kHz moved {drop_1k:.1f} dB"


def test_model_version_names_the_filter():
    assert f"+{birdnet.ANALYSIS_FILTER}" in birdnet.HEADS.version()
