"""What stops a bad upload from wedging the server.

Every ffmpeg call here decodes bytes a phone sent, and a malformed container can
make a decoder spin rather than fail. The request path used to have no bound at
all — the offline scripts in pipelines/ have carried a timeout since they were
written, and the one place reachable by anything holding an enrolment token did
not. A stuck decoder holds a worker thread forever and accumulates stderr in the
parent while it does.

These tests are about the guards rather than the audio: that a timeout is asked
for, that it arrives as the same error every other failure does, and that the
child cannot reach the terminal its parent was started from.
"""

import shutil
import subprocess

import pytest

from fieldserver.core import transcode

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed here"
)


def test_every_call_asks_for_a_timeout(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=b"x")

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    transcode.run_ffmpeg(["-i", "in.wav", "out.wav"], "could not test")

    assert seen["timeout"] == transcode.FFMPEG_TIMEOUT_SEC
    assert seen["timeout"] > 0


def test_nostdin_precedes_the_input(monkeypatch):
    """A child inheriting the terminal can otherwise swallow the parent's input."""
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=b"x")

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    transcode.run_ffmpeg(["-i", "in.wav", "out.wav"], "could not test")

    args = seen["args"]
    assert args[0] == "ffmpeg"
    assert "-nostdin" in args
    assert args.index("-nostdin") < args.index("-i")


def test_a_timeout_is_a_transcode_error(monkeypatch):
    """Callers respond to every failure the same way: leave the original alone.

    A decoder that hangs is not a special case needing its own handling at each
    call site — it is one more way the audio did not survive.
    """

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 1))

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    with pytest.raises(transcode.TranscodeError) as raised:
        transcode.run_ffmpeg(["-i", "in.wav", "out.wav"], "could not decode clip.wav")

    assert "could not decode clip.wav" in str(raised.value)
    assert "still running" in str(raised.value)


def test_a_timed_out_encode_leaves_nothing_behind(monkeypatch, tmp_path):
    """The half-written FLAC must go, and the original must not be touched."""
    source = tmp_path / "capture.wav"
    source.write_bytes(b"original bytes")
    target = tmp_path / "capture.flac"
    target.write_bytes(b"half a flac")

    monkeypatch.setattr(transcode, "pcm_sha256", lambda path: "same")

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 1)

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    with pytest.raises(transcode.TranscodeError):
        transcode.to_flac(source, target)

    assert not target.exists()
    assert source.read_bytes() == b"original bytes"


def test_memory_cap_is_wired_when_configured(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout=b"x")

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    transcode.run_ffmpeg(["-i", "in.wav", "out.wav"], "could not test")

    if transcode.FFMPEG_MEMORY_MB:
        assert seen["preexec_fn"] is transcode._cap_memory
    else:
        assert seen["preexec_fn"] is None


@needs_ffmpeg
def test_the_guards_do_not_break_a_real_decode(tmp_path):
    """The whole point is that ordinary audio still goes through untouched."""
    source = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", str(source)],
        check=True, capture_output=True,
    )

    target = tmp_path / "tone.flac"
    digest = transcode.to_flac(source, target)

    assert target.exists()
    assert digest == transcode.pcm_sha256(source)
