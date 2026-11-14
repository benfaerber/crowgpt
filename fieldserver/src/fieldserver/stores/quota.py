"""How much an invited contributor may store.

Uploads arrive in chunks and no single request is large, so nothing bounded
the total: anyone enrolled could fill the disk sixteen megabytes at a time.
An allowance per contributor closes that for the people the project does not
know yet, the ones who came in on an invite (`contributors.access_request_id`,
revision 0040). The operator's own phones enroll with the fleet token, carry
no invite, and are never refused: a field recording that will not sync is the
one failure this server exists to prevent.

Counted from the rows, not the disk. `bytes` is what is stored now, so a WAV
that became FLAC counts at its FLAC size and the allowance is of recordings
kept, not of bytes ever sent.
"""

import os

from .contributors import FLEET_ROLES
from .db_base import Database

#: The allowance, in megabytes. About a hundred ten-minute recordings as FLAC.
DEFAULT_LIMIT_MB = 2048


class StorageQuota(Database):
    def __init__(self, db_path, limit_bytes: int | None = None):
        super().__init__(db_path)
        if limit_bytes is None:
            limit_bytes = int(os.environ.get("FIELD_INVITED_QUOTA_MB") or DEFAULT_LIMIT_MB) * 1024 * 1024
        self.limit_bytes = limit_bytes

    def applies_to(self, contributor: dict) -> bool:
        return (contributor.get("access_request_id") is not None
                and contributor.get("role") not in FLEET_ROLES)

    def used(self, contributor_id) -> int:
        """Bytes stored under this contributor's captures: recordings and
        spoken notes both, since either is a way to send bytes."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT (SELECT COALESCE(SUM(m.bytes), 0) FROM media m "
                "        JOIN captures c ON c.id = m.capture_id WHERE c.contributor_id = :who) "
                "     + (SELECT COALESCE(SUM(d.bytes), 0) FROM dictations d "
                "        JOIN captures c ON c.id = d.capture_id WHERE c.contributor_id = :who)",
                {"who": contributor_id}).fetchone()[0]

    def admits(self, contributor: dict, incoming: int) -> bool:
        if not self.applies_to(contributor):
            return True
        return self.used(contributor["id"]) + incoming <= self.limit_bytes
