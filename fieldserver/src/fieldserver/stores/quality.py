"""Measured audio quality, one row per capture.

The worker writes it when it analyses; `tools/backfill_quality.py` writes it
for everything recorded before the table existed. The numbers come from
`analyzer/quality.py` and nowhere else — this store neither computes nor
interprets, it keeps.
"""

from .db_base import Database, utc_now

#: The measured columns, in one place. `upsert` takes a dict with exactly these
#: keys — the shape `analyzer.quality.measure()` returns — so the analyzer and
#: the table cannot drift apart without a KeyError saying so.
METRICS = (
    "band_snr_db",
    "noise_floor_low_dbfs",
    "noise_floor_band_dbfs",
    "peak_dbfs",
    "rms_dbfs",
    "clipped_samples",
    "clip_events",
)


class QualityStore(Database):
    def upsert(self, capture_id, media_id, metrics: dict) -> None:
        """Write the row, replacing any earlier measurement.

        Quality is a property of the audio, not of the analysis run, so there
        is nothing to keep history of: remeasuring the same file gives the
        same numbers, and remeasuring a different file supersedes them.
        """
        cols = ", ".join(METRICS)
        marks = ", ".join("?" for _ in METRICS)
        updates = ", ".join(f"{m} = excluded.{m}" for m in METRICS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO capture_quality (capture_id, media_id, {cols}, measured_at) "
                f"VALUES (?, ?, {marks}, ?) "
                f"ON CONFLICT(capture_id) DO UPDATE SET media_id = excluded.media_id, "
                f"{updates}, measured_at = excluded.measured_at",
                (capture_id, media_id, *(metrics[m] for m in METRICS), utc_now()))

    def for_capture(self, capture_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM capture_quality WHERE capture_id = ?",
                (capture_id,)).fetchone()
            return dict(row) if row else None

    def missing(self) -> list[int]:
        """Captures with complete audio and no quality row.

        The backfill's worklist, and the audit: after a full sweep this should
        be empty, and a capture that stays here is one the worker's write
        failed on — loudly in its log, silently everywhere else but here.
        """
        with self._connect() as conn:
            return [r["capture_id"] for r in conn.execute(
                "SELECT DISTINCT m.capture_id FROM media m "
                "LEFT JOIN capture_quality q ON q.capture_id = m.capture_id "
                "WHERE m.kind = 'audio' AND m.upload_state = 'complete' "
                "AND q.capture_id IS NULL ORDER BY m.capture_id")]
