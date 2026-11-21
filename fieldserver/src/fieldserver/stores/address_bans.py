"""Addresses the operator has banned from the public forms.

A ban is exact-match on the address the request arrived from. Banning also
declines whatever that address still has pending in the access queue, in the
same transaction, so the queue and the ban never disagree. Approved requests
are left alone: an invite somebody already holds is not taken back by a ban.
"""

from .db_base import Database, utc_now


class AddressBanStore(Database):
    def ban(self, ip) -> int:
        """Ban the address; how many pending requests that declined."""
        now = utc_now()
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO banned_addresses (ip, banned_at) VALUES (?, ?)",
                         (ip, now))
            return conn.execute(
                "UPDATE access_requests SET status = 'declined', decided_at = ? "
                "WHERE requester_ip = ? AND status = 'pending'", (now, ip)).rowcount

    def lift(self, ip) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM banned_addresses WHERE ip = ?", (ip,)).rowcount > 0

    def banned(self, ip) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM banned_addresses WHERE ip = ?",
                                (ip,)).fetchone() is not None

    def list_all(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT b.ip, b.banned_at, COUNT(a.id) AS requests "
                "FROM banned_addresses b LEFT JOIN access_requests a ON a.requester_ip = b.ip "
                "GROUP BY b.ip ORDER BY b.banned_at DESC")]
