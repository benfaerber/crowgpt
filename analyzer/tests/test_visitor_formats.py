"""A stranger's upload is read as the container its name claims, or not at all.

ffmpeg picks a demuxer from the bytes, so a playlist named clip.mp4 is opened
as a playlist and followed to whatever it names. The Scan page's worker passes
VISITOR_FORMATS, which leaves ffmpeg nothing to open it with.

    pipelines/representation/.venv-birdnet/bin/python -m pytest analyzer/tests -q
"""

import pytest

from analyzer import birdnet
from analyzer.tests.test_highpass import tone_wav


def test_a_playlist_named_as_a_video_is_refused(tmp_path):
    real = tone_wav(tmp_path / "real.wav")
    playlist = tmp_path / "clip.mp4"
    playlist.write_text(f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\n{real}\n#EXT-X-ENDLIST\n")
    assert birdnet.has_audio_track(playlist), "unrestricted, ffmpeg follows it"
    with pytest.raises(ValueError, match="could not read"):
        birdnet.to_wav(playlist, formats=birdnet.VISITOR_FORMATS)


def test_a_real_recording_still_decodes_and_is_cut_to_length(tmp_path):
    wav = birdnet.to_wav(tone_wav(tmp_path / "real.wav", seconds=3.0), max_seconds=1,
                         formats=birdnet.VISITOR_FORMATS)
    try:
        assert birdnet.waveform_envelope(wav)[1] == pytest.approx(1.0, abs=0.05)
    finally:
        wav.unlink()
