"""Photo identifications — an uploaded photo and the species the classifier named.

Queued here by the dashboard's Photo ID page, claimed by the photo worker
(analyzer/photo's venv, never this process), and completed with the ranked
species as JSON. The row is both the exchange and the job, as in generations.

Uploads live in their own directory: `media/` means somebody's field
recording, and a test photo for a classifier is not one.
"""

import json
import secrets
from pathlib import Path

from .db_base import Database, utc_now

JOB_STATES = ("queued", "running", "done", "failed")

#: What the classifier's image loader opens. HEIC is absent on purpose: Pillow
#: cannot read it without a plugin, and refusing at upload beats failing in
#: the worker.
FORMATS = ("jpg", "jpeg", "png", "webp")

#: A phone photo is a few megabytes. Kept under the server's 16 MB body cap so
#: an oversized photo gets this store's message, not a bare 413.
MAX_BYTES = 15 * 1024 * 1024


class PhotoIdStore(Database):
    def __init__(self, db_path, photo_dir):
        super().__init__(db_path)
        self.photo_dir = Path(photo_dir)
        self.photo_dir.mkdir(parents=True, exist_ok=True)

    def request(self, content: bytes, extension: str, original_name=None,
                latitude=None, longitude=None, contributor_id=None):
        extension = extension.lower().lstrip(".")
        if extension not in FORMATS:
            raise ValueError(f"photo must be one of: {', '.join(FORMATS)}")
        if not content:
            raise ValueError("the photo is empty")
        if len(content) > MAX_BYTES:
            raise ValueError(f"photo is over {MAX_BYTES // (1024 * 1024)} MB")
        if (latitude is None) != (longitude is None):
            raise ValueError("give both latitude and longitude, or neither")
        if latitude is not None and not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("latitude and longitude are out of range")
        storage_ref = f"{secrets.token_hex(16)}.{extension}"
        (self.photo_dir / storage_ref).write_bytes(content)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO photo_identifications (storage_ref, original_name, "
                "latitude, longitude, requested_by, state, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'queued', ?)",
                (storage_ref, original_name, latitude, longitude, contributor_id, utc_now()))
            return self._row(conn, cur.lastrowid)

    def get(self, identification_id):
        with self._connect() as conn:
            return self._row(conn, identification_id)

    def recent(self, limit=30) -> list[dict]:
        """Newest first: the page is a test bench, and the photo just
        uploaded is the one being looked at."""
        with self._connect() as conn:
            return [self._parsed(r) for r in conn.execute(
                "SELECT * FROM photo_identifications ORDER BY id DESC LIMIT ?", (limit,))]

    def path(self, row) -> Path:
        return self.photo_dir / row["storage_ref"]

    def forget(self) -> int:
        """Clear every upload and its result. Rows first, then files, so a
        crash between the two leaves stray photos, not rows pointing nowhere."""
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT storage_ref FROM photo_identifications")]
            conn.execute("DELETE FROM photo_identifications")
        for row in rows:
            self.path(row).unlink(missing_ok=True)
        return len(rows)

    # --- the worker half --------------------------------------------------

    def claim_next(self):
        """Atomically claim the oldest queued photo: one statement, no window."""
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE photo_identifications SET state='running', claimed_at=?, "
                "attempts = attempts + 1 "
                "WHERE id = (SELECT id FROM photo_identifications WHERE state='queued' "
                "            ORDER BY id LIMIT 1) "
                "RETURNING id", (utc_now(),)).fetchone()
            return self._row(conn, row["id"]) if row else None

    def reclaim_running(self, max_attempts=3):
        """Hand claimed jobs back when the worker starts: one worker runs
        against this database, so a 'running' row at startup is not running.
        The attempts guard stops a photo that kills the worker being requeued
        forever by the restart it caused."""
        requeued = abandoned = 0
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, attempts FROM photo_identifications WHERE state = 'running'")]
        for row in rows:
            if row["attempts"] < max_attempts:
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE photo_identifications SET state='queued', claimed_at=NULL "
                        "WHERE id = ?", (row["id"],))
                requeued += 1
            else:
                self.fail(row["id"], f"abandoned after {max_attempts} attempts")
                abandoned += 1
        return requeued, abandoned

    def complete(self, identification_id, result: dict):
        with self._connect() as conn:
            conn.execute(
                "UPDATE photo_identifications SET state='done', result=?, finished_at=? "
                "WHERE id = ?", (json.dumps(result), utc_now(), identification_id))
            return self._row(conn, identification_id)

    def fail(self, identification_id, error):
        with self._connect() as conn:
            conn.execute(
                "UPDATE photo_identifications SET state='failed', error=?, finished_at=? "
                "WHERE id = ?", (str(error)[:500], utc_now(), identification_id))
            return self._row(conn, identification_id)

    def _row(self, conn, identification_id):
        row = conn.execute("SELECT * FROM photo_identifications WHERE id = ?",
                           (identification_id,)).fetchone()
        return self._parsed(row) if row else None

    @staticmethod
    def _parsed(row) -> dict:
        parsed = dict(row)
        parsed["result"] = json.loads(parsed["result"]) if parsed["result"] else None
        return parsed
