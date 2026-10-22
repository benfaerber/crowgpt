"""A finished analysis job must be recognizably finished.

The client polls a job until it reaches a state it recognizes as terminal, so the
exact word matters. A failed job used to be written as 'error' where every client
looks for 'failed', which left a phone spinning forever on a clip that had blown
up in the worker.
"""

import sqlite3

import pytest

from fieldserver.core import schema
from fieldserver.stores.analysis import TERMINAL_JOB_STATES, AnalysisStore
from fieldserver.app import create_app


@pytest.fixture
def job(client, recordist):
    """A queued job against a capture with fully-uploaded audio."""
    capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                          headers=recordist.headers).get_json()
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"client_uuid": "med-1"},
                        headers=recordist.headers).get_json()
    client.put(f"/api/media/{media['id']}", data=b"xyz",
               headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
    return client.post(f"/api/captures/{capture['id']}/analyze",
                       headers=recordist.headers).get_json()


class TestJobLifecycle:
    def test_a_fresh_job_is_queued(self, job):
        assert job["state"] == "queued"

    def test_queued_is_not_terminal(self):
        assert "queued" not in TERMINAL_JOB_STATES

    def test_analysis_without_uploaded_audio_is_refused(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "cap-2"},
                              headers=recordist.headers).get_json()
        response = client.post(f"/api/captures/{capture['id']}/analyze",
                               headers=recordist.headers)
        assert response.status_code == 409


class TestClaiming:
    def test_claiming_marks_the_job_running(self, db_path, job):
        claimed = AnalysisStore(db_path).claim_next()
        assert claimed["id"] == job["id"]
        assert claimed["state"] == "running"

    def test_a_job_is_claimed_exactly_once(self, db_path, job):
        # Two workers polling the same queue must not both take it.
        store = AnalysisStore(db_path)
        assert store.claim_next() is not None
        assert store.claim_next() is None

    def test_nothing_queued_claims_nothing(self, db_path):
        assert AnalysisStore(db_path).claim_next() is None


class TestReclaimingAWorkersJobs:
    """A job a dead worker was holding has to come back.

    `claim_next` marks 'running' and only `complete` and `fail` move it again,
    both of which need the worker that just died. So a kill mid-analysis
    stranded the job and left its capture in 'analyzing' — non-terminal,
    counted by nothing, and invisible short of opening the database.
    """

    def test_a_job_left_running_is_queued_again(self, db_path, job):
        store = AnalysisStore(db_path)
        store.claim_next()

        requeued, abandoned = store.reclaim_running()

        assert requeued == [job["id"]]
        assert abandoned == []
        assert store.get_job(job["id"])["state"] == "queued"

    def test_and_can_then_be_claimed(self, db_path, job):
        store = AnalysisStore(db_path)
        store.claim_next()
        store.reclaim_running()
        assert store.claim_next()["id"] == job["id"]

    def test_a_queued_job_is_left_alone(self, db_path, job):
        # Reclaiming is about claims, not about the queue.
        store = AnalysisStore(db_path)
        assert store.reclaim_running() == ([], [])
        assert store.get_job(job["id"])["state"] == "queued"

    def test_a_finished_job_is_left_alone(self, db_path, job):
        store = AnalysisStore(db_path)
        store.claim_next()
        store.fail(job["id"], "ffmpeg exploded")

        store.reclaim_running()

        assert store.get_job(job["id"])["state"] == "failed"

    def test_a_job_that_keeps_killing_the_worker_is_given_up_on(self, db_path, job):
        # Otherwise it is requeued by the restart it caused, and the two of
        # them loop for as long as anyone lets them. Two attempts here so the
        # arithmetic is on the page rather than in the default.
        store = AnalysisStore(db_path)

        store.claim_next()
        assert store.reclaim_running(max_attempts=2) == ([job["id"]], [])

        store.claim_next()
        assert store.reclaim_running(max_attempts=2) == ([], [job["id"]])
        assert store.get_job(job["id"])["state"] == "failed"

    def test_and_hands_its_capture_back(self, db_path, job):
        # A given-up job has to reach a state somebody can see: 'analyzing' is
        # counted by nothing, so the capture would be lost a second way.
        store = AnalysisStore(db_path)
        store.claim_next()
        store.reclaim_running(max_attempts=1)

        with sqlite3.connect(db_path) as conn:
            status = conn.execute("SELECT status FROM captures WHERE id = ?",
                                  (job["capture_id"],)).fetchone()[0]
        assert status == "uploaded"


