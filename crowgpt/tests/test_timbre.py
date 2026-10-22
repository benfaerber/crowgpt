"""The timbre measures, checked against signals whose answer is known.

The frame-stitch measure is the one worth testing hardest, because it is the
only one claiming a null it did not measure: real audio has no reason to prefer
the codec's frame phase, so it should score zero without anyone calibrating it.
If that is not true on synthetic audio it is not true on crows either.
"""

import numpy as np
import pytest

from crowgpt.timbre import CODEC_HOP, FrameStitch, HarmonicNoise, OnsetSharpness, TimbrePanel

SR = 24000


def noise(seconds=3.0, seed=0, scale=0.1):
    return np.random.default_rng(seed).normal(0, scale, int(SR * seconds)).astype(np.float32)


def blocked(period, seconds=3.0, seed=0, depth=0.5):
    """Noise whose gain jumps every `period` samples.

    A per-block gain is what a decoder actually does when it is handed tokens
    that do not belong next to each other: the discontinuity lands on the block
    edge. Offsetting the whole tail instead would build a random walk, which is
    a different signal and does not test this.
    """
    samples = noise(seconds, seed)
    rng = np.random.default_rng(seed + 100)
    for index in range(samples.size // period):
        gain = 1.0 + depth * rng.normal()
        samples[index * period : (index + 1) * period] *= gain
    return samples


def caw(seconds=0.4, f0=700.0, rise_ms=8.0, seed=0):
    """A harmonic burst with a sharp attack — a crude stand-in for a call."""
    t = np.arange(int(SR * seconds)) / SR
    tone = sum(np.sin(2 * np.pi * f0 * h * t) / h for h in (1, 2, 3, 4))
    envelope = np.clip(t / (rise_ms / 1000), 0, 1) * np.exp(-t * 6)
    grit = np.random.default_rng(seed).normal(0, 0.02, t.size)
    return ((tone * envelope) + grit).astype(np.float32)


class TestFrameStitch:
    def test_plain_noise_scores_about_zero(self):
        """The null is structural, not calibrated: no grid, no reading."""
        score = FrameStitch().measure(noise(), SR)["stitch_db"]
        assert abs(score) < 6.0

    def test_a_signal_cut_on_the_codec_grid_scores_high(self):
        clean = FrameStitch().measure(noise(seed=1), SR)["stitch_db"]
        rough = FrameStitch().measure(blocked(CODEC_HOP, seed=1), SR)["stitch_db"]
        assert rough > clean + 6.0

    def test_a_grid_at_the_wrong_rate_does_not_trigger_it(self):
        """It must answer 75 Hz specifically, not periodicity in general."""
        on_grid = FrameStitch().measure(blocked(CODEC_HOP, seed=2), SR)["stitch_db"]
        off_grid = FrameStitch().measure(blocked(512, seed=2), SR)["stitch_db"]
        assert off_grid < on_grid - 6.0

    def test_silence_does_not_raise(self):
        assert np.isnan(FrameStitch().measure(np.zeros(64, dtype=np.float32), SR)["stitch_db"])


class TestOnsetSharpness:
    def test_a_sharp_attack_reads_faster_than_a_smeared_one(self):
        sharp = OnsetSharpness().measure(caw(rise_ms=3), SR)["rise_ms"]
        soft = OnsetSharpness().measure(caw(rise_ms=60), SR)["rise_ms"]
        assert sharp < soft

    def test_it_recovers_roughly_the_rise_it_was_given(self):
        measured = OnsetSharpness().measure(caw(rise_ms=20), SR)["rise_ms"]
        assert 5 < measured < 45

    def test_a_flat_signal_declines_to_answer(self):
        result = OnsetSharpness().measure(np.zeros(SR, dtype=np.float32), SR)
        assert np.isnan(result["rise_ms"])


class TestHarmonicNoise:
    def test_a_tone_is_voiced_and_noise_is_not(self):
        tonal = HarmonicNoise().measure(caw(seconds=1.0), SR)
        hiss = HarmonicNoise().measure(noise(1.0), SR)
        assert tonal["voiced_fraction"] > hiss["voiced_fraction"]

    def test_a_steady_pitch_jitters_less_than_a_wobbling_one(self):
        t = np.arange(SR) / SR
        steady = np.sin(2 * np.pi * 700 * t).astype(np.float32)
        wobble = np.sin(
            2 * np.pi * (700 + 220 * np.sin(2 * np.pi * 23 * t)) * t
        ).astype(np.float32)

        calm = HarmonicNoise().measure(steady, SR)["jitter"]
        rough = HarmonicNoise().measure(wobble, SR)["jitter"]
        assert calm < rough

    def test_a_clean_tone_has_a_high_harmonic_to_noise_ratio(self):
        t = np.arange(SR) / SR
        tone = np.sin(2 * np.pi * 600 * t).astype(np.float32)
        assert HarmonicNoise().measure(tone, SR)["hnr_db"] > 10


class TestThePanel:
    def test_it_returns_one_row_per_clip(self):
        panel = TimbrePanel()
        columns = panel.across([caw(), caw(seed=1), caw(seed=2)], SR)
        assert all(values.size == 3 for values in columns.values())

    def test_every_measure_is_present(self):
        keys = set(TimbrePanel().measure(caw(), SR))
        assert {"stitch_db", "rise_ms", "crest", "jitter", "hnr_db", "voiced_fraction"} <= keys

    def test_an_empty_set_is_not_an_error(self):
        assert TimbrePanel().across([], SR) == {}
