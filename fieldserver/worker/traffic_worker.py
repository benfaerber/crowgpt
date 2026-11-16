"""Keep crowgpt.org's Cloudflare traffic past Cloudflare's eight days.

Every hour: today's summary, provisionally, and each finished day in the
retention window that is not yet final. A finished day is pulled once more
after it ends and then left alone, so the table grows by one final row a day
and history outlives the plan's window.

Reads CLOUDFLARE_API_TOKEN from instance/secrets.env itself, so it runs
unsandboxed like the scout scheduler; it talks only to Cloudflare and reads
nothing a stranger sent. Without a token it says so once an hour and waits.

    FIELD_DB=/path/field.db .venv/bin/python worker/traffic_worker.py --once
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDSERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FIELDSERVER / "src"))

from fieldserver.core.traffic import RETENTION_DAYS, Cloudflare, Token, TrafficError  # noqa: E402
from fieldserver.stores.traffic import TrafficStore  # noqa: E402

DEFAULT_DB = FIELDSERVER / "instance" / "field.db"
SECRETS = FIELDSERVER / "instance" / "secrets.env"
EVERY_S = 3600
RETRY_S = 300
SETTLE = timedelta(hours=2)


class TrafficCollector:
    def __init__(self, store: TrafficStore, token: Token):
        self.store = store
        self.token = token

    def collect(self, now: datetime) -> list[str]:
        """A day is final once it has been over for SETTLE, so late edge logs
        land in it; until then it is saved provisionally like today."""
        cloudflare = Cloudflare(self.token.read())
        final = self.store.final_days()
        settled = (now - SETTLE).date()
        done = []
        for back in range(RETENTION_DAYS - 1, -1, -1):
            day = now.date() - timedelta(days=back)
            if day in final:
                continue
            is_final = day < settled
            self.store.save(day, cloudflare.summary(day), final=is_final)
            done.append(f"{day} {'final' if is_final else 'so far'}")
        return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="collect once and exit")
    args = parser.parse_args()
    collector = TrafficCollector(TrafficStore(Path(os.environ.get("FIELD_DB") or DEFAULT_DB)), Token(SECRETS))
    print(f"traffic worker up, collecting every {EVERY_S // 60} minutes", flush=True)
    while True:
        wait = EVERY_S
        try:
            print("traffic: " + ", ".join(collector.collect(datetime.now(timezone.utc))), flush=True)
        except (TrafficError, sqlite3.OperationalError) as error:
            print(f"traffic: {error}, retrying in {RETRY_S // 60} minutes", flush=True)
            wait = RETRY_S
        if args.once:
            return
        time.sleep(wait)


if __name__ == "__main__":
    main()
