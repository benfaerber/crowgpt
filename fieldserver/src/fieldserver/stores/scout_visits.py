"""Scout visits — the boots that grade the 0084 prior.

Idempotent on client_uuid like every sync surface: a retried push lands once
and returns the row it landed as.
"""

import sqlite3

from .db_base import Database, utc_now


class ScoutVisitStore(Database):
    def record(self, client_uuid, kind, latitude, longitude, outcome,
               visited_at, note=None, contributor_id=None, device_id=None):
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO scout_visits (client_uuid, contributor_id, "
                    "device_id, kind, latitude, longitude, outcome, note, "
                    "visited_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (client_uuid, contributor_id, device_id, kind,
                     float(latitude), float(longitude), outcome, note,
                     visited_at, utc_now()))
                row_id = cur.lastrowid
            except sqlite3.IntegrityError:
                row_id = conn.execute(
                    "SELECT id FROM scout_visits WHERE client_uuid = ?",
                    (client_uuid,)).fetchone()["id"]
            return self._row(conn, row_id)

    def list(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM scout_visits ORDER BY visited_at")]

    @staticmethod
    def _row(conn, row_id):
        return dict(conn.execute("SELECT * FROM scout_visits WHERE id = ?",
                                 (row_id,)).fetchone())
