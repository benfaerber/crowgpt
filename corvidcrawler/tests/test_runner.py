"""The job runner: one worker, the shared downloader, and the rows a dead
process leaves behind."""

from pathlib import Path

import pytest

from corvidcrawler import runner as runner_module
from corvidcrawler.database import CrawlStore
from corvidcrawler.runner import JobRunner, safe_stem


def record(ref="XC1", url="http://x/audio.mp3"):
    return {"source": "xeno_canto", "source_ref": ref, "species": "Rook", "audio_url": url,
            "raw": {}}


class FakeSource:
    def __init__(self, recs):
        self.recs = recs

    def count(self, query):
        return len(self.recs)

    def fetch(self, query, max_recordings, should_stop=None, **_):
        for rec in self.recs[:max_recordings]:
            if should_stop and should_stop():
                return
            yield rec


class SelfDownloadingSource(FakeSource):
    def __init__(self, recs):
        super().__init__(recs)
        self.fetched = []

    def download(self, rec, dest, on_bytes=None):
        self.fetched.append(rec["source_ref"])
        return True


class FakeDownloader:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def fetch(self, url, dest, on_bytes=None):
        self.calls.append(url)
        if on_bytes:
            on_bytes(50, 100)
        if self.ok:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"mp3")
        return self.ok


@pytest.fixture
def store(tmp_path):
    return CrawlStore(tmp_path / "corvid.db")


@pytest.fixture
def runner(store, tmp_path):
    return JobRunner(store, tmp_path / "audio")


def job(store, download=True):
    return store.create_job(source="xeno_canto", query="gen:Corvus", params={},
                            max_recordings=10, download=download)["id"]


def test_downloads_go_through_the_shared_downloader(store, runner, monkeypatch):
    monkeypatch.setattr(runner_module, "get_source", lambda _: FakeSource([record()]))
    runner.downloader = FakeDownloader()

    runner._run(job(store))

    assert runner.downloader.calls == ["http://x/audio.mp3"]
    rec = store.list_recordings()[0]
    assert rec["downloaded"] and Path(rec["file_path"]).exists()


def test_a_source_with_its_own_downloader_keeps_it(store, runner, monkeypatch):
    source = SelfDownloadingSource([record(ref="ML1")])
    monkeypatch.setattr(runner_module, "get_source", lambda _: source)
    runner.downloader = FakeDownloader()

    runner._run(job(store))

    assert source.fetched == ["ML1"] and runner.downloader.calls == []


def test_a_failed_download_is_not_marked_downloaded(store, runner, monkeypatch):
    monkeypatch.setattr(runner_module, "get_source", lambda _: FakeSource([record()]))
    runner.downloader = FakeDownloader(ok=False)

    runner._run(job(store))

    rec = store.list_recordings()[0]
    assert not rec["downloaded"] and rec["file_path"] is None
    assert store.get_job(1)["status"] == "done"


def test_a_job_canceled_while_queued_stays_canceled(store, runner, monkeypatch):
    def refuse(_):
        raise AssertionError("a canceled job reached its source")

    monkeypatch.setattr(runner_module, "get_source", refuse)
    job_id = job(store)
    store.set_status(job_id, "canceled")

    runner._run(job_id)

    assert store.get_job(job_id)["status"] == "canceled"


def test_jobs_queue_through_one_worker(store, runner, monkeypatch):
    monkeypatch.setattr(runner_module, "get_source", lambda _: FakeSource([record()]))
    runner.downloader = FakeDownloader()
    first, second = job(store), job(store)

    runner.start(first)
    runner.start(second)
    runner.queue.join()

    assert store.get_job(first)["status"] == "done"
    assert store.get_job(second)["status"] == "done"


def test_a_source_error_lands_on_the_job_row(store, runner, monkeypatch):
    from corvidcrawler.errors import SourceError

    class Broken(FakeSource):
        def count(self, query):
            raise SourceError("no key")

    monkeypatch.setattr(runner_module, "get_source", lambda _: Broken([]))
    job_id = job(store)

    runner._run(job_id)

    assert store.get_job(job_id) == {**store.get_job(job_id), "status": "error", "error": "no key"}


def test_nothing_is_reported_in_flight_once_the_file_is_done(store, runner, monkeypatch):
    monkeypatch.setattr(runner_module, "get_source", lambda _: FakeSource([record()]))
    runner.downloader = FakeDownloader()

    runner._run(job(store))

    assert runner.current is None


def test_a_hostile_source_ref_cannot_leave_the_audio_dir(tmp_path):
    dest = tmp_path / "audio" / f"{safe_stem('../../etc/passwd')}.mp3"

    assert "/" not in safe_stem("../../etc/passwd")
    assert dest.resolve().is_relative_to((tmp_path / "audio").resolve())


def orphan(store, job_id):
    with store._connect() as conn:
        conn.execute("UPDATE jobs SET pid = 0 WHERE id = ?", (job_id,))


def test_a_dead_process_s_jobs_are_closed_at_startup(store):
    stranded, running = job(store), job(store)
    store.set_status(running, "running")
    for job_id in (stranded, running):
        orphan(store, job_id)

    assert store.fail_abandoned() == 2
    assert "interrupted" in store.get_job(stranded)["error"]


def test_a_live_process_s_running_job_is_left_alone(store):
    running = job(store)
    store.set_status(running, "running")

    assert store.fail_abandoned() == 0
    assert store.get_job(running)["status"] == "running"


def test_a_fresh_job_with_no_pid_is_spared(store):
    stranded = job(store)
    with store._connect() as conn:
        conn.execute("UPDATE jobs SET pid = NULL WHERE id = ?", (stranded,))

    assert store.fail_abandoned() == 0
