"""Analysis job queue + results — a SQLite table, not a broker. The mobile-facing
API enqueues a job; the separate inference worker (BirdNET venv) claims it, runs
the analysis, and writes results back. This one shared table is the entire
coupling between the light CRUD server and the heavy ML worker (no HTTP, no
re-upload). `detected_calls` rows are the exact shape of demo/server.py's calls[].
"""

import json

from .db_base import Database, utc_now

# The job lifecycle, named once. 'queued' and 'running' are in flight; the other
# two are terminal. The client polls until it sees a terminal state, so a state
# it doesn't recognize is a hang — which is exactly what an earlier spelling of
# 'failed' as 'error' caused.
JOB_STATES = ("queued", "running", "done", "failed")
TERMINAL_JOB_STATES = ("done", "failed")


class AnalysisStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def enqueue(self, capture_id, media_id):
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO analysis_jobs (capture_id, media_id, state, created_at) "
                "VALUES (?, ?, 'queued', ?)", (capture_id, media_id, utc_now()))
            return self._job(conn, cur.lastrowid)

    def get_job(self, job_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?",
                               (job_id,)).fetchone()
            return dict(row) if row else None

    def claim_next(self):
        """Worker: atomically claim the oldest queued job (running).

        One statement, so there is no window between finding the job and
        taking it. The previous SELECT-then-UPDATE checked for a lost race
        with `conn.total_changes` — which is cumulative for the connection,
        not the statement's rowcount, and only read zero correctly because
        nothing else had written on that connection yet.
        """
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE analysis_jobs SET state='running', claimed_at=?, "
                "attempts = attempts + 1 "
                "WHERE id = (SELECT id FROM analysis_jobs WHERE state='queued' "
                "            ORDER BY id LIMIT 1) "
                "RETURNING id", (utc_now(),)).fetchone()
            return self._job(conn, row["id"]) if row else None

    def reclaim_running(self, max_attempts=3):
        """Hand every claimed job back, for a worker that is starting up.

        A claim had no expiry: `claim_next` sets 'running' and only `complete`
        and `fail` ever move it again, both of which need the worker that is
        gone. So a worker killed mid-analysis left the job running forever and
        its capture in 'analyzing' — non-terminal, counted by nothing, and
        invisible short of opening the database.

        Startup is the moment this is safe rather than a guess. One worker runs
        against this database, so a job still marked 'running' while that
        worker boots cannot be running anywhere: there is nothing to race and
        no timeout to tune. A stuck job on a *live* worker still needs a
        restart to clear, which is honest — nothing here can tell a wedged
        BirdNET call from a slow one.

        The guard is what stops this becoming a crash loop. A job that kills
        the worker would otherwise be requeued by the restart it caused, so
        past `max_attempts` it is failed like any other and its capture handed
        back to 'uploaded', where the dashboard counts it again.

        Returns (requeued, abandoned).
        """
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, attempts FROM analysis_jobs WHERE state='running'")]
            requeued = [r["id"] for r in rows if r["attempts"] < max_attempts]
            abandoned = [r["id"] for r in rows if r["attempts"] >= max_attempts]
            if requeued:
                conn.execute(
                    "UPDATE analysis_jobs SET state='queued', claimed_at=NULL "
                    f"WHERE id IN ({','.join('?' * len(requeued))})", requeued)
        for job_id in abandoned:
            self.fail(job_id, f"abandoned after {max_attempts} attempts")
        return requeued, abandoned

    def complete(self, job_id, capture_id, duration, waveform, reliability,
                 calls, model_version):

        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO analysis_results (job_id, capture_id, duration, "
                "waveform_json, reliability_json, model_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job_id, capture_id, duration, json.dumps(waveform),
                 json.dumps(reliability), model_version, utc_now()))
            analysis_id = cur.lastrowid
            for c in calls:
                # NULL rather than "[]" when the head offered nothing: an empty
                # list means "it heard only one thing", and no column at all
                # meant "it could not have told you" — worth keeping apart.
                alternates = c.get("alternates")
                conn.execute(
                    "INSERT INTO detected_calls (analysis_id, start_sec, end_sec, "
                    "species, scientific_name, call_type, confidence, crow_conf, "
                    "candidate, alternates, multi_label) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (analysis_id, c.get("start"), c.get("end"), c.get("species"),
                     c.get("scientific_name"), c.get("call_type"),
                     c.get("confidence"), c.get("crow_conf"),
                     int(bool(c.get("candidate"))),
                     json.dumps(alternates) if alternates else None,
                     int(bool(c.get("multi_label")))))
            conn.execute(
                "UPDATE analysis_jobs SET state='done', finished_at=? WHERE id=?",
                (utc_now(), job_id))
            return analysis_id

    def fail(self, job_id, error):
        """Mark the job failed and hand its capture back.

        The capture was moved to 'analyzing' when the job was enqueued, and
        that state is non-terminal: nothing counts it, so a failure that left
        it there made the capture vanish from every needs-work number on the
        dashboard, permanently and silently. Guarded on the status so failing
        a stale job cannot demote a capture a later run has since analyzed.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET state='failed', error=?, finished_at=? WHERE id=?",
                (str(error)[:500], utc_now(), job_id))
            conn.execute(
                "UPDATE captures SET status='uploaded' WHERE status='analyzing' "
                "AND id = (SELECT capture_id FROM analysis_jobs WHERE id = ?)",
                (job_id,))

    def latest_calls_for_capture(self, capture_id):
        with self._connect() as conn:
            res = conn.execute(
                "SELECT * FROM analysis_results WHERE capture_id=? "
                "ORDER BY id DESC LIMIT 1", (capture_id,)).fetchone()
            if not res:
                return None
            calls = [dict(r) for r in conn.execute(
                "SELECT start_sec, end_sec, species, scientific_name, call_type, "
                "confidence, crow_conf, candidate, alternates, multi_label "
                "FROM detected_calls WHERE analysis_id=? "
                "ORDER BY start_sec", (res["id"],))]
            for call in calls:
                # Decoded here rather than by every caller: the column is an
                # implementation detail of this store, a list of call types is
                # not. Rows written before 0018 have NULL and become [].
                call["alternates"] = json.loads(call["alternates"] or "[]")
                call["multi_label"] = bool(call["multi_label"])
            return {
                "capture_id": capture_id,
                "duration": res["duration"],
                "waveform": json.loads(res["waveform_json"] or "[]"),
                "reliability": json.loads(res["reliability_json"] or "{}"),
                "model_version": res["model_version"],
                "calls": calls,
            }

    @staticmethod
    def _job(conn, job_id):
        return dict(conn.execute("SELECT * FROM analysis_jobs WHERE id=?",
                                 (job_id,)).fetchone())
