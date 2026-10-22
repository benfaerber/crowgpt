"""Free-text field notes written *after* the fact — the context half of the corpus.

Presets (`labels.call_type`) are what training consumes; they're deliberately a
closed vocabulary so they stay consistent and can be tapped one-handed in the
field. This is the other half: an unconstrained account of what the observer
actually saw, written back at the desk when there's time to type.

    "Edgar is alone, cawing and searching. I think he's calling the other four
     home."

Its job is not to train anything directly — at two contributors it can't. It's
for debugging a confusing prediction ("why did this get tagged alarm?") and for
discovering which situations recur often enough to *earn* a preset later. Since
the label set is server-driven, promoting a recurring phrase to a tag is a config
push, not an app release.

Kept separate from `captures.notes` (a quick note stamped at capture time, by the
recorder, on the spot): observations arrive later, there can be several, they're
editable as memory or interpretation changes, and they may be authored by someone
other than whoever held the phone.
"""

import sqlite3

from .db_base import Database, utc_now

SOURCES = ("typed", "voice")


class ObservationStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def add(self, capture_id, contributor_id, device_id, body, source="typed",
            locale=None, client_uuid=None):
        """Create an observation, or return the existing one for `client_uuid`.

        Same reasoning as captures and media: the app writes a description
        offline and pushes it when a sync is asked for, so a retry after a lost
        response is routine. Without a key that retry silently duplicates the
        note. Replaying also carries the latest body, since the author may have
        edited it between the failed attempt and the retry.
        """
        body = (body or "").strip()
        if not body:
            raise ValueError("observation body cannot be empty")
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}")
        now = utc_now()
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, capture_id, client_uuid)
                if existing:
                    if existing["body"] != body:
                        conn.execute(
                            "UPDATE observations SET body = ?, updated_at = ? WHERE id = ?",
                            (body, now, existing["id"]),
                        )
                        return self._row(conn, existing["id"])
                    return existing
            try:
                cur = conn.execute(
                    "INSERT INTO observations (capture_id, contributor_id, device_id, "
                    "client_uuid, body, source, locale, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (capture_id, contributor_id, device_id, client_uuid, body, source,
                     locale, now, now),
                )
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, capture_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    @staticmethod
    def _by_client_uuid(conn, capture_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM observations WHERE capture_id = ? AND client_uuid = ?",
            (capture_id, client_uuid)).fetchone()
        return dict(row) if row else None

    def get(self, observation_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM observations WHERE id = ?",
                               (observation_id,)).fetchone()
            return dict(row) if row else None

    def for_capture(self, capture_id):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM observations WHERE capture_id = ? ORDER BY created_at",
                (capture_id,))]

    def update_body(self, observation_id, body):
        body = (body or "").strip()
        if not body:
            raise ValueError("observation body cannot be empty")
        with self._connect() as conn:
            conn.execute(
                "UPDATE observations SET body = ?, updated_at = ? WHERE id = ?",
                (body, utc_now(), observation_id),
            )
            return self._row(conn, observation_id)

    @staticmethod
    def _row(conn, observation_id):
        return dict(conn.execute("SELECT * FROM observations WHERE id = ?",
                                 (observation_id,)).fetchone())
