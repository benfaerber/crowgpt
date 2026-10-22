"""The registry and the shared protocol the runner relies on."""

import inspect

import pytest

from corvidcrawler.errors import SourceError
from corvidcrawler.sources import SOURCE_CLASSES, SOURCES, build_query_for, get_source, source_status

KEY = "test-key-not-a-real-secret-0000000000000"


def test_only_the_two_distributable_sources_exist():
    assert sorted(SOURCE_CLASSES) == ["macaulay", "xeno_canto"]
    assert sorted(s["id"] for s in SOURCES) == ["macaulay", "xeno_canto"]


def test_xeno_canto_is_not_ready_without_its_key():
    xc = next(s for s in source_status() if s["id"] == "xeno_canto")
    assert not xc["ready"] and "XENOCANTO_KEY" in xc["blocked_by"]


def test_xeno_canto_is_ready_once_the_key_is_set(monkeypatch):
    monkeypatch.setenv("XENOCANTO_KEY", KEY)
    xc = next(s for s in source_status() if s["id"] == "xeno_canto")
    assert xc["ready"] and xc["blocked_by"] is None


def test_macaulay_needs_nothing():
    assert next(s for s in source_status() if s["id"] == "macaulay")["ready"]


def test_every_source_declares_what_its_query_means():
    for row in SOURCES:
        assert row["query_is"] and row["docs"]


def test_an_unknown_source_is_a_source_error():
    with pytest.raises(SourceError):
        get_source("someday")


def _accepts_keyword(func, name):
    params = inspect.signature(func).parameters
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


@pytest.mark.parametrize("source_id", sorted(SOURCE_CLASSES))
def test_fetch_accepts_the_shared_keywords(source_id):
    for keyword in ("should_stop", "refresh"):
        assert _accepts_keyword(SOURCE_CLASSES[source_id].fetch, keyword)


@pytest.mark.parametrize("source_id", sorted(SOURCE_CLASSES))
def test_a_source_that_downloads_itself_accepts_on_bytes(source_id):
    download = getattr(SOURCE_CLASSES[source_id], "download", None)
    if download is not None:
        assert _accepts_keyword(download, "on_bytes")


class TestTheCrawlQuery:
    def test_xeno_canto_gets_a_search_expression(self):
        assert build_query_for("xeno_canto", {"gen": "Corvus", "sp": "corone"}) == "gen:Corvus sp:corone"

    def test_macaulay_gets_the_preset_slug(self):
        assert build_query_for("macaulay", {"gen": "Corvus", "sp": "frugilegus"}) == "rook"

    def test_macaulay_without_a_preset_asks_for_a_query(self):
        with pytest.raises(SourceError, match="--query"):
            build_query_for("macaulay", {"gen": "Corvus", "sp": "nobody"})
