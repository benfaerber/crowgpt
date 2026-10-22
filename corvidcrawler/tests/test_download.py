"""The Downloader: a partial never becomes the destination, and a 200 is not
proof of audio."""

import pytest
import requests

from conftest import FakeResponse, ScriptedSession
from corvidcrawler.download import Downloader
from corvidcrawler.politeness import Bucket


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr("corvidcrawler.download.time.sleep", lambda _: None)


def downloader(session, **kwargs):
    return Downloader(delay=0, session=session, bucket=Bucket(sleeper=lambda _s: None), **kwargs)


def test_a_finished_file_is_never_refetched(tmp_path, quick):
    dest = tmp_path / "1.mp3"
    dest.write_bytes(b"already here")
    session = ScriptedSession([])

    assert downloader(session).fetch("http://x/1", dest) is True
    assert session.calls == []


def test_a_partial_download_never_becomes_the_destination(tmp_path, quick):
    class Failing(ScriptedSession):
        def get(self, url, **kwargs):
            raise requests.ConnectionError("cut off")

    dest = tmp_path / "1.mp3"

    assert downloader(Failing([]), retries=1).fetch("http://x/1", dest) is False
    assert not dest.exists()


def test_a_leftover_part_file_is_resumed_not_restarted(tmp_path, quick):
    dest = tmp_path / "1.mp3"
    (tmp_path / "1.mp3.part").write_bytes(b"AAA")
    session = ScriptedSession([FakeResponse(status_code=206, body=b"BBB")])

    assert downloader(session).fetch("http://x/1", dest) is True
    assert dest.read_bytes() == b"AAABBB"
    assert session.calls[0][1]["headers"]["Range"] == "bytes=3-"


def test_it_identifies_itself(tmp_path, quick):
    session = ScriptedSession([FakeResponse(body=b"ok")])

    downloader(session).fetch("http://x/1", tmp_path / "1.mp3")

    assert "CrowGPT" in session.calls[0][1]["headers"]["User-Agent"]


def test_a_rate_limit_is_waited_out(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("corvidcrawler.download.time.sleep", slept.append)
    session = ScriptedSession([FakeResponse(status_code=429, headers={"Retry-After": "7"}),
                               FakeResponse(body=b"ok")])

    assert downloader(session).fetch("http://x/1", tmp_path / "1.mp3") is True
    assert 7.0 in slept


def test_an_html_error_body_is_retried_not_kept(tmp_path, quick):
    session = ScriptedSession([FakeResponse(body=b"<html><body>503</body></html>"),
                               FakeResponse(body=b"ID3 realaudio")])
    dest = tmp_path / "song.mp3"

    assert downloader(session).fetch("http://x/a.mp3", dest)
    assert dest.read_bytes().startswith(b"ID3")
    assert len(session.calls) == 2


def test_a_server_that_only_serves_errors_yields_no_file(tmp_path, quick):
    session = ScriptedSession([FakeResponse(body=b"<!DOCTYPE html><p>down</p>")] * 3)
    dest = tmp_path / "song.mp3"

    assert not downloader(session, retries=3).fetch("http://x/a", dest)
    assert not dest.exists() and not dest.with_suffix(".mp3.part").exists()


def test_bytes_in_flight_are_reported(tmp_path, quick):
    session = ScriptedSession([FakeResponse(body=b"abcdef", headers={"Content-Length": "6"})])
    seen = []

    downloader(session).fetch("http://x/1", tmp_path / "1.mp3", on_bytes=lambda d, t: seen.append((d, t)))

    assert seen == [(6, 6)]
