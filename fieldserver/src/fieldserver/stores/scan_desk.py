"""What a visitor says about the scan they let the project keep.

`scans.py` ends where a file is kept. This is everything after: the
contribution found again by the visitor's link, the labels and context they
attach to it from the labelling desk, and the operator's view of the pile.

The link is the credential. A contribution's `public_id` is 144 bits handed
to one browser, so holding it is what lets someone label that one recording;
it opens nothing else. Rows kept before revision 0041 have no public id and
no desk, and are still listed for the operator.

Nothing here is a capture or a label. A stranger's answers stay in
`scan_labels` and `scan_context` until an operator promotes the contribution
(core/promotion.py), which is the first time anybody on the project has
heard it.
"""

import json
from pathlib import Path

from .db_base import Database, utc_now

#: A recording is at most scans.SOUND_SECONDS of analysed audio; nobody marks
#: two hundred calls in ninety seconds, and the route takes no token.
MAX_LABELS = 200
MAX_CONTEXT = 600


class DeskFull(ValueError):
    pass


class ScanDeskStore(Database):
    def __init__(self, db_path, kept_dir):
        super().__init__(db_path)
        self.kept_dir = Path(kept_dir)

    # --- contributions -------------------------------------------------------

    def by_public_id(self, public_id):
        if not public_id:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM scan_contributions WHERE public_id = ?",
                               (public_id,)).fetchone()
            return self._parsed(row)

    def get(self, contribution_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM scan_contributions WHERE id = ?",
                               (contribution_id,)).fetchone()
            return self._parsed(row)

    def list_all(self):
        """Newest first, each with how much its visitor said about it."""
        with self._connect() as conn:
            return [self._parsed(row) for row in conn.execute(
                "SELECT c.*, "
                "(SELECT COUNT(*) FROM scan_labels l WHERE l.contribution_id = c.id) AS label_count, "
                "(SELECT COUNT(*) FROM scan_context x WHERE x.contribution_id = c.id) AS context_count "
                "FROM scan_contributions c ORDER BY c.id DESC")]

    def path(self, contribution) -> Path:
        return self.kept_dir / contribution["storage_ref"]

    def confirm_silent(self, contribution_id, silent=True):
        with self._connect() as conn:
            conn.execute("UPDATE scan_contributions SET silent_confirmed_at = ? WHERE id = ?",
                         (utc_now() if silent else None, contribution_id))
        return self.get(contribution_id)

    def mark_promoted(self, contribution_id, capture_id):
        with self._connect() as conn:
            conn.execute("UPDATE scan_contributions SET promoted_capture_id = ? WHERE id = ?",
                         (capture_id, contribution_id))
        return self.get(contribution_id)

    def delete(self, contribution_id) -> bool:
        """The file and everything said about it. A promoted contribution's
        capture is its own thing by then and is not touched."""
        contribution = self.get(contribution_id)
        if contribution is None:
            return False
        with self._connect() as conn:
            conn.execute("DELETE FROM scan_contributions WHERE id = ?", (contribution_id,))
        self.path(contribution).unlink(missing_ok=True)
        return True

    # --- labels ----------------------------------------------------------------

    def labels(self, contribution_id):
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM scan_labels WHERE contribution_id = ? ORDER BY start_sec, id",
                (contribution_id,))]

    def put_label(self, contribution_id, client_uuid, start_sec, end_sec, call_type,
                  from_detection=False, config_version=None):
        """Record a label, or replace the answer already stored for this uuid."""
        with self._connect() as conn:
            existing = self._label(conn, contribution_id, client_uuid)
            if existing:
                conn.execute(
                    "UPDATE scan_labels SET start_sec=?, end_sec=?, call_type=?, from_detection=?, "
                    "config_version=? WHERE id = ?",
                    (start_sec, end_sec, call_type, int(from_detection), config_version,
                     existing["id"]))
            else:
                self._room(conn, "scan_labels", contribution_id, MAX_LABELS)
                conn.execute(
                    "INSERT INTO scan_labels (contribution_id, client_uuid, start_sec, end_sec, "
                    "call_type, from_detection, config_version, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (contribution_id, client_uuid, start_sec, end_sec, call_type,
                     int(from_detection), config_version, utc_now()))
            # A label is evidence there was something to label.
            conn.execute("UPDATE scan_contributions SET silent_confirmed_at = NULL WHERE id = ?",
                         (contribution_id,))
            return self._label(conn, contribution_id, client_uuid)

    def set_caller(self, contribution_id, client_uuid, caller_role):
        with self._connect() as conn:
            conn.execute(
                "UPDATE scan_labels SET caller_role = ? WHERE contribution_id = ? AND client_uuid = ?",
                (caller_role, contribution_id, client_uuid))
            return self._label(conn, contribution_id, client_uuid)

    def delete_label(self, contribution_id, client_uuid) -> None:
        """The label and the context that described it: chips attached to an
        answer must not outlive it onto a different one."""
        with self._connect() as conn:
            conn.execute("DELETE FROM scan_context WHERE contribution_id = ? AND label_uuid = ?",
                         (contribution_id, client_uuid))
            conn.execute("DELETE FROM scan_labels WHERE contribution_id = ? AND client_uuid = ?",
                         (contribution_id, client_uuid))

    # --- context ---------------------------------------------------------------

    def context(self, contribution_id):
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM scan_context WHERE contribution_id = ? "
                "ORDER BY COALESCE(start_sec, -1), id", (contribution_id,))]

    def put_context(self, contribution_id, client_uuid, key, label_uuid=None,
                    start_sec=None, end_sec=None, config_version=None):
        with self._connect() as conn:
            existing = self._event(conn, contribution_id, client_uuid)
            if existing:
                return existing
            if label_uuid and not self._label(conn, contribution_id, label_uuid):
                raise LookupError("that label does not exist on this recording")
            self._room(conn, "scan_context", contribution_id, MAX_CONTEXT)
            conn.execute(
                "INSERT INTO scan_context (contribution_id, client_uuid, label_uuid, key, "
                "start_sec, end_sec, config_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (contribution_id, client_uuid, label_uuid, key, start_sec, end_sec,
                 config_version, utc_now()))
            return self._event(conn, contribution_id, client_uuid)

    def delete_context(self, contribution_id, client_uuid) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM scan_context WHERE contribution_id = ? AND client_uuid = ?",
                         (contribution_id, client_uuid))

    # --- helpers ---------------------------------------------------------------

    @staticmethod
    def _room(conn, table, contribution_id, limit):
        held = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE contribution_id = ?",
                            (contribution_id,)).fetchone()[0]
        if held >= limit:
            raise DeskFull("this recording has as many of those as it can hold")

    @staticmethod
    def _label(conn, contribution_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM scan_labels WHERE contribution_id = ? AND client_uuid = ?",
            (contribution_id, client_uuid)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _event(conn, contribution_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM scan_context WHERE contribution_id = ? AND client_uuid = ?",
            (contribution_id, client_uuid)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _parsed(row):
        if row is None:
            return None
        out = dict(row)
        out["result"] = json.loads(out["result"]) if out.get("result") else None
        return out
