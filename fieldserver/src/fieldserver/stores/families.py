"""Crow families — a named group of birds a contributor watches over time.

A family belongs to the *person* who created it, not the handset. Two recordists
in different towns both watching "the pair on the corner" mean different birds,
and silently merging those would corrupt exactly the long-term identity a family
exists to track — but one recordist carrying two phones means the same birds, and
splitting *those* corrupts it just as badly. Ownership sits at the contributor
because that is the boundary that matches how families are actually used.

Individual crows are deliberately not modelled yet. When they are, they hang off
a family — `crows(name, role, family_id)`, the shape the retired sighting app
used — so nothing here forecloses that.
"""

import sqlite3

from .db_base import Database, utc_now


class FamilyStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def add(self, contributor_id, device_id, name, color=None, notes=None,
            client_uuid=None):
        """Create a family, or adopt the pushed version of an existing one.

        Idempotent for the same reason captures are: the app creates families
        offline and pushes them when a sync is asked for, so a retry after a lost
        response must not leave two families with the same name. A re-push with
        changed fields is the phone editing its own family — the phone owns its
        families, so the server adopts name, colour and notes rather than
        returning the stale row (which is how "The Scholars, 3 so far" reaches
        the record after the family was first created blank in the field).
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("family name cannot be empty")

        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, contributor_id, client_uuid)
                if existing:
                    if (name, color, notes) != (existing["name"],
                                                existing["color"],
                                                existing["notes"]):
                        conn.execute(
                            "UPDATE families SET name = ?, color = ?, notes = ? "
                            "WHERE id = ?",
                            (name, color, notes, existing["id"]),
                        )
                        return self._row(conn, existing["id"])
                    return existing
            try:
                cur = conn.execute(
                    "INSERT INTO families (contributor_id, device_id, client_uuid, "
                    "name, color, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (contributor_id, device_id, client_uuid, name, color, notes,
                     utc_now()),
                )
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, contributor_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    def get(self, family_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()
            return dict(row) if row else None

    def for_contributor(self, contributor_id):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM families WHERE contributor_id = ? ORDER BY name",
                (contributor_id,))]

    def owned_by(self, family_id, contributor_id) -> bool:
        family = self.get(family_id)
        return bool(family) and family["contributor_id"] == contributor_id

    @staticmethod
    def _by_client_uuid(conn, contributor_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM families WHERE contributor_id = ? AND client_uuid = ?",
            (contributor_id, client_uuid)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _row(conn, family_id):
        return dict(conn.execute("SELECT * FROM families WHERE id = ?",
                                 (family_id,)).fetchone())
