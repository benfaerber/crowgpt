"""Devices — the things recordings are made *on*, and the credential that proves
which person made them.

A device no longer *is* a contributor; it belongs to one (see contributors.py).
That split is what lets someone carry two phones without splitting their corpus
in half, and lets a reinstall rejoin the person it belonged to rather than
becoming a stranger.

The bearer token is unchanged and still the only credential: minted once at
enrollment, stored hashed, long-lived because a phone in a field has no way to
re-authenticate.
"""

import hashlib
import secrets

from .db_base import Database, utc_now


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def register(self, contributor_id, label=None, platform=None, locale="en"):
        """Create a device for a contributor, return (public row, raw bearer
        token). The raw token is shown once; only its hash is stored."""
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO devices (device_uuid, contributor_id, label, token_hash, "
                "locale, platform, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (secrets.token_hex(16), contributor_id, (label or "").strip() or None,
                 _hash(token), locale, platform, utc_now()),
            )
            row = self._public(conn, cur.lastrowid)
        return row, token

    def authenticate(self, token, app_version=None, app_commit=None):
        """Return the device row for a bearer token, or None. Touches last_seen.

        A revoked device, or one whose owner is suspended, authenticates as
        nobody — the token is not deleted, so the row keeps its history and the
        captures it made stay attributed.

        `app_version`/`app_commit` come from headers the phone sets on every
        request. Recorded here rather than on a dedicated route because this is
        the one call every request already makes, so the build on the phone stays
        current without the client having to remember to report it.
        """
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT d.* FROM devices d "
                "LEFT JOIN contributors ct ON ct.id = d.contributor_id "
                "WHERE d.token_hash = ? AND d.revoked_at IS NULL "
                "AND COALESCE(ct.status, 'active') = 'active'",
                (_hash(token),),
            ).fetchone()
            if not row:
                return None
            seen = dict(row)
            # A client that sends nothing leaves the last known build in place —
            # "unknown" would erase a real answer with the absence of one.
            if app_version:
                conn.execute(
                    "UPDATE devices SET last_seen_at = ?, app_version = ?, app_commit = ? "
                    "WHERE id = ?",
                    (utc_now(), int(app_version), app_commit, row["id"]))
                seen["app_version"] = int(app_version)
                seen["app_commit"] = app_commit
            else:
                conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?",
                             (utc_now(), row["id"]))
            return seen

    def rotate_token(self, device_id):
        """Issue a new bearer token for an existing device, invalidating the old.

        Lets a re-login reuse one row instead of minting another. Signing in to
        the dashboard used to create a device every time, so the fleet list
        filled up with rows that had never recorded anything.
        """
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            conn.execute(
                "UPDATE devices SET token_hash = ?, revoked_at = NULL, last_seen_at = ? "
                "WHERE id = ?", (_hash(token), utc_now(), device_id))
            return self._public(conn, device_id), token

    def find(self, contributor_id, platform):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM devices WHERE contributor_id = ? AND platform = ? "
                "ORDER BY id LIMIT 1", (contributor_id, platform)).fetchone()
            return self._public(conn, row["id"]) if row else None

    def rename(self, device_id, label):
        with self._connect() as conn:
            conn.execute("UPDATE devices SET label = ? WHERE id = ?",
                         ((label or "").strip() or None, device_id))
            return self._public(conn, device_id)

    def revoke(self, device_id):
        """Retire a device without losing what it recorded."""
        with self._connect() as conn:
            conn.execute("UPDATE devices SET revoked_at = ? WHERE id = ?",
                         (utc_now(), device_id))
            return self._public(conn, device_id)

    def for_contributor(self, contributor_id):
        with self._connect() as conn:
            return [self._public(conn, r["id"]) for r in conn.execute(
                "SELECT id FROM devices WHERE contributor_id = ? ORDER BY created_at",
                (contributor_id,))]

    def get(self, device_id):
        with self._connect() as conn:
            return self._public(conn, device_id)

    @staticmethod
    def _public(conn, device_id):
        row = conn.execute(
            "SELECT d.id, d.device_uuid, d.contributor_id, d.label, "
            "d.locale, d.platform, d.created_at, d.last_seen_at, d.revoked_at, "
            "d.app_version, d.app_commit, "
            "ct.display_name, ct.role "
            "FROM devices d LEFT JOIN contributors ct ON ct.id = d.contributor_id "
            "WHERE d.id = ?", (device_id,)
        ).fetchone()
        if not row:
            return None
        row = dict(row)
        # Kept in the payload because clients and the dashboard read it, but it
        # is now *derived* from the owner's role rather than stored on the
        # device: authority belongs to the person, not the handset.
        row["is_operator"] = row.get("role") in ("operator", "admin")
        return row
