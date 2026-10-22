"""Generations — chat with CrowGPT, one row per exchange.

A request for a call type, queued here, claimed by the generation worker
(crowgpt's venv, never this process), and completed with the wav's storage_ref.
The row is both the chat exchange and the job: the product is the artifact, so
splitting them would only create a state — done with no clip — that one table
makes unrepresentable.

Clips live in their own directory for the reason dictations do: `media/` means
"somebody's actual recording of birds", and a synthetic caw filed there is the
seeded-audio confusion manufactured in-house.
"""

import secrets
from pathlib import Path

from .db_base import Database, utc_now

# Restated rather than imported from another queue, as dictations records: two
# unrelated queues that happen to agree should not be coupled by an import.
JOB_STATES = ("queued", "running", "done", "failed")

#: What the chat's buttons may ask for — the call types `model-calltype` was
#: trained to condition on, minus "unknown", which is a bucket rather than a
#: request. The worker checks its checkpoint actually carries these at startup.
CALL_TYPES = ("alarm call", "begging", "call", "song")

#: The models the chat can address, and what each may be asked for. The
#: releases carry no call types in their manifests, so a request addressed to
#: one is a bare caw — call_type NULL. Names only, on purpose: the actual
#: recipe (checkpoint, decoder, sampling) lives in crowgpt's release files and
#: is the worker's to load; the server just refuses requests no model answers.
#: The worker asserts its recipe list matches this one at startup.
MODELS = {
    "model-calltype": CALL_TYPES,
    "crowgpt1": (),
    "crowgpt2": (),
    # The standing crowgpt3 candidate, in chat for the ear test only: 0075's
    # batch-32 retrain of 0074's conditioned long-context model. Begging and
    # call remain the weak buttons (label-bound); not the default, not a
    # release.
    "model-longctx-ct-b32": CALL_TYPES,
}
DEFAULT_MODEL = "model-calltype"

#: Highest seed handed out; small enough to read aloud off the dashboard.
SEED_SPAN = 1_000_000


class GenerationStore(Database):
    def __init__(self, db_path, clip_dir):
        super().__init__(db_path)
        self.clip_dir = Path(clip_dir)
        self.clip_dir.mkdir(parents=True, exist_ok=True)

    def request(self, call_type, model=DEFAULT_MODEL, contributor_id=None):
        if model not in MODELS:
            raise ValueError(f"model must be one of {', '.join(MODELS)}")
        allowed = MODELS[model]
        if allowed and call_type not in allowed:
            raise ValueError(
                f"{model} takes a call_type from: {', '.join(allowed)}")
        if not allowed and call_type is not None:
            raise ValueError(f"{model} does not take a call_type")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO generations (call_type, model, seed, requested_by, "
                "state, created_at) VALUES (?, ?, ?, ?, 'queued', ?)",
                (call_type, model, secrets.randbelow(SEED_SPAN), contributor_id,
                 utc_now()))
            return self._row(conn, cur.lastrowid)

    def get(self, generation_id):
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM generations WHERE id = ?",
                             (generation_id,)).fetchone()
            return dict(r) if r else None

    def recent(self, limit=50) -> list[dict]:
        """The newest exchanges in chat order — oldest of the window first."""
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM generations ORDER BY id DESC LIMIT ?", (limit,))]
        return list(reversed(rows))

    def path(self, row) -> Path:
        return self.clip_dir / row["storage_ref"]

    def forget(self) -> int:
        """Clear the whole conversation — rows and clips both.

        Everything here is synthetic and regenerable, so this is the one store
        where wholesale deletion needs no keep-flag ceremony. The rows go
        first, then the files: a crash between the two leaves orphaned wavs,
        which the 0028 migration already calls untidy rather than harmful. A
        generation running while the chat forgets finishes against a row that
        no longer exists — `complete` cleans up after that race itself.
        """
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT storage_ref FROM generations")]
            conn.execute("DELETE FROM generations")
        for row in rows:
            if row["storage_ref"]:
                self.path(row).unlink(missing_ok=True)
        return len(rows)

    # --- the worker half --------------------------------------------------

    def claim_next(self):
        """Atomically claim the oldest queued request — one statement, no window.

        `AnalysisStore.claim_next` records why the SELECT-then-UPDATE version
        was wrong.
        """
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE generations SET state='running', claimed_at=?, "
                "attempts = attempts + 1 "
                "WHERE id = (SELECT id FROM generations WHERE state='queued' "
                "            ORDER BY id LIMIT 1) "
                "RETURNING id", (utc_now(),)).fetchone()
            return self._row(conn, row["id"]) if row else None

    def reclaim_running(self, max_attempts=3):
        """Hand claimed jobs back, for a worker that is starting up.

        Claims have no expiry and one worker runs against this database, so
        startup is the moment a 'running' row is provably not running. The
        attempts guard stops a request that kills the worker being requeued
        forever by the restart it caused.
        """
        requeued = abandoned = 0
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM generations WHERE state = 'running'")]
        for row in rows:
            if row["attempts"] < max_attempts:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE generations SET state='queued', claimed_at=NULL "
                        "WHERE id = ?", (row["id"],))
                requeued += 1
            else:
                self.fail(row["id"], f"abandoned after {max_attempts} attempts")
                abandoned += 1
        return requeued, abandoned

    def allocate_ref(self) -> str:
        return f"{secrets.token_hex(16)}.wav"

    def complete(self, generation_id, storage_ref, duration_sec, model,
                 temperature, top_k):
        """The reply half and the job state in one transaction.

        A row forgotten mid-generation returns None and takes its wav with it,
        so the race with `forget` leaves nothing behind.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE generations SET state='done', storage_ref=?, "
                "duration_sec=?, model=?, temperature=?, top_k=?, finished_at=? "
                "WHERE id = ?",
                (storage_ref, float(duration_sec), model, float(temperature),
                 int(top_k), utc_now(), generation_id))
            row = self._row(conn, generation_id)
        if row is None:
            self.path({"storage_ref": storage_ref}).unlink(missing_ok=True)
        return row

    def fail(self, generation_id, error):
        with self._connect() as conn:
            conn.execute(
                "UPDATE generations SET state='failed', error=?, finished_at=? "
                "WHERE id = ?", (str(error)[:500], utc_now(), generation_id))
            return self._row(conn, generation_id)

    @staticmethod
    def _row(conn, generation_id):
        row = conn.execute("SELECT * FROM generations WHERE id = ?",
                           (generation_id,)).fetchone()
        return dict(row) if row else None
