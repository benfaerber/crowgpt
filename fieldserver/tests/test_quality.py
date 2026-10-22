"""Measured audio quality: one row per capture, overwritten rather than versioned.

The numbers themselves are the analyzer's business (`analyzer/quality.py`,
calibrated by experiments 0004/0008/0009) and are verified against the corpus,
not restated here. These tests are about the keeping: that a remeasurement
replaces rather than accumulates, that the audit query tells the truth, and
that the dashboard can see what was stored.
"""

import sqlite3

import pytest

from fieldserver.stores.quality import METRICS, QualityStore

MEASURED = {
    "band_snr_db": 21.7,
    "noise_floor_low_dbfs": -83.4,
    "noise_floor_band_dbfs": -110.2,
    "peak_dbfs": -26.7,
    "rms_dbfs": -66.1,
    "clipped_samples": 0,
    "clip_events": 0,
}

REMEASURED = {**MEASURED, "band_snr_db": 12.6, "clipped_samples": 195,
              "clip_events": 2}


@pytest.fixture
def capture(client, recordist):
    """A capture with fully-uploaded audio."""
    capture = client.post("/api/captures", json={"client_uuid": "cap-q1"},
                          headers=recordist.headers).get_json()
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"client_uuid": "med-q1"},
                        headers=recordist.headers).get_json()
    client.put(f"/api/media/{media['id']}", data=b"xyz",
               headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
    return {"capture": capture, "media": media}


@pytest.fixture
def store(db_path, app):
    return QualityStore(db_path)


class TestKeeping:
    def test_what_was_measured_is_what_is_kept(self, store, capture):
        store.upsert(capture["capture"]["id"], capture["media"]["id"], MEASURED)
        row = store.for_capture(capture["capture"]["id"])
        assert {k: row[k] for k in METRICS} == MEASURED

    def test_it_remembers_which_file_was_measured(self, store, capture):
        store.upsert(capture["capture"]["id"], capture["media"]["id"], MEASURED)
        row = store.for_capture(capture["capture"]["id"])
        assert row["media_id"] == capture["media"]["id"]
        assert row["measured_at"]

    def test_remeasuring_replaces_rather_than_accumulates(self, store, capture,
                                                          db_path):
        cid = capture["capture"]["id"]
        store.upsert(cid, capture["media"]["id"], MEASURED)
        store.upsert(cid, capture["media"]["id"], REMEASURED)
        assert store.for_capture(cid)["band_snr_db"] == 12.6
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM capture_quality "
                                 "WHERE capture_id = ?", (cid,)).fetchone()[0]
        assert count == 1

    def test_an_unmeasurable_snr_is_kept_as_null(self, store, capture):
        # A merged capture's silence gaps put digital zero in the quiet
        # percentile, and a ratio against zero is infinity — which is not a
        # number and not JSON. The analyzer hands back None for it, and None
        # has to survive the round trip as null rather than something.
        store.upsert(capture["capture"]["id"], capture["media"]["id"],
                     {**MEASURED, "band_snr_db": None})
        assert store.for_capture(capture["capture"]["id"])["band_snr_db"] is None

    def test_an_unmeasured_capture_has_no_row_and_no_error(self, store, capture):
        assert store.for_capture(capture["capture"]["id"]) is None

    def test_a_deleted_capture_takes_its_quality_with_it(self, store, capture,
                                                         db_path):
        cid = capture["capture"]["id"]
        store.upsert(cid, capture["media"]["id"], MEASURED)
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM captures WHERE id = ?", (cid,))
        assert store.for_capture(cid) is None


class TestTheAudit:
    def test_complete_audio_without_a_row_is_missing(self, store, capture):
        assert store.missing() == [capture["capture"]["id"]]

    def test_measuring_clears_it(self, store, capture):
        store.upsert(capture["capture"]["id"], capture["media"]["id"], MEASURED)
        assert store.missing() == []

    def test_a_capture_without_complete_audio_is_not_the_backfills_business(
            self, store, client, recordist):
        # No media at all, and media declared but never uploaded: neither can
        # be measured, so neither belongs on the worklist.
        bare = client.post("/api/captures", json={"client_uuid": "cap-q2"},
                           headers=recordist.headers).get_json()
        with_pending = client.post("/api/captures", json={"client_uuid": "cap-q3"},
                                   headers=recordist.headers).get_json()
        client.post(f"/api/captures/{with_pending['id']}/media",
                    json={"client_uuid": "med-q3"}, headers=recordist.headers)
        assert store.missing() == []


class TestTheDashboardSeesIt:
    def test_the_capture_detail_carries_the_row(self, store, capture, client,
                                                operator):
        cid = capture["capture"]["id"]
        store.upsert(cid, capture["media"]["id"], MEASURED)
        detail = client.get(f"/api/fleet/captures/{cid}",
                            headers=operator.headers).get_json()
        assert detail["quality"]["band_snr_db"] == 21.7

    def test_and_says_nothing_rather_than_something_when_unmeasured(
            self, capture, client, operator):
        detail = client.get(f"/api/fleet/captures/{capture['capture']['id']}",
                            headers=operator.headers).get_json()
        assert detail["quality"] is None

    def test_the_captures_list_carries_band_snr(self, store, capture, client,
                                                operator):
        cid = capture["capture"]["id"]
        store.upsert(cid, capture["media"]["id"], MEASURED)
        rows = client.get("/api/fleet/captures",
                          headers=operator.headers).get_json()
        row = next(r for r in rows if r["id"] == cid)
        assert row["band_snr_db"] == 21.7
        assert row["quality_measured_at"] is not None

    def test_with_null_for_the_unmeasured(self, capture, client, operator):
        rows = client.get("/api/fleet/captures",
                          headers=operator.headers).get_json()
        row = next(r for r in rows if r["id"] == capture["capture"]["id"])
        assert row["band_snr_db"] is None
        assert row["quality_measured_at"] is None

    def test_and_an_unmeasurable_snr_is_still_marked_measured(
            self, store, capture, client, operator):
        # The gauge tells "never measured" from "measured, and there was no
        # quiet signal to measure against" by exactly this pair.
        cid = capture["capture"]["id"]
        store.upsert(cid, capture["media"]["id"],
                     {**MEASURED, "band_snr_db": None})
        rows = client.get("/api/fleet/captures",
                          headers=operator.headers).get_json()
        row = next(r for r in rows if r["id"] == cid)
        assert row["band_snr_db"] is None
        assert row["quality_measured_at"] is not None
