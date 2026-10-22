"""Xeno-canto: paging, duration, and the key that must not reach an error."""

import traceback

import pytest
import requests

from corvidcrawler.xeno_canto import (
    XenoCantoError,
    XenoCantoSource,
    build_query,
    parse_length_seconds,
)

KEY = "test-key-not-a-real-secret-0000000000000"


def recording(rid, length="1:30", **overrides):
    return {"id": rid, "gen": "Corvus", "sp": "corone", "en": "Carrion Crow",
            "length": length, "rec": "A Recordist", "date": "2020-05-01",
            "file": f"//x/{rid}.mp3", "q": "A", **overrides}


def page(recordings, num_pages=1, num_recordings=None):
    return {"numRecordings": str(len(recordings) if num_recordings is None else num_recordings),
            "numPages": num_pages, "recordings": recordings}


class Feed:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def __call__(self, url, params=None, **kwargs):
        self.calls.append(params or {})
        payload = self.pages[min(int((params or {}).get("page", 1)) - 1, len(self.pages) - 1)]

        class Response:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return payload

        return Response()


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("XENOCANTO_KEY", KEY)
    monkeypatch.setattr("corvidcrawler.xeno_canto.time.sleep", lambda _: None)
    return XenoCantoSource()


class TestPaging:
    def test_it_pages_until_the_api_says_there_is_no_more(self, source, monkeypatch):
        pages = [page([recording(i)], num_pages=30, num_recordings=30) for i in range(1, 31)]
        monkeypatch.setattr(requests, "get", Feed(pages))

        assert len(list(source.fetch("gen:Corvus", max_recordings=100))) == 30

    def test_max_recordings_stops_it(self, source, monkeypatch):
        pages = [page([recording(i)], num_pages=30, num_recordings=30) for i in range(1, 31)]
        monkeypatch.setattr(requests, "get", Feed(pages))

        assert len(list(source.fetch("q", max_recordings=4))) == 4

    def test_counting_then_fetching_asks_for_page_one_once(self, source, monkeypatch):
        feed = Feed([page([recording(1)])])
        monkeypatch.setattr(requests, "get", feed)

        source.count("gen:Corvus")
        list(source.fetch("gen:Corvus", max_recordings=10))

        assert [c["page"] for c in feed.calls] == [1]

    def test_refresh_is_accepted_and_ignored(self, source, monkeypatch):
        """The shared call site passes it to whichever source it holds."""
        monkeypatch.setattr(requests, "get", Feed([page([recording(1)])]))

        assert [r["source_ref"] for r in
                source.fetch("gen:Corvus", max_recordings=5, refresh=True)] == ["1"]


class TestDuration:
    @pytest.mark.parametrize("text,seconds", [
        ("0:04", 4), ("1:30", 90), ("4:07", 247), ("1:02:03", 3723), ("0:00", 0), (12, 12),
    ])
    def test_clock_text_becomes_seconds(self, text, seconds):
        assert parse_length_seconds(text) == seconds

    @pytest.mark.parametrize("bad", [None, "", "nonsense", "a:b", "--"])
    def test_anything_unparseable_is_none_rather_than_zero(self, bad):
        assert parse_length_seconds(bad) is None

    def test_a_normalized_recording_carries_seconds_and_a_date(self):
        record = XenoCantoSource.normalize(recording(7, length="2:05"))

        assert record["duration_seconds"] == 125
        assert record["date"] == "2020-05-01"
        assert record["recordist_id"] is None
        assert record["audio_url"] == "https://x/7.mp3"


class TestTheQueryBuilder:
    def test_a_value_with_a_space_is_quoted(self):
        assert build_query({"gen": "Corvus", "call_type": "alarm call"}) == 'gen:Corvus type:"alarm call"'

    def test_an_operator_is_quoted(self):
        assert build_query({"gen": "Corvus", "quality": ">C"}) == 'gen:Corvus q:">C"'


def raise_timeout(*_args, **_kwargs):
    raise requests.exceptions.ConnectTimeout(
        f"HTTPSConnectionPool(host='xeno-canto.org', port=443): Max retries "
        f"exceeded with url: /api/3/recordings?query=gen%3ACorvus&key={KEY}&page=1")


class TestTheKeyNeverReachesAnError:
    def test_a_transport_failure_is_redacted(self, source, monkeypatch):
        monkeypatch.setattr(requests, "get", raise_timeout)
        with pytest.raises(XenoCantoError, match="ConnectTimeout") as e:
            source.count("gen:Corvus")
        assert KEY not in str(e.value)
        assert "<key redacted>" in str(e.value)

    def test_no_unredacted_copy_survives_on_the_exception_chain(self, source, monkeypatch):
        monkeypatch.setattr(requests, "get", raise_timeout)
        with pytest.raises(XenoCantoError) as e:
            source.count("gen:Corvus")
        assert e.value.__cause__ is None and e.value.__context__ is None
        rendered = "".join(traceback.format_exception(type(e.value), e.value, e.value.__traceback__))
        assert KEY not in rendered

    def test_a_body_echoing_the_key_is_scrubbed(self, source, monkeypatch):
        class Response:
            status_code = 401
            text = f"unauthorized for key={KEY}"

        monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
        with pytest.raises(XenoCantoError, match="401") as e:
            source.count("gen:Corvus")
        assert KEY not in str(e.value)

    def test_a_missing_key_says_so(self):
        with pytest.raises(XenoCantoError, match="XENOCANTO_KEY"):
            XenoCantoSource().count("gen:Corvus")
