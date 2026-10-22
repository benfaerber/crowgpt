"""The phone's own log, pushed up so it can be read without a cable.

Everything else in this database is evidence about crows. This is evidence
about the app, and it is treated differently for that reason: rows are capped,
pruned oldest-first, and nothing is allowed to depend on one being there.

The reason it exists at all: the field app is used in a park, and the failures
worth catching are the ones that happen there — a microphone that was revoked
in a pocket, a database handle that threw at startup, a sync that gave up on a
weak signal. `adb logcat` can see none of that, and it is wiped by the
reinstall that follows every fix.

Ingest is a batch, because the phone accumulates offline and pushes on demand
like everything else it owns, and idempotent per line: the phone marks a line
sent only once the server has confirmed it, so a dropped response means the
whole batch comes again.
"""

import json
import logging
import sqlite3

from .db_base import Database, utc_now

log = logging.getLogger(__name__)

LEVELS = ("debug", "info", "warn", "error")

# Per device. Enough to hold days of ordinary use and any single bad afternoon,
# small enough that a phone stuck in a crash loop cannot fill the disk with the
# same line — the newest are the ones that explain what is happening now.
KEEP_PER_DEVICE = 5000

# One line. Long enough for a stack trace's first frames, short enough that a
# runaway string cannot be pasted into the corpus.
MAX_MESSAGE = 4000
MAX_DETAIL = 16000


class LogStore(Database):
    def record(self, device_id, contributor_id, entries, app_version=None,
               app_commit=None) -> dict:
        """Take a batch, returning which client uuids are now stored.

        The uuids come back rather than a count, because the phone needs to know
        *which* lines to mark sent — a batch that half-lands otherwise repeats
        forever or loses the tail.

        Lines already present are reported as accepted. They are: the phone's
        copy is the one that mattered, and re-sending is the normal way a
        dropped response is recovered.
        """
        accepted, rejected = [], []
        with self._connect() as conn:
            for entry in entries:
                uuid = str(entry.get("client_uuid") or "").strip()
                if not uuid:
                    rejected.append({"client_uuid": None, "why": "client_uuid required"})
                    continue
                level = str(entry.get("level") or "info")
                if level not in LEVELS:
                    level = "info"
                try:
                    conn.execute(
                        "INSERT INTO device_logs (device_id, contributor_id, "
                        "client_uuid, at, level, tag, message, detail, app_version, "
                        "app_commit, received_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (device_id, contributor_id, uuid,
                         str(entry.get("at") or utc_now()), level,
                         str(entry.get("tag") or "app")[:64],
                         _clip(entry.get("message"), MAX_MESSAGE),
                         _detail(entry.get("detail")),
                         app_version, app_commit, utc_now()),
                    )
                except sqlite3.IntegrityError as refused:
                    # Only a uniqueness clash means "already have it". This
                    # used to catch every integrity error the same way, so a
                    # line refused by a foreign key was reported accepted —
                    # and an accepted line is one the phone stops resending,
                    # which turned a server-side refusal into a lost log line
                    # with both ends satisfied.
                    if "UNIQUE" in str(refused):
                        accepted.append(uuid)
                    else:
                        log.warning("log line %s refused: %s", uuid, refused)
                        rejected.append({"client_uuid": uuid, "why": str(refused)})
                    continue
                accepted.append(uuid)
            self._prune(conn, device_id)
        return {"accepted": accepted, "rejected": rejected}

    def recent(self, limit=200, level=None, device_id=None, tag=None,
               search=None) -> list[dict]:
        """Newest first, because the question is always "what just happened".

        `level` selects that level *and above*: asking for warnings and being
        shown warnings but no errors is a trap, and it is the filter anyone
        reaches for first when something is wrong.
        """
        where, params = [], []
        if level in LEVELS:
            where.append("level IN (%s)" % ",".join("?" * (len(LEVELS) - LEVELS.index(level))))
            params.extend(LEVELS[LEVELS.index(level):])
        if device_id is not None:
            where.append("l.device_id = ?")
            params.append(device_id)
        if tag:
            where.append("tag = ?")
            params.append(tag)
        if search:
            # Escaped, so searching for a literal underscore or percent finds
            # it rather than acting as a wildcard the operator never typed.
            needle = "%" + _like_escape(search) + "%"
            where.append(r"(message LIKE ? ESCAPE '\' OR detail LIKE ? ESCAPE '\')")
            params.extend([needle, needle])
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT l.*, d.label AS device_label, c.display_name "
                "FROM device_logs l "
                "JOIN devices d ON d.id = l.device_id "
                "JOIN contributors c ON c.id = l.contributor_id "
                f"{clause} ORDER BY l.at DESC, l.id DESC LIMIT ?",
                (*params, int(limit)))]

    def tags(self) -> list[str]:
        with self._connect() as conn:
            return [r["tag"] for r in conn.execute(
                "SELECT DISTINCT tag FROM device_logs ORDER BY tag")]

    def counts(self) -> dict:
        """Totals by level, for a badge that says whether it is worth looking."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT level, COUNT(*) n FROM device_logs GROUP BY level")
            return {r["level"]: r["n"] for r in rows}

    def clear(self, device_id=None) -> int:
        with self._connect() as conn:
            cur = (conn.execute("DELETE FROM device_logs WHERE device_id = ?",
                                (device_id,))
                   if device_id is not None
                   else conn.execute("DELETE FROM device_logs"))
            return cur.rowcount

    @staticmethod
    def _prune(conn, device_id) -> None:
        conn.execute(
            "DELETE FROM device_logs WHERE device_id = ? AND id NOT IN ("
            "  SELECT id FROM device_logs WHERE device_id = ? "
            "  ORDER BY id DESC LIMIT ?)",
            (device_id, device_id, KEEP_PER_DEVICE))


def _like_escape(text: str) -> str:
    return (str(text).replace("\\", "\\\\")
            .replace("%", r"\%").replace("_", r"\_"))


def _clip(value, limit: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _detail(value):
    """Detail is JSON on the wire and JSON in the column.

    Stored as text rather than parsed into columns because the useful fields
    differ per subsystem — a sync failure carries a status code and a capture
    uuid, a recorder failure carries a sample rate and a device name — and
    inventing a column per subsystem is how a log table becomes a schema
    migration every time something new goes wrong.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return _clip(value, MAX_DETAIL)
    try:
        return _clip(json.dumps(value, default=str), MAX_DETAIL)
    except (TypeError, ValueError):
        return _clip(repr(value), MAX_DETAIL)
