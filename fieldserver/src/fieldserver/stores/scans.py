"""Demo scans — a visitor's upload to the promo's Scan page, and its answer.

Queued by the public scan route, claimed by whichever worker handles its kind
(the photo worker for photos, the BirdNET worker for audio and video), and
completed with the result as JSON. Built like photo_ids, with three
differences that follow from the uploader being a stranger:

  - the file is deleted as soon as a worker finishes with it, done or failed;
  - the row is addressed by an unguessable `public_id`, never its integer id;
  - rows are pruned an hour after they were made.

Nothing here is a capture. See revision 0038 for why it has its own table.
"""

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db_base import Database, utc_now

JOB_STATES = ("queued", "running", "done", "failed")

FORMATS = {
    "photo": ("jpg", "jpeg", "png", "webp"),
    "audio": ("wav", "mp3", "m4a", "aac", "ogg", "oga", "opus", "flac"),
    "video": ("mp4", "mov", "m4v", "webm", "mkv"),
}

#: Which worker answers which kinds. Audio and video are one queue: the
#: analyzer reads a video's audio track and nothing else of it.
QUEUES = {"photo": ("photo",), "sound": ("audio", "video")}

MAX_BYTES = {"photo": 15 * 1024 * 1024, "audio": 40 * 1024 * 1024, "video": 40 * 1024 * 1024}

#: How many uploads a queue may hold before the route says "busy". Workers are
#: sequential, so this is the longest wait the page promises anybody.
MAX_WAITING = 6

#: How much of a recording the sound worker analyses. The page states it
#: before the upload; the worker enforces it.
SOUND_SECONDS = 90

#: How long a result stays readable.
KEEP = timedelta(hours=1)

#: A worker that has not been heard from for this long is treated as absent.
ALIVE_WITHIN = timedelta(minutes=5)


def kind_of(filename: str) -> str | None:
    extension = Path(filename).suffix.lower().lstrip(".")
    for kind, extensions in FORMATS.items():
        if extension in extensions:
            return kind
    return None


def queue_of(kind: str) -> str:
    return next(name for name, kinds in QUEUES.items() if kind in kinds)


