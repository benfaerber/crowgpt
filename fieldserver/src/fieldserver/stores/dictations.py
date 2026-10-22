"""Dictations — the recordist talking, not the birds.

A spoken field note recorded against a capture, its machine transcript, and the
queue that produces one. Two tables and one directory, deliberately separate from
media in all three.

WHY NOT A MEDIA ROW. `MediaStore.complete_audio_for` does not filter by kind, it
only sorts — so every complete media row is a candidate for analysis, and among
non-audio kinds the newest wins. A dictation filed there would be handed to
BirdNET whenever a capture's own audio had not finished uploading. Separation by
construction rather than by a `WHERE` clause somebody has to remember.

WHY ITS OWN DIRECTORY. `instance/media/` means "somebody's actual recording of
birds", and anything that walks it — the compressor, the experiments, any future
export — can rely on that only if it is true. It also makes retention a fact about
a folder: a memo is speech, may name people and places, and syncs over no TLS with
one shared secret, so "delete every dictation older than N" needs to be one line
rather than a predicate spread across the corpus.

WHY THE TRANSCRIPT STAYS HERE. `observations.source` has had a 'voice' value since
the baseline and is the tempting destination. But `label-set` renders observations
under "WHAT THE RECORDIST WROTE (weigh this above the model)" with no hedge and
without selecting `source` at all — so a mis-heard name or head count would be
indistinguishable from testimony forever, and names and counts are precisely what
speech recognition gets wrong. The transcript is machine output until a human
reads it; `confirm()` is what promotes it, and that promotion is the whole
difference.
"""

import hashlib
import logging
import secrets
import sqlite3
from pathlib import Path

from .db_base import Database, utc_now
from .media import MEDIA_FORMAT

log = logging.getLogger(__name__)

# The job lifecycle, restated rather than imported from `analysis`. Two unrelated
# queues that happen to agree today should not be coupled by an import: a change
# to how bird analysis retries has no business changing how speech does.
JOB_STATES = ("queued", "running", "done", "failed")
TERMINAL_JOB_STATES = ("done", "failed")

#: States a job may already be in that make re-enqueueing a no-op.
#:
#: A completing PUT enqueues, and re-sending the final chunk is routine on a bad
#: link — so without this a flaky upload transcribes the same memo twice.
LIVE_JOB_STATES = ("queued", "running", "done")


