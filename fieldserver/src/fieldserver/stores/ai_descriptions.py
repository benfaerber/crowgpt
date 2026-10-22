"""What a model wrote about a recording, or about one span of it.

Kept apart from `captures.notes` and `labels.notes`, which are the recordist's
own words. The separation is the point: a description a machine wrote is a guess
of the same standing as a detection, and anything proposing labels from it has to
weigh it below the person who was there. Merging the two into one field would
make that impossible to do, and impossible to notice.

Keyed on the span rather than on a label, so it outlives the answer. See
`0016_ai_descriptions` for why that is not an implementation detail.
"""

from .db_base import Database, utc_now

WHOLE_CAPTURE = (None, None)


class AiDescriptionStore(Database):

    def set(self, capture_id, description, start_sec=None, end_sec=None,
            model=None) -> dict:
        """Write a description, replacing any earlier one for the same span.

        Replace rather than accumulate, and for the opposite reason to
        `label_revisions`. A re-answered label is a person changing their mind,
        which is evidence about the vocabulary and worth keeping. A re-run model
        is the same reading done again, usually because the first was wrong or
        the prompt improved — history of that is noise, and it would double-count
        in anything summing descriptions per capture.
        """
        text = (description or "").strip()
        if not text:
            raise ValueError("a description needs text; use clear() to remove one")
        span = _span(start_sec, end_sec)
        with self._connect() as conn:
            existing = self._find(conn, capture_id, span)
            if existing:
                conn.execute(
                    "UPDATE ai_descriptions SET description = ?, model = ?, "
                    "written_at = ? WHERE id = ?",
                    (text, model, utc_now(), existing["id"]))
                return self._row(conn, existing["id"])
            cur = conn.execute(
                "INSERT INTO ai_descriptions "
                "(capture_id, start_sec, end_sec, description, model, written_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (capture_id, span[0], span[1], text, model, utc_now()))
            return self._row(conn, cur.lastrowid)

    def clear(self, capture_id, start_sec=None, end_sec=None) -> bool:
        """Remove one. Returns whether there was anything to remove.

        A separate verb because `set` refuses empty text: "" and "no description"
        are different states, and letting a blank string mean deletion is how a
        truncated write silently erases a paragraph.
        """
        span = _span(start_sec, end_sec)
        with self._connect() as conn:
            existing = self._find(conn, capture_id, span)
            if not existing:
                return False
            conn.execute("DELETE FROM ai_descriptions WHERE id = ?", (existing["id"],))
            return True

    def whole_capture(self, capture_id) -> dict | None:
        """The description of the recording as a whole, if one has been written."""
        with self._connect() as conn:
            return self._find(conn, capture_id, WHOLE_CAPTURE)

    def spans(self, capture_id) -> list[dict]:
        """Every per-span description, in time order. Excludes the whole-capture one."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM ai_descriptions WHERE capture_id = ? "
                "AND start_sec IS NOT NULL ORDER BY start_sec, end_sec",
                (capture_id,))]

    def for_capture(self, capture_id) -> list[dict]:
        """Everything written about this capture, whole-capture row first."""
        whole = self.whole_capture(capture_id)
        return ([whole] if whole else []) + self.spans(capture_id)

    @staticmethod
    def _find(conn, capture_id, span):
        start, end = span
        if start is None:
            row = conn.execute(
                "SELECT * FROM ai_descriptions WHERE capture_id = ? AND start_sec IS NULL",
                (capture_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM ai_descriptions WHERE capture_id = ? "
                "AND start_sec = ? AND end_sec = ?",
                (capture_id, start, end)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _row(conn, description_id):
        return dict(conn.execute("SELECT * FROM ai_descriptions WHERE id = ?",
                                 (description_id,)).fetchone())


def _span(start_sec, end_sec):
    """Both ends or neither.

    Half a span is the bug this catches: a caller passing only `start_sec` means
    something, but nothing here can tell whether it meant "from here on" or
    forgot the end, and storing it would put a row in the span index that no
    lookup by span could ever find again.
    """
    if start_sec is None and end_sec is None:
        return WHOLE_CAPTURE
    if start_sec is None or end_sec is None:
        raise ValueError("a span needs both start_sec and end_sec, or neither")
    start, end = float(start_sec), float(end_sec)
    if end <= start:
        raise ValueError(f"a span must end after it starts, got {start} to {end}")
    return start, end
