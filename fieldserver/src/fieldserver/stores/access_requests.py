"""Access requests — the queue between "may I try the app?" and an invite.

A request is open while it is pending or approved; a second submission from
the same address while one is open returns the existing row rather than a
duplicate, so a nervous requester cannot fill the queue. Declined rows stay,
so the same address asking again is visible as such.
"""

import secrets

from .db_base import Database, utc_now

OPEN = ("pending", "approved")


class AccessRequestStore(Database):
    def request(self, email, name=None, note=None, requester_ip=None) -> tuple[dict, bool]:
        """The row for this email, and whether this call created it."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM access_requests WHERE email = ? AND status IN (?, ?) "
                "ORDER BY id DESC LIMIT 1", (email, *OPEN)).fetchone()
            if existing:
                return self._row(conn, existing["id"]), False
            cur = conn.execute(
                "INSERT INTO access_requests (email, name, note, requester_ip, "
                "requested_at, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                (email, name, note, requester_ip, utc_now()))
            return self._row(conn, cur.lastrowid), True

    def list_all(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM access_requests ORDER BY "
                "CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END, "
                "id DESC")]

    def get(self, request_id) -> dict | None:
        with self._connect() as conn:
            return self._row(conn, request_id)

    def by_token(self, token) -> dict | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM access_requests WHERE invite_token = ?", (token,)).fetchone()
            return dict(row) if row else None

    def approve(self, request_id) -> dict | None:
        """Approve, minting the invite token once; approving again keeps it."""
        with self._connect() as conn:
            row = self._row(conn, request_id)
            if not row:
                return None
            token = row["invite_token"] or secrets.token_urlsafe(18)
            conn.execute(
                "UPDATE access_requests SET status = 'approved', decided_at = ?, "
                "invite_token = ? WHERE id = ?", (utc_now(), token, request_id))
            return self._row(conn, request_id)

    def decline(self, request_id) -> dict | None:
        with self._connect() as conn:
            if not self._row(conn, request_id):
                return None
            conn.execute(
                "UPDATE access_requests SET status = 'declined', decided_at = ? "
                "WHERE id = ?", (utc_now(), request_id))
            return self._row(conn, request_id)

    def mark_emailed(self, request_id, error=None) -> dict | None:
        with self._connect() as conn:
            if error:
                conn.execute("UPDATE access_requests SET email_error = ? WHERE id = ?",
                             (error, request_id))
            else:
                conn.execute(
                    "UPDATE access_requests SET emailed_at = ?, email_error = NULL "
                    "WHERE id = ?", (utc_now(), request_id))
            return self._row(conn, request_id)

    def record_download(self, token) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE access_requests SET downloads = downloads + 1, "
                "last_download_at = ? WHERE invite_token = ?", (utc_now(), token))

    @staticmethod
    def _row(conn, request_id):
        row = conn.execute("SELECT * FROM access_requests WHERE id = ?",
                           (request_id,)).fetchone()
        return dict(row) if row else None
