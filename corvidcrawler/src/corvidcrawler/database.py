"""data/corvid.db: crawl jobs and the recordings they collected.

The `recordings` schema is a contract. crowgpt, the pipelines, the promo
credits and the dashboard's corpus panel open this file with bare sqlite3 and
share no code with the writer, so `slug`, `group_key` and `group_basis` are
resolved here, once, at write time — three readers each deriving them from
the free-text `species` column disagreed, and stored answers are the only way
to make readers that import nothing agree.

`detections` is created here too. It is filled by a detector, not by a crawl,
but the dashboard joins against it and a corpus with no scans yet should
answer with zeros rather than an error.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db_base import Database, utc_now
from .taxonomy import resolve

PENDING, RUNNING, DONE, ERROR, CANCELED = "pending", "running", "done", "error", "canceled"
TERMINAL = frozenset({DONE, ERROR, CANCELED})
ACTIVE = frozenset({PENDING, RUNNING})

#: How recently a job with no recorded pid must have been created to be spared.
GRACE = timedelta(minutes=15)

#: How a channel — one microphone in one setting — is identified, best first.
#: A recordist uploads many recordings of one bird on one day, so grouping per
#: recording lets that bird sit on both sides of a train/test split.
GROUP_LADDER = ("rec-day", "rec", "file")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    label TEXT,
    query TEXT NOT NULL,
    params TEXT NOT NULL,
    download INTEGER NOT NULL DEFAULT 0,
    max_recordings INTEGER NOT NULL,
    status TEXT NOT NULL,
    total_found INTEGER,
    fetched INTEGER NOT NULL DEFAULT 0,
    downloaded INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    source TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    species TEXT,
    call_type TEXT,
    country TEXT,
    location TEXT,
    lat REAL,
    lng REAL,
    license TEXT,
    quality TEXT,
    length TEXT,
    recordist TEXT,
    audio_url TEXT,
    page_url TEXT,
    file_path TEXT,
    downloaded INTEGER NOT NULL DEFAULT 0,
    raw TEXT,
    created_at TEXT NOT NULL,
    date TEXT,
    recordist_id TEXT,
    duration_seconds INTEGER,
    slug TEXT,
    core_type TEXT,
    content_sha256 TEXT,
    bytes INTEGER,
    group_key TEXT,
    group_basis TEXT,
    analyzed_at TEXT,
    UNIQUE (source, source_ref),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS recordings_source_idx ON recordings (source);
CREATE INDEX IF NOT EXISTS recordings_slug_idx ON recordings (slug);
CREATE INDEX IF NOT EXISTS recordings_group_idx ON recordings (group_key);
CREATE INDEX IF NOT EXISTS recordings_duration_idx ON recordings (duration_seconds);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    species TEXT NOT NULL,
    scientific_name TEXT,
    confidence REAL,
    candidate INTEGER NOT NULL DEFAULT 0,
    call_type TEXT,
    call_type_confidence REAL,
    location_filtered INTEGER NOT NULL DEFAULT 0,
    analyzer TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS detections_rec_idx ON detections (recording_id);
CREATE INDEX IF NOT EXISTS detections_species_idx ON detections (species);
"""


def _process_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


class CrawlStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- jobs ----------------------------------------------------------------

    def create_job(self, source, query, params, max_recordings, download, label=None) -> dict:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (source, label, query, params, download, max_recordings, "
                "                  status, created_at, pid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source, label, query, json.dumps(params, default=str), 1 if download else 0,
                 max_recordings, PENDING, utc_now(), os.getpid()),
            )
            return self._shape_job(
                conn.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def get_job(self, job_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._shape_job(row) if row else None

    def list_jobs(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [self._shape_job(r) for r in rows]

    def set_status(self, job_id, status) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))

    def update_progress(self, job_id, fetched, downloaded, total_found) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET fetched = ?, downloaded = ?, total_found = ? WHERE id = ?",
                         (fetched, downloaded, total_found, job_id))

    def finish_job(self, job_id, error=None) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                         (ERROR if error else DONE, error, utc_now(), job_id))

    def is_canceled(self, job_id) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is None or row["status"] == CANCELED

    def fail_abandoned(self) -> int:
        """Close out jobs whose owning process is gone — only that process's.

        A job records the pid that created it, so a second command in another
        shell does not mark a crawl that is still running as interrupted. A
        NULL pid predates the column and is closed only after a grace period.
        """
        mine = os.getpid()
        cutoff = (datetime.now(timezone.utc) - GRACE).isoformat()
        with self._connect() as conn:
            rows = conn.execute("SELECT id, pid, created_at FROM jobs WHERE status IN (?, ?)",
                                (PENDING, RUNNING)).fetchall()
            stale = [
                r["id"] for r in rows
                if r["pid"] != mine
                and not _process_alive(r["pid"])
                and (r["pid"] is not None or (r["created_at"] or "") < cutoff)
            ]
            conn.executemany(
                "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                [(ERROR, "interrupted — the process running this job exited", utc_now(), job_id)
                 for job_id in stale],
            )
        return len(stale)

    @staticmethod
    def _shape_job(row) -> dict:
        job = dict(row)
        job["download"] = bool(job["download"])
        job["params"] = json.loads(job["params"]) if job["params"] else {}
        return job

    # -- recordings ----------------------------------------------------------

    def upsert_recording(self, job_id, rec: dict) -> int:
        """Insert a recording, or refresh it in place. Returns 1 if new."""
        slug = resolve(rec.get("species")).slug
        basis, key = self._group_for(rec, slug)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM recordings WHERE source = ? AND source_ref = ?",
                (rec["source"], rec["source_ref"])).fetchone()
            conn.execute(
                """
                INSERT INTO recordings (
                    job_id, source, source_ref, species, call_type, country, location,
                    lat, lng, license, quality, length, duration_seconds, recordist,
                    recordist_id, date, audio_url, page_url, raw, slug, group_key,
                    group_basis, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, source_ref) DO UPDATE SET
                    job_id = excluded.job_id, species = excluded.species,
                    call_type = excluded.call_type, country = excluded.country,
                    location = excluded.location, lat = excluded.lat, lng = excluded.lng,
                    license = excluded.license, quality = excluded.quality,
                    length = excluded.length, duration_seconds = excluded.duration_seconds,
                    recordist = excluded.recordist, recordist_id = excluded.recordist_id,
                    date = excluded.date, audio_url = excluded.audio_url,
                    page_url = excluded.page_url, raw = excluded.raw, slug = excluded.slug,
                    group_key = excluded.group_key, group_basis = excluded.group_basis
                """,
                (job_id, rec["source"], rec["source_ref"], rec.get("species"),
                 rec.get("call_type"), rec.get("country"), rec.get("location"),
                 rec.get("lat"), rec.get("lng"), rec.get("license"), rec.get("quality"),
                 rec.get("length"), rec.get("duration_seconds"), rec.get("recordist"),
                 rec.get("recordist_id"), rec.get("date"), rec.get("audio_url"),
                 rec.get("page_url"), json.dumps(rec.get("raw"), default=str), slug, key,
                 basis, utc_now()),
            )
            return 0 if existing else 1

    @staticmethod
    def _group_for(rec: dict, slug) -> tuple[str, str]:
        namespace = slug or "unknown"
        who = (rec.get("recordist_id") or rec.get("recordist") or "").strip()
        when = (rec.get("date") or "").strip()[:10]
        if who and when:
            return "rec-day", f"{namespace}|rec-day|{who}|{when}"
        if who:
            return "rec", f"{namespace}|rec|{who}"
        return "file", f"{namespace}|file|{rec['source']}:{rec['source_ref']}"

    def mark_downloaded(self, source, source_ref, file_path) -> None:
        try:
            size = Path(file_path).stat().st_size
        except OSError:
            size = None
        with self._connect() as conn:
            conn.execute(
                "UPDATE recordings SET downloaded = 1, file_path = ?, bytes = ? "
                "WHERE source = ? AND source_ref = ?",
                (str(file_path), size, source, source_ref))

    def list_recordings(self, call_type=None, quality=None, downloaded=None, source=None,
                        species=None, min_seconds=None, limit=200) -> list[dict]:
        clauses, params = [], []
        for clause, value in (("call_type = ?", call_type), ("quality = ?", quality),
                              ("source = ?", source), ("duration_seconds >= ?", min_seconds)):
            if value is not None:
                clauses.append(clause)
                params.append(value)
        if downloaded is not None:
            clauses.append("downloaded = ?")
            params.append(1 if downloaded else 0)
        if species:
            clauses.append("(species LIKE ? OR slug = ?)")
            params += [f"%{species}%", species]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM recordings {where} ORDER BY id DESC LIMIT ?",
                                [*params, limit]).fetchall()
        return [self._shape_recording(r) for r in rows]

    def stats(self) -> dict:
        with self._connect() as conn:
            totals = conn.execute(
                "SELECT COUNT(*) AS n, SUM(downloaded) AS dl, SUM(duration_seconds) AS secs, "
                "       SUM(bytes) AS bytes, COUNT(DISTINCT group_key) AS channels "
                "FROM recordings").fetchone()
            by_source = [dict(r) for r in conn.execute(
                "SELECT source, COUNT(*) AS recordings, SUM(downloaded) AS downloaded, "
                "       SUM(duration_seconds) AS secs, SUM(bytes) AS bytes "
                "FROM recordings GROUP BY source ORDER BY recordings DESC")]
            by_slug = [dict(r) for r in conn.execute(
                "SELECT COALESCE(slug, 'unknown') AS slug, COUNT(*) AS recordings, "
                "       SUM(downloaded) AS downloaded, COUNT(DISTINCT group_key) AS channels, "
                "       SUM(duration_seconds) AS secs "
                "FROM recordings GROUP BY 1 ORDER BY recordings DESC LIMIT 20")]
            by_basis = {r["group_basis"] or "ungrouped": r["n"] for r in conn.execute(
                "SELECT group_basis, COUNT(*) AS n FROM recordings GROUP BY group_basis")}
        hours = lambda secs: round((secs or 0) / 3600, 2)  # noqa: E731
        return {
            "total": totals["n"] or 0,
            "downloaded": totals["dl"] or 0,
            "hours": hours(totals["secs"]),
            "gigabytes": round((totals["bytes"] or 0) / 1e9, 2),
            "channels": totals["channels"] or 0,
            "by_source": [{**r, "hours": hours(r.pop("secs")),
                           "gigabytes": round((r.pop("bytes") or 0) / 1e9, 2)} for r in by_source],
            "by_slug": [{**r, "hours": hours(r.pop("secs"))} for r in by_slug],
            "by_group_basis": by_basis,
        }

    @staticmethod
    def _shape_recording(row) -> dict:
        rec = dict(row)
        rec["downloaded"] = bool(rec["downloaded"])
        rec.pop("raw", None)
        return rec
