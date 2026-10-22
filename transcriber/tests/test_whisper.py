"""What has to be true of the transcriber before a transcript can be believed.

Two of these are about failures that produce no error at all — a process that has
silently lost the GPU, and a memo silently cut to its first thirty seconds. Those
are the ones worth having, because nothing downstream can tell that either
happened: the transcript reads fine.

    ../crowgpt/.venv/bin/python -m pytest transcriber/tests -q
"""

import subprocess
import sys
import types
import wave

import pytest


def test_the_birdnetlib_guard_refuses_rather_than_going_slow(monkeypatch):
    """Importing birdnetlib first takes CUDA away from torch permanently, and
    the only symptom is a run ~20x slower. crowgpt/src/crowgpt/gpu.py is the
    record of that costing a night. Refusing to start is the whole point."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys, types\n"
         "sys.modules['birdnetlib'] = types.ModuleType('birdnetlib')\n"
         "from transcriber import whisper\n"],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "birdnetlib is already loaded" in result.stderr


def sine_wav(path, seconds, rate=48_000):
    """A file of the right shape and length. Nothing here listens to it."""
    import math

    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            value = int(8000 * math.sin(2 * math.pi * 220 * i / rate))
            frames += value.to_bytes(2, "little", signed=True)
        fh.writeframes(bytes(frames))
    return path


class TestRendering:
    def test_it_renders_to_sixteen_kilohertz_mono(self, tmp_path):
        """What Whisper consumes. Handing it anything else costs a resample and
        changes nothing, and 16 kHz is a third of the bytes on the wire."""
        from transcriber import whisper

        source = sine_wav(tmp_path / "memo.wav", 2, rate=48_000)
        rendered = whisper.to_wav(source)
        try:
            with wave.open(str(rendered)) as fh:
                assert fh.getframerate() == whisper.SAMPLE_RATE
                assert fh.getnchannels() == 1
        finally:
            rendered.unlink(missing_ok=True)

    def test_a_file_with_no_sound_says_so(self, tmp_path):
        """Its own exception type, for the reason the analyzer's has one: a
        silent file failing as a raw subprocess error reads as 'the transcriber
        crashed' when the truth is 'there is nothing here to listen to'."""
        from transcriber import whisper

        junk = tmp_path / "notaudio.wav"
        junk.write_bytes(b"this is not a RIFF file")
        with pytest.raises(whisper.NoAudioTrack):
            whisper.to_wav(junk)


class TestLongForm:
    """The single most likely defect in the whole feature.

    Whisper's encoder takes exactly thirty seconds. The obvious processor call
    pads or truncates to that, so a ninety-second memo comes back as a fluent,
    confident transcript of its first third — no error, nothing in the output
    saying a word about it. These assert on the features rather than on a
    transcript, so they need no speech and no model weights: the defect lives
    entirely in whether the features cover the file.
    """

    @pytest.fixture(scope="class")
    def processor(self):
        transformers = pytest.importorskip("transformers")
        try:
            return transformers.AutoProcessor.from_pretrained(
                "openai/whisper-tiny.en")
        except Exception as exc:  # noqa: BLE001 — offline, most likely
            pytest.skip(f"could not fetch a processor: {exc}")

    def audio(self, seconds, rate=16_000):
        import numpy as np

        return np.zeros(int(rate * seconds), dtype="float32")

    def test_the_naive_call_silently_truncates(self, processor):
        """Pinning the trap itself, so nobody 'simplifies' the kwargs away."""
        naive = processor(self.audio(90), sampling_rate=16_000,
                          return_tensors="pt")
        # 3000 frames is exactly Whisper's thirty seconds. Sixty seconds of the
        # memo are simply gone, and nothing anywhere says so.
        assert naive.input_features.shape[-1] == 3000

    def test_our_call_keeps_the_whole_memo(self, processor):
        long_form = processor(self.audio(90), sampling_rate=16_000,
                              return_tensors="pt", truncation=False,
                              padding="longest", return_attention_mask=True)
        assert long_form.input_features.shape[-1] > 3000
        # The mask is what tells generate() to take the sequential long-form
        # path rather than treating the extra frames as padding.
        assert hasattr(long_form, "attention_mask")

    def test_a_short_memo_is_unaffected(self, processor):
        """The kwargs must not change anything for the common case."""
        short = processor(self.audio(10), sampling_rate=16_000,
                          return_tensors="pt", truncation=False,
                          padding="longest", return_attention_mask=True)
        assert short.input_features.shape[-1] <= 3000
