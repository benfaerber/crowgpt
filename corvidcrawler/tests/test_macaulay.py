"""Macaulay: the cache that keeps us off their API, and the cursor rule."""

import pytest

from conftest import FakeResponse, ScriptedSession
from corvidcrawler.macaulay import (
    CATALOG_NUMBER,
    AssetCache,
    MacaulayError,
    MacaulaySearch,
    MacaulaySource,
    read_catalogue,
)


def asset(asset_id, cursor=None, **overrides):
    return {
        "assetId": asset_id,
        "cursorMark": cursor,
        "taxonomy": {"comName": "Rook", "sciName": "Corvus frugilegus"},
        "location": {"countryName": "United Kingdom", "name": "Elkstone",
                     "latitude": 53.1, "longitude": -1.9},
        "userDisplayName": "A Recordist",
        "userId": "USER1",
        "obsDt": "2020-08-14T07:15:00",
        "rating": 4.9,
        "tags": ["call", "flight_call", "no_playback"],
        "licenseId": "LICENSE2",
        **overrides,
    }


class TestAnAssetFromTheSearchApi:
    def test_it_becomes_the_same_shape_a_csv_row_does(self):
        record = MacaulaySource.normalize_asset(asset(255641931))

        assert record["source_ref"] == "255641931"
        assert record["species"] == "Rook"
        assert record["recordist_id"] == "USER1"
        assert record["date"] == "2020-08-14"
        assert record["audio_url"].endswith("/asset/255641931/mp3")

    def test_housekeeping_tags_are_not_call_types(self):
        assert MacaulaySource.normalize_asset(asset(1))["call_type"] == "call; flight_call"

    def test_an_asset_with_no_behaviour_tags_has_no_call_type(self):
        assert MacaulaySource.normalize_asset(asset(1, tags=["no_playback"]))["call_type"] is None


class TestTheSearch:
    def test_it_pages_on_the_last_result_s_cursor(self):
        session = ScriptedSession([
            FakeResponse(payload=[asset(1), asset(2, cursor="CURSOR-A")]),
            FakeResponse(payload=[asset(3, cursor=None)]),
        ])
        search = MacaulaySearch(delay=0, session=session)

        assert [a["assetId"] for a in search.assets("rook1")] == [1, 2, 3]
        assert session.calls[1][1]["params"]["initialCursorMark"] == "CURSOR-A"

    def test_restricted_assets_are_never_yielded(self):
        session = ScriptedSession([
            FakeResponse(payload=[asset(1), asset(2, restricted=True, cursor=None)])])

        assert [a["assetId"] for a in MacaulaySearch(delay=0, session=session).assets("rook1")] == [1]

    def test_it_does_not_ask_for_a_hundred_to_satisfy_a_limit_of_two(self):
        session = ScriptedSession([FakeResponse(payload=[asset(1), asset(2, cursor=None)])])

        list(MacaulaySearch(delay=0, session=session).assets("rook1", limit=2))

        assert session.calls[0][1]["params"]["count"] == 2

    def test_a_server_error_is_retried_rather_than_raised(self, monkeypatch):
        monkeypatch.setattr("corvidcrawler.macaulay.time.sleep", lambda _: None)
        session = ScriptedSession([FakeResponse(status_code=503),
                                   FakeResponse(payload=[asset(1, cursor=None)])])

        assert [a["assetId"] for a in MacaulaySearch(delay=0, session=session).assets("rook1")] == [1]

    def test_a_browser_check_page_points_at_the_csv_export(self):
        """The search host may answer with a bot challenge instead of JSON.
        That is not transient, and the export by hand is the route left."""
        session = ScriptedSession([FakeResponse(
            text="<!doctype html><html><head><title>Making sure you're not a bot!</title>")])

        with pytest.raises(MacaulayError, match="--csv") as e:
            list(MacaulaySearch(delay=0, session=session).assets("rook1"))
        assert "taxonCode=rook1" in str(e.value)
        assert len(session.calls) == 1

    def test_a_refusal_that_is_not_transient_says_so(self):
        session = ScriptedSession([FakeResponse(status_code=403)])

        with pytest.raises(MacaulayError, match="403"):
            list(MacaulaySearch(delay=0, session=session).assets("rook1"))

    def test_a_species_slug_is_turned_into_its_ebird_code(self):
        session = ScriptedSession([FakeResponse(payload=[asset(1, cursor=None)])])
        source = MacaulaySource(search=MacaulaySearch(delay=0, session=session))

        list(source.fetch("rook", max_recordings=5))

        assert session.calls[0][1]["params"]["taxonCode"] == "rook1"


class TestTheCache:
    def test_a_second_run_asks_the_api_for_nothing(self, tmp_path):
        session = ScriptedSession([FakeResponse(payload=[asset(1), asset(2, cursor=None)])])
        list(MacaulaySearch(delay=0, session=session, cache_dir=tmp_path).assets("rook1"))
        first_pass = len(session.calls)

        again = MacaulaySearch(delay=0, session=session, cache_dir=tmp_path)

        assert [a["assetId"] for a in again.assets("rook1")] == [1, 2]
        assert len(session.calls) == first_pass

    def test_an_interrupted_crawl_resumes_from_its_cursor(self, tmp_path):
        session = ScriptedSession([FakeResponse(payload=[asset(1, cursor="CURSOR-A")])])
        list(MacaulaySearch(delay=0, session=session, cache_dir=tmp_path).assets("rook1", limit=1))

        session.responses.append(FakeResponse(payload=[asset(2, cursor=None)]))
        resumed = MacaulaySearch(delay=0, session=session, cache_dir=tmp_path)

        assert [a["assetId"] for a in resumed.assets("rook1")] == [1, 2]
        assert session.calls[-1][1]["params"]["initialCursorMark"] == "CURSOR-A"

    def test_refresh_throws_the_cache_away(self, tmp_path):
        AssetCache(tmp_path, "rook1").append([asset(99)], cursor="")
        session = ScriptedSession([FakeResponse(payload=[asset(1, cursor=None)])])
        search = MacaulaySearch(delay=0, session=session, cache_dir=tmp_path)

        assert [a["assetId"] for a in search.assets("rook1", refresh=True)] == [1]


class TestTheCsvCatalogue:
    def test_the_byte_order_mark_does_not_hide_the_id_column(self, tmp_path):
        path = tmp_path / "export.csv"
        path.write_text(f"﻿{CATALOG_NUMBER},Common Name,Recordist,Date\n"
                        "104365511,American Crow,Jim,2018-06-14\n", encoding="utf-8")

        rows = read_catalogue(path)

        assert rows[0][CATALOG_NUMBER] == "104365511"
        assert MacaulaySource.normalize(rows[0])["recordist"] == "Jim"

    def test_a_missing_export_says_where_to_get_one(self, tmp_path):
        with pytest.raises(MacaulayError, match="search.macaulaylibrary.org"):
            read_catalogue(tmp_path / "nope.csv")

    def test_something_that_is_not_an_export_is_rejected(self, tmp_path):
        path = tmp_path / "wrong.csv"
        path.write_text("id,name\n1,nope\n", encoding="utf-8")

        with pytest.raises(MacaulayError, match="Macaulay export"):
            read_catalogue(path)