class ScanStore(Database):
    def __init__(self, db_path, scan_dir):
        super().__init__(db_path)
        self.scan_dir = Path(scan_dir)
        self.scan_dir.mkdir(parents=True, exist_ok=True)

    # --- the visitor half ---------------------------------------------------

    def allocate(self, filename: str):
        """Where an upload of this name should be written, and its kind.
        The route streams the file there, then calls `request`."""
        kind = kind_of(filename)
        if kind is None:
            raise ValueError("not a photo, audio or video format this page reads")
        extension = Path(filename).suffix.lower().lstrip(".")
        storage_ref = f"{secrets.token_hex(16)}.{extension}"
        return kind, storage_ref, self.scan_dir / storage_ref

    def request(self, kind, storage_ref, latitude=None, longitude=None):
        path = self.scan_dir / storage_ref
        try:
            self._check(kind, path, latitude, longitude)
        except ValueError:
            path.unlink(missing_ok=True)
            raise
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO demo_scans (public_id, kind, storage_ref, latitude, "
                "longitude, state, created_at) VALUES (?, ?, ?, ?, ?, 'queued', ?)",
                (secrets.token_urlsafe(18), kind, storage_ref, latitude, longitude, utc_now()))
            return self._row(conn, cur.lastrowid)

    @staticmethod
    def _check(kind, path, latitude, longitude):
        size = path.stat().st_size if path.exists() else 0
        if size == 0:
            raise ValueError("the file is empty")
        if size > MAX_BYTES[kind]:
            raise ValueError(f"{kind} files are limited to {MAX_BYTES[kind] // (1024 * 1024)} MB")
        if (latitude is None) != (longitude is None):
            raise ValueError("give both latitude and longitude, or neither")
        if latitude is not None and not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("latitude and longitude are out of range")

    def get_public(self, public_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM demo_scans WHERE public_id = ?",
                               (public_id,)).fetchone()
            return self._parsed(row) if row else None

    def waiting(self, queue) -> int:
        kinds = QUEUES[queue]
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM demo_scans WHERE state IN ('queued', 'running') "
                f"AND kind IN ({','.join('?' * len(kinds))})", kinds).fetchone()[0]

    def ahead_of(self, row) -> int:
        kinds = QUEUES[queue_of(row["kind"])]
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM demo_scans WHERE state IN ('queued', 'running') "
                f"AND id < ? AND kind IN ({','.join('?' * len(kinds))})",
                (row["id"], *kinds)).fetchone()[0]

    def prune(self, now=None) -> int:
        """Drop rows past their hour, and any file one still points at."""
        cutoff = ((now or datetime.now(timezone.utc)) - KEEP).isoformat()
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, storage_ref FROM demo_scans WHERE created_at < ?", (cutoff,))]
            conn.execute("DELETE FROM demo_scans WHERE created_at < ?", (cutoff,))
        for row in rows:
            self._discard(row["storage_ref"])
        return len(rows)

    # --- the worker half ----------------------------------------------------

    def path(self, row) -> Path:
        return self.scan_dir / row["storage_ref"]

    def claim_next(self, queue):
        kinds = QUEUES[queue]
        marks = ",".join("?" * len(kinds))
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE demo_scans SET state='running', claimed_at=?, attempts = attempts + 1 "
                f"WHERE id = (SELECT id FROM demo_scans WHERE state='queued' AND kind IN ({marks}) "
                "            ORDER BY id LIMIT 1) RETURNING id", (utc_now(), *kinds)).fetchone()
            return self._row(conn, row["id"]) if row else None

    def reclaim_running(self, queue, max_attempts=2):
        """Hand back what a stopped worker left running. Two attempts, not
        three: a stranger's file that kills a worker should not get to do it
        again and again."""
        kinds = QUEUES[queue]
        marks = ",".join("?" * len(kinds))
        requeued = abandoned = 0
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                f"SELECT id, attempts FROM demo_scans WHERE state='running' AND kind IN ({marks})",
                kinds)]
        for row in rows:
            if row["attempts"] < max_attempts:
                with self._connect() as conn:
                    conn.execute("UPDATE demo_scans SET state='queued', claimed_at=NULL "
                                 "WHERE id = ?", (row["id"],))
                requeued += 1
            else:
                self.fail(row["id"], "abandoned")
                abandoned += 1
        return requeued, abandoned

    def complete(self, scan_id, result: dict):
        return self._finish(scan_id, "done", result=json.dumps(result))

    def fail(self, scan_id, error):
        return self._finish(scan_id, "failed", error=str(error)[:500])

    def _finish(self, scan_id, state, result=None, error=None):
        """The answer, and the end of the file, together: nothing of a
        visitor's upload outlives the job that read it."""
        with self._connect() as conn:
            before = conn.execute("SELECT storage_ref FROM demo_scans WHERE id = ?",
                                  (scan_id,)).fetchone()
            conn.execute(
                "UPDATE demo_scans SET state=?, result=?, error=?, finished_at=?, "
                "storage_ref=NULL WHERE id = ?", (state, result, error, utc_now(), scan_id))
            row = self._row(conn, scan_id)
        if before:
            self._discard(before["storage_ref"])
        return row

    def _discard(self, storage_ref):
        if storage_ref:
            (self.scan_dir / storage_ref).unlink(missing_ok=True)

    # --- who is there to answer ---------------------------------------------

    def beat(self, queue):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO worker_heartbeats (name, seen_at) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET seen_at = excluded.seen_at", (queue, utc_now()))

    def alive(self, queue, now=None) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT seen_at FROM worker_heartbeats WHERE name = ?",
                               (queue,)).fetchone()
        if row is None:
            return False
        seen = datetime.fromisoformat(row["seen_at"])
        return (now or datetime.now(timezone.utc)) - seen <= ALIVE_WITHIN

    def _row(self, conn, scan_id):
        row = conn.execute("SELECT * FROM demo_scans WHERE id = ?", (scan_id,)).fetchone()
        return self._parsed(row) if row else None

    @staticmethod
    def _parsed(row) -> dict:
        parsed = dict(row)
        parsed["result"] = json.loads(parsed["result"]) if parsed["result"] else None
        return parsed
