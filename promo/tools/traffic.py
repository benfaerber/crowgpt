#!/usr/bin/env python3
"""Pull a week of crowgpt.org traffic from Cloudflare and say who it was.

    make -C promo traffic            # last 7 days
    make -C promo traffic DAYS=3     # fewer

Reads `CLOUDFLARE_API_TOKEN` from `fieldserver/instance/secrets.env` (a zone
analytics read token scoped to crowgpt.org) and queries the GraphQL dataset
`httpRequestsAdaptiveGroups` one day at a time, which is the free plan's window.
Retention is eight days, so a promo event not pulled within a week is gone.

The rules (who counts as a person, an assistant, a probe) live in
`fieldserver/src/fieldserver/core/traffic.py`, shared with the traffic worker
that keeps a summary per day for the dashboard's Traffic page.

The raw numbers hide who it was. Scanners send browser user agents, so a user-agent
split alone called 11,244 requests human in a week when the analytics beacon ran
152 times. So page views and visitors here count only `/cdn-cgi/rum`, the beacon a
browser fires by running the page's JavaScript, and any other browser-looking
request that failed or asked for `/.env` and the like is filed as a probe. That
count still includes Ben's own visits.

AI use shows up only partly. Assistants that fetch a page for a person name
themselves in the user agent and are counted, but a model answering from its index
or from search makes no request here. On the free plan this dataset refuses
`clientRefererHost` and `clientRequestQuery`, so visits arriving from an assistant
can only be seen in the dashboard, under Web Analytics, and only when the browser
sent a referrer.

The token may carry a client-IP filter. If the IP changes the API answers
"Cannot use the access token from location <ip>", and the fix is in the Cloudflare
dashboard (profile, API Tokens, edit, client IP filtering), not here.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fieldserver" / "src"))

from fieldserver.core.traffic import (  # noqa: E402
    RETENTION_DAYS, ZONE, Cloudflare, Kind, Request, Token, TrafficError,
)

SECRETS = REPO / "fieldserver" / "instance" / "secrets.env"


class Report:
    def __init__(self, cf: Cloudflare, days: int):
        self.cf = cf
        today = datetime.now(timezone.utc).date()
        self.days = [today - timedelta(days=i) for i in range(days, 0, -1)]

    def pull(self) -> list[tuple[date, list[Request]]]:
        return [(d, self.cf.requests(d)[0]) for d in self.days]

    @staticmethod
    def tally(rows: list[Request], key: str) -> Counter:
        counts: Counter = Counter()
        for row in rows:
            counts[getattr(row, key)] += row.count
        return counts

    @staticmethod
    def total(rows: list[Request]) -> int:
        return sum(row.count for row in rows)

    @staticmethod
    def table(title: str, counter: Counter, n: int = 12) -> None:
        print(f"\n{title}")
        if not counter:
            print("  none")
        for key, count in counter.most_common(n):
            print(f"  {count:>7}  {str(key)[:110]}")

    def render(self, days: list[tuple[date, list[Request]]]) -> None:
        print(f"{ZONE}, {days[0][0]} to {days[-1][0]} (UTC days)")
        print("\n  day         views  visitors  assistant  ai crawl  search  preview  other bot   probe  all reqs")
        for day, rows in days:
            views = [r for r in rows if r.is_view]
            of = lambda kind: [r for r in rows if r.kind is kind]  # noqa: E731
            print(
                f"  {day}  {self.total(views):>5}  {len({r.ip for r in views}):>8}"
                f"  {self.total(of(Kind.ASSISTANT)):>9}  {self.total(of(Kind.AI_CRAWLER)):>8}"
                f"  {self.total(of(Kind.SEARCH)):>6}  {self.total(of(Kind.PREVIEW)):>7}"
                f"  {self.total(of(Kind.BOT)):>9}  {self.total(of(Kind.PROBE)):>6}  {self.total(rows):>8}"
            )

        rows = [row for _, day_rows in days for row in day_rows]
        by_kind = {kind: [row for row in rows if row.kind is kind] for kind in Kind}
        views = [row for row in rows if row.is_view]
        print(
            f"\nvisitors: {len({r.ip for r in views})} distinct IPs ran the beacon, "
            f"{self.total(views)} page views. Includes your own visits."
        )

        self.table("visitors: countries", self.tally(views, "country"))
        self.table("browsers: pages that loaded", self.tally([r for r in rows if r.is_page], "path"))
        self.table("AI assistants fetching a page for someone", self.tally(by_kind[Kind.ASSISTANT], "agent"))
        self.table("AI assistants: which pages", self.tally(by_kind[Kind.ASSISTANT], "path"), 6)
        self.table("AI crawlers", self.tally(by_kind[Kind.AI_CRAWLER], "agent"))
        self.table("search crawlers", self.tally(by_kind[Kind.SEARCH], "agent"))
        self.table("link previews, usually a link being shared", self.tally(by_kind[Kind.PREVIEW], "agent"))
        self.table("other bots", self.tally(by_kind[Kind.BOT], "agent"), 6)
        self.table("probes: requests that failed or hunted for secrets", self.tally(by_kind[Kind.PROBE], "path"), 6)

        print(
            "\nWhere visitors came from, Gemini and other assistants included, is only in the"
            "\ndashboard (Analytics & Logs, Web Analytics), and only when a referrer was sent."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7, help=f"days back, max {RETENTION_DAYS} on the free plan")
    parser.add_argument("--json", action="store_true", help="dump the raw rows instead of tables")
    args = parser.parse_args()

    try:
        report = Report(Cloudflare(Token(SECRETS).read()), min(args.days, RETENTION_DAYS))
        days = report.pull()
    except TrafficError as error:
        sys.exit(str(error))
    if args.json:
        json.dump([{"day": d.isoformat(), "rows": [vars(r) for r in rows]} for d, rows in days],
                  sys.stdout, indent=1, default=lambda kind: kind.value)
        return
    report.render(days)


if __name__ == "__main__":
    main()
