"""crowgpt.org's traffic, one summary per UTC day, written by the traffic worker.

A day is provisional until it is over and pulled once more; after that it is
final and the worker leaves it alone.
"""

import json
from datetime import date

from .db_base import Database, utc_now


class TrafficStore(Database):
    def save(self, day: date, summary: dict, final: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO traffic_days (day, summary, final, fetched_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(day) DO UPDATE SET summary = excluded.summary, "
                "final = excluded.final, fetched_at = excluded.fetched_at",
                (day.isoformat(), json.dumps(summary), int(final), utc_now()))

    def final_days(self) -> set[date]:
        with self._connect() as conn:
            rows = conn.execute("SELECT day FROM traffic_days WHERE final = 1")
            return {date.fromisoformat(r["day"]) for r in rows}

    def since(self, first: date) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM traffic_days WHERE day >= ? ORDER BY day", (first.isoformat(),))
            return [{"day": r["day"], "final": bool(r["final"]), "fetched_at": r["fetched_at"],
                     "summary": json.loads(r["summary"])} for r in rows]

    def last_fetched(self) -> str | None:
        with self._connect() as conn:
            return conn.execute("SELECT MAX(fetched_at) AS at FROM traffic_days").fetchone()["at"]
