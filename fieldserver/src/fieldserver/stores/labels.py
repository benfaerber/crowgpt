"""Human ground truth — the retrain fuel. A label is a call region a contributor
confirmed or drew on the waveform, tagged with a call_type from the active,
server-driven label set. export_manifest.py turns these into the manifest that
train_species.py already reads, so field labels enter training through the same
door as the archive corpus.
"""

import sqlite3

from .db_base import Database, utc_now


class LabelStore(Database):
    def __init__(self, db_path):
        super().__init__(db_path)

    def add(self, capture_id, media_id, contributor_id, device_id, species, call_type,
            start_sec=None, end_sec=None, label_source="human", notes=None,
            client_uuid=None, config_version=None, crow_id=None,
            caller_role=None):
        """Record a label, or update the existing one for this `client_uuid`.

        Replaying carries the latest answer, so a labeller who corrects a mistake
        before the push lands does not end up with both stored — both would enter
        the training manifest. What changed is that the answer being replaced is
        kept in `label_revisions` instead of being overwritten into nothing.

        The row's id does not move, which is what keeps a label's witnessed
        context attached to it across a refinement, and `config_version` moves
        with the answer: the column says which vocabulary *this* judgement was
        chosen from, so leaving it behind would attribute a new answer to the old
        list. The version the previous answer was chosen from goes to the
        revision, where it is the whole point — it is what makes "did the finer
        vocabulary change anybody's mind" a question the corpus can answer.

        `crow_id` is which bird the recordist watched make this call, and it is
        stamped with `attributed_at` at the moment it arrives. Experiment 0017
        showed the audio cannot recover a caller, so an attribution is only
        worth anything if it was made live — and a column that could not tell a
        live attribution from one filled in later would launder the second into
        the first. The timestamp is what keeps them apart.
        """
        with self._connect() as conn:
            if client_uuid:
                existing = self._by_client_uuid(conn, capture_id, client_uuid)
                if existing:
                    if (existing["call_type"], existing["species"]) != (call_type, species):
                        self._archive(conn, existing)
                        conn.execute(
                            "UPDATE labels SET call_type = ?, species = ?, "
                            "config_version = ? WHERE id = ?",
                            (call_type, species, config_version, existing["id"]))
                        return self._row(conn, existing["id"])
                    return existing
            try:
                cur = conn.execute(
                    "INSERT INTO labels (capture_id, media_id, contributor_id, device_id, "
                    "client_uuid, start_sec, end_sec, species, call_type, label_source, "
                    "notes, config_version, crow_id, caller_role, attributed_at, "
                    "created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (capture_id, media_id, contributor_id, device_id, client_uuid,
                     start_sec, end_sec, species, call_type, label_source, notes,
                     # Which vocabulary the labeller was looking at. Sent by the
                     # phone, because the phone caches the config and labels
                     # offline — this server's idea of "current" at that moment
                     # may be several versions ahead of what they were shown.
                     config_version, crow_id, caller_role,
                     utc_now() if (crow_id or caller_role) else None,
                     utc_now()),
                )
            except sqlite3.IntegrityError:
                return self._by_client_uuid(conn, capture_id, client_uuid)
            return self._row(conn, cur.lastrowid)

    def set_caller(self, label_id, caller_role=None, crow_id=None):
        """Set who called, stamping when the attribution was made.

        `attributed_at` moves to now whenever a caller is set and clears when
        both are removed, so the column always describes the answer currently in
        the row. Experiment 0017 is why it exists: an attribution made while the
        bird was calling and one recalled at a keyboard are worth different
        amounts, and nothing else distinguishes them.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE labels SET caller_role = ?, crow_id = ?, attributed_at = ? "
                "WHERE id = ?",
                (caller_role, crow_id,
                 utc_now() if (caller_role or crow_id) else None, label_id))
            return self._row(conn, label_id)

    @staticmethod
    def _archive(conn, existing):
        """File the answer a label is about to stop holding.

        Written before the UPDATE and in the same transaction, so there is no
        moment where the old answer has been dropped and not yet kept.
        """
        conn.execute(
            "INSERT INTO label_revisions "
            "(label_id, call_type, species, config_version, superseded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (existing["id"], existing["call_type"], existing["species"],
             existing["config_version"], utc_now()),
        )

    def delete(self, label_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM labels WHERE id = ?", (label_id,))

    def get(self, label_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM labels WHERE id = ?",
                               (label_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _by_client_uuid(conn, capture_id, client_uuid):
        row = conn.execute(
            "SELECT * FROM labels WHERE capture_id = ? AND client_uuid = ?",
            (capture_id, client_uuid)).fetchone()
        return dict(row) if row else None

    def for_capture(self, capture_id):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM labels WHERE capture_id = ? ORDER BY start_sec",
                (capture_id,))]

    @staticmethod
    def _row(conn, label_id):
        return dict(conn.execute("SELECT * FROM labels WHERE id = ?",
                                 (label_id,)).fetchone())
