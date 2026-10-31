"""The promo page's shelf of generated calls.

A visitor to crowgpt.org presses "alarm call" and should hear one now, on a
two-core box that takes half a minute a bout. So the worker generates ahead:
each item on a fixed menu keeps a few finished clips waiting (`generations`
rows with source 'demo' and no `served_at`), a press takes one off the shelf,
and the gap is queued for refill at priority 0 — behind anybody actually
waiting. Only when the shelf for an item is bare does a press become a live
job, at priority 1, and the page polls for it.

The menu is fixed here, not sent by the visitor: a public route with free
parameters is an invitation to spend the box's CPU in arbitrary ways. Every
seed is drawn server-side, and a clip stays fetchable for a day after it is
served so a visitor can replay what they heard and quote the seed.

Same table as Crow Chat on purpose: the worker's queue is one queue, and a
clip is a clip. `GenerationStore.recent` filters the chat's view to its own
rows; everything here filters to 'demo'.
"""

from pathlib import Path

from .db_base import Database, utc_now
from .generations import GenerationStore


class MenuItem:
    def __init__(self, key, label, model, call_type):
        self.key = key
        self.label = label
        self.model = model
        self.call_type = call_type

    def describe(self) -> dict:
        return {"key": self.key, "label": self.label, "model": self.model,
                "call_type": self.call_type}


#: What the page may ask for. The conditioned model answers the four call
#: types it was trained on; CrowGPT2, the release the page plays beside a real
#: crow, answers a bare caw. Keys are what ride in the URL.
MENU = {item.key: item for item in (
    MenuItem("alarm-call", "Alarm call", "model-calltype", "alarm call"),
    MenuItem("call", "Call", "model-calltype", "call"),
    MenuItem("begging", "Begging", "model-calltype", "begging"),
    MenuItem("song", "Song", "model-calltype", "song"),
    MenuItem("caw", "A caw from CrowGPT2", "crowgpt2", None),
)}

#: Finished clips kept waiting per item. Two is a press and a follow-up press
#: answered at once while the refill for the first is still generating.
SHELF_DEPTH = 2

#: Live jobs the demo may have open at once. The worker is sequential, so this
#: is the longest wait the page will promise anybody, in bouts.
MAX_WAITING = 8

#: A served clip stays fetchable this long, then its row and wav go.
KEEP_SERVED_HOURS = 24


class DemoPool(Database):
    def __init__(self, generations: GenerationStore):
        super().__init__(generations.db_path)
        self.generations = generations

    # --- what the page asks ----------------------------------------------

    def take(self, key: str) -> dict:
        """Hand a visitor a clip for this item, finished if one is waiting.

        Returns the row, marked served. A finished row from the shelf is the
        common case; failing that, the oldest refill already in flight for the
        item is promoted to priority 1 and handed over, so a press never
        queues a job behind one that would answer the same question. Only an
        item with nothing in flight queues a new job. Call `restock` after.
        """
        item = MENU[key]
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE generations SET served_at = ? WHERE id = ("
                "  SELECT id FROM generations WHERE source = 'demo' "
                "  AND served_at IS NULL AND model = ? AND call_type IS ? "
                "  AND state = 'done' ORDER BY id LIMIT 1) RETURNING id",
                (now, item.model, item.call_type)).fetchone()
            if row is None:
                row = conn.execute(
                    "UPDATE generations SET served_at = ?, priority = 1 "
                    "WHERE id = ("
                    "  SELECT id FROM generations WHERE source = 'demo' "
                    "  AND served_at IS NULL AND model = ? AND call_type IS ? "
                    "  AND state IN ('queued', 'running') "
                    "  ORDER BY state = 'running' DESC, id LIMIT 1) RETURNING id",
                    (now, item.model, item.call_type)).fetchone()
            if row is not None:
                return self._row(conn, row["id"])
        row = self.generations.request(item.call_type, model=item.model,
                                       source="demo", priority=1)
        with self._connect() as conn:
            conn.execute("UPDATE generations SET served_at = ? WHERE id = ?",
                         (now, row["id"]))
            return self._row(conn, row["id"])

    def get(self, generation_id: int):
        with self._connect() as conn:
            return self._row(conn, generation_id)

    def ahead_of(self, row: dict) -> int:
        """How many jobs the worker will finish before this one, running included."""
        if row["state"] not in ("queued", "running"):
            return 0
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM generations WHERE "
                "(state = 'running' AND id != ?) "
                "OR (state = 'queued' AND (priority > ? "
                "    OR (priority = ? AND id < ?)))",
                (row["id"], row["priority"], row["priority"], row["id"])
            ).fetchone()[0]

    def waiting(self) -> int:
        """Live demo jobs open right now — what MAX_WAITING caps."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM generations WHERE source = 'demo' "
                "AND served_at IS NOT NULL AND state IN ('queued', 'running')"
            ).fetchone()[0]

    def path(self, row) -> Path:
        return self.generations.path(row)

    # --- keeping the shelf full --------------------------------------------

    def restock(self, depth: int = SHELF_DEPTH) -> int:
        """Queue refills so every item has `depth` clips waiting or on the way."""
        queued = 0
        for item in MENU.values():
            with self._connect() as conn:
                have = conn.execute(
                    "SELECT COUNT(*) FROM generations WHERE source = 'demo' "
                    "AND served_at IS NULL AND model = ? AND call_type IS ? "
                    "AND state IN ('queued', 'running', 'done')",
                    (item.model, item.call_type)).fetchone()[0]
            for _ in range(depth - have):
                self.generations.request(item.call_type, model=item.model,
                                         source="demo", priority=0)
                queued += 1
        return queued

    def shelf(self) -> dict:
        """Finished, unserved clips per item — the health line of the pool."""
        with self._connect() as conn:
            counts = {}
            for item in MENU.values():
                counts[item.key] = conn.execute(
                    "SELECT COUNT(*) FROM generations WHERE source = 'demo' "
                    "AND served_at IS NULL AND state = 'done' "
                    "AND model = ? AND call_type IS ?",
                    (item.model, item.call_type)).fetchone()[0]
        return counts

    def prune(self, keep_hours: float = KEEP_SERVED_HOURS) -> int:
        """Drop served demo rows older than the keep window, and failed refills.

        A failed row somebody was handed stays its day like any served row, so
        the page polling it reads the failure rather than a 404.

        Compares ISO timestamps as strings, which `utc_now` makes safe: same
        zone, same layout, fixed width.
        """
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415
        cutoff = (datetime.now(timezone.utc) -
                  timedelta(hours=keep_hours)).isoformat()
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT id, storage_ref FROM generations WHERE source = 'demo' "
                "AND ((served_at IS NOT NULL AND served_at < ?) "
                "     OR (served_at IS NULL AND state = 'failed'))", (cutoff,))]
            if rows:
                conn.executemany("DELETE FROM generations WHERE id = ?",
                                 [(r["id"],) for r in rows])
        for row in rows:
            if row["storage_ref"]:
                self.path(row).unlink(missing_ok=True)
        return len(rows)

    @staticmethod
    def _row(conn, generation_id):
        row = conn.execute(
            "SELECT * FROM generations WHERE id = ? AND source = 'demo'",
            (generation_id,)).fetchone()
        return dict(row) if row else None
