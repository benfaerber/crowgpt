"""What was happening in the world when the bird called.

The other half of the semantics problem. `labels` records what the crow *said*
— a class an acoustic model can learn. This records what a human *witnessed*: a
dog walked through, someone put food down, a hawk went over. Neither is
interesting alone. A corpus of calls with no context is a phonetics dataset; a
corpus of contexts with no calls is a diary. Paired, they are the only thing
that can turn "this is an alarm call" into "this is what a crow says about a
dog".

Deliberately its own table rather than a row in `labels`. export_manifest.py
builds the training manifest from `labels.call_type`, so a "dog visible" row
there would become a class the model tries to predict from audio — which is
both wrong and silently wrong.

Context hangs off a **label**, not a capture. That distinction is the whole
value: a two-minute recording might have a dog appear at 0:30 and leave at 0:50,
so the alarm calls in that window are about the dog and the song at 1:40 is not.
Tagging the capture would credit every situation to every call in it — a
recording with one dog and one song would report that crows sing at dogs, which
is precisely the false conclusion this exists to avoid.

The vocabulary is server-defined for the same reason the call labels are: which
situations recur often enough to earn a tag is something you discover from the
free-text observations, and promoting one should be a config push rather than an
app release.
"""

import sqlite3

from .db_base import Database, utc_now


class ContextStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def add(self, capture_id, contributor_id, device_id, key, label_id=None,
            start_sec=None, end_sec=None, notes=None, client_uuid=None, config_version=None):
        """Record a witnessed event, or return the existing one for `client_uuid`.

        Idempotent like everything else the app pushes: context is tagged in the
        field and syncs later, so a retried push is routine.
        """
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, capture_id, client_uuid)
                if existing:
                    return existing
            try:
                cur = conn.execute(
                    "INSERT INTO context_events (capture_id, label_id, contributor_id, "
                    "device_id, client_uuid, key, start_sec, end_sec, notes, "
                    "config_version, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (capture_id, label_id, contributor_id, device_id, client_uuid, key,
                     start_sec, end_sec, notes, config_version, utc_now()),
                )
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, capture_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    def for_capture(self, capture_id):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM context_events WHERE capture_id = ? "
                "ORDER BY COALESCE(start_sec, -1), id", (capture_id,))]

    def get(self, event_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM context_events WHERE id = ?",
                               (event_id,)).fetchone()
            return dict(row) if row else None

    def delete(self, event_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM context_events WHERE id = ?", (event_id,))

    @staticmethod
    def _by_client_uuid(conn, capture_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM context_events WHERE capture_id = ? AND client_uuid = ?",
            (capture_id, client_uuid)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _row(conn, event_id):
        return dict(conn.execute("SELECT * FROM context_events WHERE id = ?",
                                 (event_id,)).fetchone())