class DictationStore(Database):
    def __init__(self, db_path, dictation_dir):
        super().__init__(db_path)
        self.dictation_dir = Path(dictation_dir)
        self.dictation_dir.mkdir(parents=True, exist_ok=True)

    # --- the upload half, shaped like MediaStore's -------------------------

    def create(self, capture_id, contributor_id=None, device_id=None,
               format="wav", sample_rate=16000, channels=1,
               duration_sec=None, recorded_at=None, locale=None,
               client_uuid=None):
        """Register a slot, or return the existing one for this `client_uuid`.

        Idempotent for the reason media is: a retried sync must resume the upload
        it already started rather than strand a half-written file behind a second
        slot. The returned row's `bytes` is the offset the client resumes from.

        16 kHz mono by default, which is not media's 48 kHz. It is what the
        transcriber wants (no resample), a third of the bytes, and it makes "this
        is not bird audio" a property of the file rather than of a column.
        """
        format = (format or "").strip().lower().lstrip(".")
        if not MEDIA_FORMAT.match(format):
            raise ValueError(
                "format must be a short plain extension like 'wav' or 'm4a'")
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, capture_id, client_uuid)
                if existing:
                    return existing
            storage_ref = f"{secrets.token_hex(16)}.{format}"
            try:
                cur = conn.execute(
                    "INSERT INTO dictations (capture_id, contributor_id, device_id, "
                    "client_uuid, storage, storage_ref, format, sample_rate, channels, "
                    "duration_sec, recorded_at, locale, upload_state, created_at) "
                    "VALUES (?, ?, ?, ?, 'local', ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (capture_id, contributor_id, device_id, client_uuid, storage_ref,
                     format, sample_rate, channels,
                     None if duration_sec is None else float(duration_sec),
                     recorded_at, locale, utc_now()))
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, capture_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    def append(self, dictation_id, data: bytes, offset: int) -> dict:
        """Write `data` at byte `offset` (resumable). Raw bytes, no transcode.

        Refuses to leave a hole, for the reason `MediaStore.append` gives: a
        sparse file's recorded length is whatever the client asked for, and
        `finalize` reads the whole of it back to hash it.
        """
        row = self.get(dictation_id)
        dest = self.path(row)
        stored = dest.stat().st_size if dest.exists() else 0
        if offset < 0 or offset > stored:
            raise ValueError(
                f"cannot write at byte {offset}: {stored} bytes have arrived, "
                "so that would leave a gap")
        with open(dest, "r+b" if dest.exists() else "wb") as fh:
            fh.seek(offset)
            fh.write(data)
        size = dest.stat().st_size
        with self._connect() as conn:
            conn.execute(
                "UPDATE dictations SET bytes = ?, upload_state = 'partial' WHERE id = ?",
                (size, dictation_id))
            return self._row(conn, dictation_id)

    def finalize(self, dictation_id) -> dict:
        """Hash the assembled file and mark it complete.

        No FLAC step, unlike media. Compression exists there because bird audio is
        the corpus and storage is the cost that grows; ninety seconds of speech at
        16 kHz mono is under 3 MB, and a verified-transcode path is one more
        failure mode for a saving nobody has measured wanting.
        """
        row = self.get(dictation_id)
        digest = hashlib.sha256(self.path(row).read_bytes()).hexdigest()
        with self._connect() as conn:
            conn.execute(
                "UPDATE dictations SET sha256 = ?, upload_state = 'complete', "
                "uploaded_at = ? WHERE id = ?", (digest, utc_now(), dictation_id))
            return self._row(conn, dictation_id)

    def path(self, row) -> Path:
        return self.dictation_dir / row["storage_ref"]

    def get(self, dictation_id):
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM dictations WHERE id = ?",
                             (dictation_id,)).fetchone()
            return dict(r) if r else None

    def for_capture(self, capture_id) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM dictations WHERE capture_id = ? ORDER BY id",
                (capture_id,))]

    @staticmethod
    def _by_client_uuid(conn, capture_id, client_uuid):
        r = conn.execute(
            "SELECT * FROM dictations WHERE capture_id = ? AND client_uuid = ?",
            (capture_id, client_uuid)).fetchone()
        return dict(r) if r else None

    # --- the transcript half ----------------------------------------------

    def confirm(self, dictation_id, contributor_id, observation_id):
        """A human has read the transcript, so it may now count as testimony.

        The stamp is the whole point of this table's middle tier. Until it is set
        the words are a machine's guess at what was said; after it, somebody has
        put their name to them and `observation_id` says where they went.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE dictations SET confirmed_at = ?, confirmed_by = ?, "
                "observation_id = ? WHERE id = ?",
                (utc_now(), contributor_id, observation_id, dictation_id))
            return self._row(conn, dictation_id)

    def purge_before(self, timestamp) -> int:
        """Delete memos recorded before `timestamp`, audio and all.

        Exists so the privacy note has a verb rather than an intention: this is
        speech, it may name people and places, and it lives on a server with no
        TLS. Nothing calls it on a schedule yet — that is a decision about
        retention, not a default to slip in.
        """
        removed = 0
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM dictations WHERE created_at < ?", (timestamp,))]
            for row in rows:
                self.path(row).unlink(missing_ok=True)
                conn.execute("DELETE FROM dictations WHERE id = ?", (row["id"],))
                removed += 1
        return removed

    # --- the queue half ---------------------------------------------------

    def enqueue(self, dictation_id, capture_id):
        """Queue a transcription, unless one is already queued, running or done.

        The guard is not tidiness. The completing PUT enqueues, and re-sending a
        final chunk is routine on a bad link, so without it one memo is
        transcribed twice. Only a `failed` job may be superseded, and only by the
        explicit re-transcribe route.
        """
        with self._connect() as conn:
            live = conn.execute(
                "SELECT * FROM dictation_jobs WHERE dictation_id = ? "
                f"AND state IN ({','.join('?' * len(LIVE_JOB_STATES))}) "
                "ORDER BY id DESC LIMIT 1",
                (dictation_id, *LIVE_JOB_STATES)).fetchone()
            if live:
                return dict(live)
            cur = conn.execute(
                "INSERT INTO dictation_jobs (dictation_id, capture_id, state, created_at) "
                "VALUES (?, ?, 'queued', ?)", (dictation_id, capture_id, utc_now()))
            return self._job(conn, cur.lastrowid)

    def get_job(self, job_id):
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM dictation_jobs WHERE id = ?",
                             (job_id,)).fetchone()
            return dict(r) if r else None

    def claim_next(self):
        """Worker: atomically claim the oldest queued job.

        One statement, so there is no window between finding the job and taking
        it. `AnalysisStore.claim_next` records why the SELECT-then-UPDATE version
        was wrong: `conn.total_changes` is cumulative for the connection, not the
        statement's rowcount.
        """
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE dictation_jobs SET state='running', claimed_at=?, "
                "attempts = attempts + 1 "
                "WHERE id = (SELECT id FROM dictation_jobs WHERE state='queued' "
                "            ORDER BY id LIMIT 1) "
                "RETURNING id", (utc_now(),)).fetchone()
            return self._job(conn, row["id"]) if row else None

    def reclaim_running(self, max_attempts=3):
        """Hand every claimed job back, for a worker that is starting up.

        Same reasoning as the analysis queue: a claim has no expiry, one worker
        runs against this database, and startup is the moment a 'running' job is
        provably not running. The attempts guard is what stops a job that kills
        the worker being requeued forever by the restart it caused.
        """
        requeued = abandoned = 0
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM dictation_jobs WHERE state = 'running'")]
        for row in rows:
            if row["attempts"] < max_attempts:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE dictation_jobs SET state='queued', claimed_at=NULL "
                        "WHERE id = ?", (row["id"],))
                requeued += 1
            else:
                self.fail(row["id"], f"abandoned after {max_attempts} attempts")
                abandoned += 1
        return requeued, abandoned

    def complete(self, job_id, dictation_id, text, model=None, language=None,
                 mean_logprob=None):
        """Write the transcript and finish the job, in one transaction.

        Deliberately not the analyze worker's shape, where the quality write is
        wrapped so it cannot fail the job — quality is a decoration there. Here
        the transcript *is* the job's product, so doing both together makes
        "done, with no transcript" a state that cannot be reached.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE dictations SET transcript = ?, transcript_model = ?, "
                "transcript_language = ?, mean_logprob = ?, transcribed_at = ? "
                "WHERE id = ?",
                (text, model, language,
                 None if mean_logprob is None else float(mean_logprob),
                 utc_now(), dictation_id))
            conn.execute(
                "UPDATE dictation_jobs SET state='done', finished_at=? WHERE id = ?",
                (utc_now(), job_id))
            return self._job(conn, job_id)

    def fail(self, job_id, error):
        """Terminal. No retry.

        DELIBERATELY DOES NOT TOUCH THE CAPTURE. `AnalysisStore.fail` ends by
        handing the capture back from 'analyzing' to 'uploaded', which is right
        there and wrong here: a failed transcription says nothing about whether
        the bird audio was analysed, and demoting the capture would make an
        analysed recording reappear in the dashboard's needs-work count. The
        copy-paste is the easiest mistake in this file.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE dictation_jobs SET state='failed', error=?, finished_at=? "
                "WHERE id = ?", (str(error)[:500], utc_now(), job_id))
            return self._job(conn, job_id)

    @staticmethod
    def _job(conn, job_id):
        return dict(conn.execute("SELECT * FROM dictation_jobs WHERE id = ?",
                                 (job_id,)).fetchone())

    @staticmethod
    def _row(conn, dictation_id):
        return dict(conn.execute("SELECT * FROM dictations WHERE id = ?",
                                 (dictation_id,)).fetchone())
