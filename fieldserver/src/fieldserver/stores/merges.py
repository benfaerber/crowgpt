"""Which captures were folded into which.

The phone does the merging: it joins the audio and uploads the result as an
ordinary capture, so nothing here ever sees a merge happen. What this records is
the consequence — that some captures on this server are the same birds as
another one, held twice.

Both copies are kept on purpose, for now. Deleting the parts would make the
merge irreversible, and the ★ Keep flag is the only thing separating real field
audio from seeded clips: a merge that dropped a kept capture would destroy the
scarcest thing in the corpus. Keeping them costs disk, which is cheap, and costs
correctness only where something counts captures without asking — which is what
[not_a_part] and `part_ids` exist to prevent.
"""

from .db_base import Database, utc_now


def not_a_part(column: str = "id") -> str:
    """SQL predicate: this capture has not been folded into another one.

    The one spelling of the exclusion every corpus-wide count needs. It used
    to be inlined wherever a query summed captures, which is exactly how the
    next such query forgets it — the merged copy holds identical audio, so a
    count without this shows one morning's work as two mornings'.
    """
    return f"{column} NOT IN (SELECT part_capture_id FROM capture_merges)"


class MergeStore(Database):
    def record(self, merged_capture_id, parts, contributor_id=None):
        """Note that `parts` were folded into `merged_capture_id`.

        `parts` is an ordered list of {capture_id, offset_ms} — the order and
        the offsets both matter, and neither is recomputable here. The offset
        depends on the silence the client inserted between segments, which is
        the client's choice and free to change between versions.

        Idempotent: sync retries, and a retry must not record the merge twice.
        A part already folded into this same capture is left alone; one folded
        into a *different* capture is a conflict the caller has to resolve,
        because it means two merges disagree about where a recording went.
        """
        now = utc_now()
        with self._connect() as conn:
            existing = {
                row["part_capture_id"]: row["merged_capture_id"]
                for row in conn.execute(
                    "SELECT part_capture_id, merged_capture_id FROM capture_merges "
                    "WHERE part_capture_id IN (%s)" %
                    ",".join("?" * len(parts)),
                    [p["capture_id"] for p in parts])
            }
            conflicts = [cid for cid, into in existing.items()
                         if into != merged_capture_id]
            if conflicts:
                raise ValueError(
                    f"captures {sorted(conflicts)} are already part of a different "
                    f"merge — un-merge those first")

            for position, part in enumerate(parts):
                if part["capture_id"] in existing:
                    continue
                conn.execute(
                    "INSERT INTO capture_merges (merged_capture_id, part_capture_id, "
                    "position, offset_ms, created_at, contributor_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (merged_capture_id, part["capture_id"], position,
                     int(part["offset_ms"]), now, contributor_id))
        return self.for_merged(merged_capture_id)

    def for_merged(self, merged_capture_id):
        """The parts of one merge, in the order they were joined."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM capture_merges WHERE merged_capture_id = ? "
                "ORDER BY position", (merged_capture_id,))]

    def part_ids(self):
        """Every capture that has been folded into another one.

        Anything summarising the corpus should exclude these, or it counts the
        same calls twice — the merged capture holds the identical audio. The
        rows stay so a merge can be undone; this is how they stay out of the
        arithmetic meanwhile.
        """
        with self._connect() as conn:
            return {r["part_capture_id"] for r in conn.execute(
                "SELECT part_capture_id FROM capture_merges")}
