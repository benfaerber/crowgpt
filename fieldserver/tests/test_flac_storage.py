"""Audio is stored as FLAC, and the encoder is never believed.

Lossless is measured rather than assumed — experiments/0007, bit-exact on all
77 files in the corpus — but "measured on today's files with today's ffmpeg" is
not "true forever". So every transcode is verified sample-for-sample, and these
tests are mostly about what happens when that verification fails: nothing is
deleted, nothing is renamed, and the recording is still there.

The other half is the phone. It parses RIFF headers directly to draw waveforms,
normalise playback and crop before upload, so it can ask for a WAV back.
"""

import shutil
import struct
import subprocess

import pytest

from fieldserver.core import transcode


def wav_bytes(seconds=0.25, rate=48_000, freq=1000.0):
    """A small real WAV, since ffmpeg is going to have opinions about it."""
    import math

    frames = int(rate * seconds)
    samples = b"".join(
        struct.pack("<h", int(math.sin(2 * math.pi * freq * i / rate) * 8000))
        for i in range(frames)
    )
    header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(samples))
    return header + samples


needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed here"
)


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "capture.wav"
    path.write_bytes(wav_bytes())
    return path


@needs_ffmpeg
class TestTranscoding:

    def test_the_samples_survive(self, wav, tmp_path):
        flac = tmp_path / "capture.flac"
        returned = transcode.to_flac(wav, flac)
        assert returned == transcode.pcm_sha256(wav)
        assert transcode.pcm_sha256(flac) == transcode.pcm_sha256(wav)

    def test_it_is_smaller(self, wav, tmp_path):
        flac = tmp_path / "capture.flac"
        transcode.to_flac(wav, flac)
        assert flac.stat().st_size < wav.stat().st_size

    def test_a_file_that_is_not_audio_is_refused(self, tmp_path):
        junk = tmp_path / "notaudio.wav"
        junk.write_bytes(b"this is not a RIFF file")
        with pytest.raises(transcode.TranscodeError):
            transcode.to_flac(junk, tmp_path / "out.flac")

    def test_a_failed_encode_leaves_nothing_behind(self, tmp_path):
        junk = tmp_path / "notaudio.wav"
        junk.write_bytes(b"nope")
        target = tmp_path / "out.flac"
        with pytest.raises(transcode.TranscodeError):
            transcode.to_flac(junk, target)
        assert not target.exists()
        assert junk.exists()

    def test_rendering_back_to_wav_returns_the_same_samples(self, wav, tmp_path):
        # What the phone gets on restore. It has to be the same audio, or the
        # waveform it draws is of something else.
        flac = tmp_path / "capture.flac"
        transcode.to_flac(wav, flac)
        back = transcode.to_wav(flac, tmp_path / "back.wav")
        assert transcode.pcm_sha256(back) == transcode.pcm_sha256(wav)
        assert back.read_bytes()[:4] == b"RIFF"


@needs_ffmpeg
class TestKeepingTheOriginal:

    def test_the_wav_is_moved_rather_than_deleted(self, wav, tmp_path):
        # The verification is strong, but it is a check written by the same
        # hand as the thing it checks, and a field recording cannot be
        # collected again.
        backups = tmp_path / "media-originals"
        kept = transcode.archive(wav, backups)
        assert kept.exists()
        assert kept.read_bytes()[:4] == b"RIFF"
        assert not wav.exists()


@needs_ffmpeg
class TestThroughTheStore:

    @pytest.fixture
    def uploaded(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                              headers=recordist.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "m-1", "kind": "audio",
                                  "format": "wav"},
                            headers=recordist.headers).get_json()
        body = wav_bytes()
        client.put(f"/api/media/{media['id']}",
                   data=body,
                   headers={**recordist.headers,
                            "Content-Type": "application/octet-stream",
                            "Content-Range": f"bytes 0-{len(body) - 1}/{len(body)}"})
        return capture, media

    def test_a_completed_upload_ends_up_stored_as_flac(self, client, recordist,
                                                       uploaded, app):
        _, media = uploaded
        rows = client.get(f"/api/captures/{uploaded[0]['id']}/media",
                          headers=recordist.headers).get_json()
        stored = next(r for r in rows if r["id"] == media["id"])
        assert stored["format"] == "flac"
        assert stored["storage_ref"].endswith(".flac")
        # The hash of the samples, which survives re-containering — the one a
        # mover can verify a copy against. See migration 0009.
        assert stored["pcm_sha256"]

    def test_the_dashboard_gets_the_stored_bytes(self, client, recordist, uploaded):
        _, media = uploaded
        answer = client.get(f"/api/media/{media['id']}/raw", headers=recordist.headers)
        assert answer.status_code == 200
        assert answer.data[:4] == b"fLaC"

    def test_the_phone_can_ask_for_a_wav(self, client, recordist, uploaded):
        # It parses RIFF directly in three places; handing it FLAC would leave a
        # restored capture playable but with no waveform and no playback boost.
        _, media = uploaded
        answer = client.get(f"/api/media/{media['id']}/raw?format=wav",
                            headers=recordist.headers)
        assert answer.status_code == 200
        assert answer.data[:4] == b"RIFF"

    def test_asking_for_wav_when_it_is_already_wav_is_harmless(self, client,
                                                               recordist, uploaded):
        _, media = uploaded
        first = client.get(f"/api/media/{media['id']}/raw?format=wav",
                           headers=recordist.headers)
        second = client.get(f"/api/media/{media['id']}/raw?format=wav",
                            headers=recordist.headers)
        assert first.data == second.data