class TestFailedJobs:
    @pytest.fixture
    def failed(self, client, recordist, db_path, job):
        AnalysisStore(db_path).fail(job["id"], "ffmpeg exploded")
        return client.get(f"/api/jobs/{job['id']}", headers=recordist.headers).get_json()

    def test_it_reports_the_state_the_app_polls_for(self, failed):
        assert failed["state"] == "failed"

    def test_which_the_client_reads_as_terminal(self, failed):
        assert failed["state"] in TERMINAL_JOB_STATES

    def test_and_it_carries_the_reason(self, failed):
        assert "ffmpeg" in (failed["error"] or "")

    def test_and_the_capture_is_handed_back(self, failed, db_path, job):
        # Enqueueing moved the capture to 'analyzing', which is non-terminal
        # and counted by nothing — a failure that left it there made the
        # capture vanish from every needs-work number, silently and forever.
        with sqlite3.connect(db_path) as conn:
            status = conn.execute("SELECT status FROM captures WHERE id = ?",
                                  (job["capture_id"],)).fetchone()[0]
        assert status == "uploaded"

    def test_but_a_stale_failure_cannot_demote_an_analyzed_capture(
            self, db_path, job):
        # A re-run can finish before an old job's failure is recorded; the
        # late failure must not pull the capture back out of 'analyzed'.
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE captures SET status = 'analyzed' WHERE id = ?",
                         (job["capture_id"],))
        AnalysisStore(db_path).fail(job["id"], "a worker restarted mid-job")
        with sqlite3.connect(db_path) as conn:
            status = conn.execute("SELECT status FROM captures WHERE id = ?",
                                  (job["capture_id"],)).fetchone()[0]
        assert status == "analyzed"


class TestWhoMayReadAJob:
    """A job names a capture, so it is exactly as readable as that capture.

    It used to authenticate the device and stop there, which let any enrolled
    phone count up through the job ids and learn which captures and media
    existed on everybody else's account.
    """

    def test_its_own_contributor_may(self, client, recordist, job):
        assert client.get(f"/api/jobs/{job['id']}",
                          headers=recordist.headers).status_code == 200

    def test_another_contributor_may_not(self, client, stranger, job):
        assert client.get(f"/api/jobs/{job['id']}",
                          headers=stranger.headers).status_code == 403

    def test_an_operator_may(self, client, operator, job):
        # The same rule the capture itself follows, rather than a second one.
        assert client.get(f"/api/jobs/{job['id']}",
                          headers=operator.headers).status_code == 200

    def test_an_unauthenticated_caller_may_not(self, client, job):
        assert client.get(f"/api/jobs/{job['id']}").status_code == 401

    def test_a_job_that_does_not_exist_is_a_404(self, client, recordist, job):
        assert client.get("/api/jobs/9999",
                          headers=recordist.headers).status_code == 404


class TestLegacyErrorState:
    """Jobs written before the rename still say 'error', which no client stops on."""

    @pytest.fixture
    def migrated_state(self, tmp_path):
        # Stopped one revision short, so the legacy row can be written into a
        # database that has not yet had the rename applied. Reopening the store
        # used to do this on every launch; it is a migration now, so it is
        # tested as one.
        path = tmp_path / "legacy.db"
        schema.upgrade_to(path, "0002_retire_pre_contributor")
        with sqlite3.connect(path) as conn:
            conn.execute(
                "INSERT INTO analysis_jobs (capture_id, media_id, state, created_at) "
                "VALUES (1, 1, 'error', '2026-01-01')")
        schema.upgrade(path)
        with sqlite3.connect(path) as conn:
            return conn.execute("SELECT state FROM analysis_jobs").fetchone()[0]

    def test_it_is_migrated_to_failed(self, migrated_state):
        assert migrated_state == "failed"

    def test_so_no_stored_job_is_left_in_a_state_the_client_ignores(self, migrated_state):
        assert migrated_state in TERMINAL_JOB_STATES
