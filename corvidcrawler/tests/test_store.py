"""The store resolves slug and channel grouping at write time, and its job
statuses are a vocabulary the poller recognises."""

import pytest

from corvidcrawler.database import ACTIVE, TERMINAL, CrawlStore


@pytest.fixture
def store(tmp_path):
    return CrawlStore(tmp_path / "corvid.db")


def job(store, **kwargs):
    return store.create_job(source="xeno_canto", query="gen:Corvus", params={},
                            max_recordings=10, download=False, **kwargs)["id"]


def recording(ref="XC1", **overrides):
    return {"source": "xeno_canto", "source_ref": ref, "species": "Northern Raven",
            "recordist": "A Recordist", "recordist_id": None, "date": "2020-05-01",
            "length": "1:30", "duration_seconds": 90, "raw": {}, **overrides}


class TestTheStatusVocabulary:
    def test_a_failed_job_is_terminal(self, store):
        job_id = job(store)
        store.finish_job(job_id, error="Xeno-canto returned HTTP 500")
        assert store.get_job(job_id)["status"] in TERMINAL

    def test_a_new_job_is_active(self, store):
        assert store.get_job(job(store))["status"] in ACTIVE

    def test_the_two_sets_do_not_overlap(self):
        assert not (TERMINAL & ACTIVE)


class TestWhatAWriteResolves:
    def test_the_archives_name_becomes_the_corpus_slug(self, store):
        store.upsert_recording(job(store), recording())

        assert store.list_recordings()[0]["slug"] == "common-raven"

    def test_a_recordist_and_a_day_make_a_channel(self, store):
        store.upsert_recording(job(store), recording())

        row = store.list_recordings()[0]
        assert row["group_basis"] == "rec-day"
        assert row["group_key"] == "common-raven|rec-day|A Recordist|2020-05-01"

    def test_a_stable_recordist_id_is_preferred_over_the_display_name(self, store):
        store.upsert_recording(job(store), recording(source="macaulay", recordist_id="USER1"))

        assert store.list_recordings()[0]["group_key"].endswith("|USER1|2020-05-01")

    def test_nothing_to_group_on_falls_back_to_the_file(self, store):
        store.upsert_recording(job(store), recording(recordist=None, date=None))

        row = store.list_recordings()[0]
        assert row["group_basis"] == "file"
        assert row["group_key"] == "common-raven|file|xeno_canto:XC1"

    def test_a_name_that_is_no_bird_gets_no_slug(self, store):
        store.upsert_recording(job(store), recording(species="Corvus sp."))

        row = store.list_recordings()[0]
        assert row["slug"] is None
        assert row["group_key"].startswith("unknown|")

    def test_an_update_refreshes_in_place(self, store):
        job_id = job(store)
        assert store.upsert_recording(job_id, recording()) == 1
        assert store.upsert_recording(job_id, recording(species="Rook")) == 0

        rows = store.list_recordings()
        assert len(rows) == 1 and rows[0]["slug"] == "rook"


class TestDownloads:
    def test_marking_downloaded_records_the_size(self, store, tmp_path):
        audio = tmp_path / "XC1.mp3"
        audio.write_bytes(b"x" * 1234)
        store.upsert_recording(job(store), recording())

        store.mark_downloaded("xeno_canto", "XC1", audio)

        row = store.list_recordings(downloaded=True)[0]
        assert row["bytes"] == 1234 and row["file_path"] == str(audio)

    def test_stats_sum_hours_and_channels(self, store):
        job_id = job(store)
        store.upsert_recording(job_id, recording(ref="XC1", duration_seconds=1800))
        store.upsert_recording(job_id, recording(ref="XC2", duration_seconds=1800, date="2020-05-02"))

        stats = store.stats()

        assert stats["hours"] == 1.0
        assert stats["channels"] == 2
        assert stats["by_slug"][0]["slug"] == "common-raven"


def test_the_detections_table_exists_for_readers_that_join_against_it(store):
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 0
