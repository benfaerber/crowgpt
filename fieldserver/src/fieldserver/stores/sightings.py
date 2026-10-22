"""Something seen near a recording but not during it.

The case this exists for: a crow gives an alarm bout, and five minutes later,
a block away, two hawks come into view. That is worth writing down — it is the
beginning of a real hypothesis — but it is *not* what `context_events` records.

`context_events` is ground truth: a human watched a dog walk through at 0:30 and
tagged the calls in that window. It is the axis the calls × context matrix is
built from. Putting an after-the-fact sighting in there would be circular in the
worst way: you infer "that was an alarm call" from the hawk, tag the hawk, and
the matrix then reports that alarm calls co-occur with hawks — true by
construction, and indistinguishable a year later from a result you actually
earned.

So this is a separate table, not a flag on that one. Separation by construction
rather than by discipline: a forgotten `WHERE witnessed = 1` in some future
query cannot quietly turn a guess back into evidence, because these rows are not
reachable from the context joins at all.

What makes a sighting honest is `offset_sec`. It is required and it is signed —
negative before the recording, positive after. A sighting with no offset is just
a context event with the honesty stripped out of it, so there is deliberately no
way to write one.

The vocabulary is the *same* one context events use. That is the point: it is
what lets you eventually ask "how often does an alarm bout precede a raptor
coming into view" and get an answer from data rather than from the tag you
already applied.
"""

import sqlite3

from .db_base import Database, utc_now


class SightingStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def add(self, capture_id, contributor_id, device_id, key, offset_sec,
            distance_m=None, notes=None, client_uuid=None):
        """Record a sighting, or return the existing one for `client_uuid`.

        Idempotent like everything else the phone pushes: the app writes offline
        and syncs on demand, so a retry after a lost response is routine rather
        than exceptional.
        """
        if offset_sec is None:
            raise ValueError("offset_sec is required — a sighting without a "
                             "time is a context event")
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, capture_id, client_uuid)
                if existing:
                    return existing
            try:
                cur = conn.execute(
                    "INSERT INTO sightings (capture_id, contributor_id, device_id, "
                    "client_uuid, key, offset_sec, distance_m, notes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (capture_id, contributor_id, device_id, client_uuid, key,
                     float(offset_sec),
                     None if distance_m is None else float(distance_m),
                     (notes or "").strip() or None, utc_now()),
                )
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, capture_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    def for_capture(self, capture_id) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM sightings WHERE capture_id = ? ORDER BY offset_sec",
                (capture_id,))]

    def get(self, sighting_id):
        with self._connect() as conn:
            return self._row(conn, sighting_id)

    def remove(self, sighting_id) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sightings WHERE id = ?", (sighting_id,))

    @staticmethod
    def _by_client_uuid(conn, capture_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM sightings WHERE capture_id = ? AND client_uuid = ?",
            (capture_id, client_uuid)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _row(conn, sighting_id):
        row = conn.execute("SELECT * FROM sightings WHERE id = ?",
                           (sighting_id,)).fetchone()
        return dict(row) if row else None
