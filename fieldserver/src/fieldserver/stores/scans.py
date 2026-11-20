"""Demo scans — a visitor's upload to the promo's Scan page, and its answer.

Queued by the public scan route, claimed by whichever worker handles its kind
(the photo worker for photos, the BirdNET worker for audio and video), and
completed with the result as JSON. Built like photo_ids, with three
differences that follow from the uploader being a stranger:

  - the file is deleted as soon as a worker finishes with it, done or failed;
  - the row is addressed by an unguessable `public_id`, never its integer id;
  - rows are pruned an hour after they were made;
  - the row carries the address it was uploaded from (revision 0043), which
    only the operator's routes return.

A visitor who ticks the page's "keep this file" box changes the first of
those: when the scan is done the file moves to `scan-contributions/` beside
the scan directory and a `scan_contributions` row records it with the result
(revision 0039). Unticked, nothing is kept. The contribution keeps the scan's
`public_id`, which is how its visitor reaches the labelling desk after this
table's row is pruned (stores/scan_desk.py).

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

#: What a scan is assumed to take before any has finished this hour: the
#: hosted box's time with the models not yet loaded, which is the slow case.
FIRST_GUESS_SECONDS = {"photo": 40, "sound": 20}

#: The most the server will hold of files visitors let it keep. The route
#: takes no token, so without a ceiling the disk belongs to whoever asks.
KEEP_BUDGET_BYTES = 5 * 1024 ** 3

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
        self.kept_dir = self.scan_dir.parent / "scan-contributions"

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

    def request(self, kind, storage_ref, latitude=None, longitude=None, keep=False,
                requester_ip=None):
        path = self.scan_dir / storage_ref
        try:
            self._check(kind, path, latitude, longitude)
        except ValueError:
            path.unlink(missing_ok=True)
            raise
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO demo_scans (public_id, kind, storage_ref, latitude, "
                "longitude, keep, requester_ip, state, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
                (secrets.token_urlsafe(18), kind, storage_ref, latitude, longitude, int(keep),
                 requester_ip, utc_now()))
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

    def typical_seconds(self, queue) -> float:
        """How long this queue's scans have been taking: the upper quartile
        of the hour's finished ones, so the page's countdown errs long."""
        kinds = QUEUES[queue]
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT claimed_at, finished_at FROM demo_scans WHERE state = 'done' "
                f"AND claimed_at IS NOT NULL AND kind IN ({','.join('?' * len(kinds))})", kinds).fetchall()
        took = sorted((datetime.fromisoformat(r["finished_at"]) - datetime.fromisoformat(r["claimed_at"]))
                      .total_seconds() for r in rows)
        return took[(len(took) * 3) // 4] if took else FIRST_GUESS_SECONDS[queue]

    def seconds_left(self, row, now=None) -> int:
        """A guess at the wait for a queued or running scan: everything ahead
        of it at the typical pace, then its own share, less what a running
        one has already spent. Zero means overdue, not finished."""
        typical = self.typical_seconds(queue_of(row["kind"]))
        mine = typical
        if row["state"] == "running" and row["claimed_at"]:
            spent = (now or datetime.now(timezone.utc)) - datetime.fromisoformat(row["claimed_at"])
            mine = max(typical - spent.total_seconds(), 0)
        return round(self.ahead_of(row) * typical + mine)

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

    def recent(self) -> list[dict]:
        """Every scan still inside its hour, newest first, for the operator."""
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT kind, state, keep, requester_ip, created_at FROM demo_scans "
                "ORDER BY id DESC")]

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
        visitor's upload outlives the job that read it, unless the visitor
        asked for it to be kept and the scan could read it."""
        with self._connect() as conn:
            before = conn.execute("SELECT * FROM demo_scans WHERE id = ?", (scan_id,)).fetchone()
        kept = bool(before) and state == "done" and bool(before["keep"]) and self._keep(dict(before), result)
        with self._connect() as conn:
            conn.execute(
                "UPDATE demo_scans SET state=?, result=?, error=?, finished_at=?, keep=?, "
                "storage_ref=NULL WHERE id = ?", (state, result, error, utc_now(), int(kept), scan_id))
            row = self._row(conn, scan_id)
        if before and not kept:
            self._discard(before["storage_ref"])
        return row

    def _keep(self, scan, result) -> bool:
        """Move a finished scan's file to the contributions and record it.
        False when the file is gone or the budget is spent, and then the
        caller deletes it like any other."""
        source = self.scan_dir / (scan["storage_ref"] or "")
        if not scan["storage_ref"] or not source.exists():
            return False
        size = source.stat().st_size
        if self.kept_bytes() + size > KEEP_BUDGET_BYTES:
            return False
        self.kept_dir.mkdir(parents=True, exist_ok=True)
        source.replace(self.kept_dir / scan["storage_ref"])
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO scan_contributions (public_id, kind, storage_ref, bytes, latitude, "
                "longitude, result, requester_ip, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scan["public_id"], scan["kind"], scan["storage_ref"], size, scan["latitude"],
                 scan["longitude"], result, scan["requester_ip"], utc_now()))
        return True

    # --- what visitors let the project keep -----------------------------------

    def kept_bytes(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM scan_contributions").fetchone()[0]

    def contributions(self):
        with self._connect() as conn:
            return [self._parsed(row) for row in conn.execute(
                "SELECT * FROM scan_contributions ORDER BY id")]

    def contribution_path(self, contribution) -> Path:
        return self.kept_dir / contribution["storage_ref"]

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
