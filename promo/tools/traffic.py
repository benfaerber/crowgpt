#!/usr/bin/env python3
"""Pull a week of cawtalker.org traffic from Cloudflare and say who it was.

    make -C promo traffic            # last 7 days
    make -C promo traffic DAYS=3     # fewer

Reads `CLOUDFLARE_API_TOKEN` from `fieldserver/instance/secrets.env` (a zone
analytics read token scoped to cawtalker.org) and queries the GraphQL dataset
`httpRequestsAdaptiveGroups` one day at a time, which is the free plan's window.
Retention is eight days, so a promo event not pulled within a week is gone.

Two things the raw numbers hide, both learned on 2026-08-15: the request total
is overwhelmingly AI crawlers and vulnerability scanners, and the largest human
slice is Ben's own browsers. So every table here is split into likely-human and
bot by user agent, and the human rows are the ones worth reading.

The token carries a client-IP filter. When the home IP changes the API answers
"Cannot use the access token from location <ip>", and the fix is in the
Cloudflare dashboard (profile, API Tokens, edit, client IP filtering), not here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "fieldserver" / "instance" / "secrets.env"
API = "https://api.cloudflare.com/client/v4"
ZONE = "cawtalker.org"

BOT_MARKERS = re.compile(
    r"bot|crawl|spider|scan|fetch|python|curl|wget|go-http|java/|okhttp|libwww|"
    r"headless|phantom|slurp|facebookexternalhit|gptbot|claudebot|anthropic|"
    r"bytespider|petalbot|censys|zgrab|nuclei|masscan|nmap|^$|^-$",
    re.I,
)


def is_bot(user_agent: str) -> bool:
    return bool(BOT_MARKERS.search(user_agent))


class Token:
    def __init__(self, path: Path = SECRETS):
        self.path = path

    def read(self) -> str:
        if not self.path.exists():
            sys.exit(f"no {self.path}; run fieldserver/tools/secrets.sh first")
        for line in self.path.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?CLOUDFLARE_API_TOKEN=(.*)", line)
            if m:
                return m.group(1).strip().strip("'\"")
        sys.exit(f"CLOUDFLARE_API_TOKEN not in {self.path}")


class Cloudflare:
    def __init__(self, token: str):
        self.token = token

    def _call(self, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read() or b"{}")
        errors = payload.get("errors") or []
        if errors:
            msgs = "; ".join(err.get("message", str(err)) for err in errors)
            if "location" in msgs:
                msgs += (
                    "\n  The token is locked to a client IP that is no longer this machine's."
                    "\n  Fix: dash.cloudflare.com, profile, API Tokens, edit the token,"
                    " Client IP Address Filtering."
                )
            sys.exit(f"cloudflare: {msgs}")
        return payload

    def zone_id(self) -> str:
        zones = self._call(f"{API}/zones?name={ZONE}")["result"]
        if not zones:
            sys.exit(f"token cannot see zone {ZONE}")
        return zones[0]["id"]

    def graphql(self, query: str, variables: dict) -> dict:
        return self._call(f"{API}/graphql", {"query": query, "variables": variables})["data"]


@dataclass
class Day:
    day: date
    rows: list[dict] = field(default_factory=list)

    @property
    def requests(self) -> int:
        return sum(r["count"] for r in self.rows)

    def split(self) -> tuple[int, int]:
        human = sum(r["count"] for r in self.rows if not is_bot(r["ua"]))
        return human, self.requests - human


GROUPS = """
query($zone: String!, $start: Date!, $end: Date!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zone}) {
      groups: httpRequestsAdaptiveGroups(
        limit: $limit,
        filter: {date_geq: $start, date_leq: $end}
      ) {
        count
        sum { edgeResponseBytes }
        dimensions {
          userAgent
          clientRequestPath
          clientCountryName
          edgeResponseStatus
          clientIP
        }
      }
    }
  }
}
"""


class Report:
    def __init__(self, cf: Cloudflare, zone: str, days: int):
        self.cf = cf
        self.zone = zone
        self.days = [date.today() - timedelta(days=i) for i in range(days, 0, -1)]

    def pull(self) -> list[Day]:
        out = []
        for d in self.days:
            data = self.cf.graphql(
                GROUPS, {"zone": self.zone, "start": d.isoformat(), "end": d.isoformat(), "limit": 10000}
            )
            groups = data["viewer"]["zones"][0]["groups"]
            rows = [
                {
                    "count": g["count"],
                    "bytes": g["sum"]["edgeResponseBytes"],
                    "ua": g["dimensions"]["userAgent"] or "",
                    "path": g["dimensions"]["clientRequestPath"],
                    "country": g["dimensions"]["clientCountryName"],
                    "status": g["dimensions"]["edgeResponseStatus"],
                    "ip": g["dimensions"]["clientIP"],
                }
                for g in groups
            ]
            out.append(Day(d, rows))
        return out

    @staticmethod
    def table(title: str, counter: Counter, n: int = 12) -> None:
        print(f"\n{title}")
        width = max((len(str(k)) for k, _ in counter.most_common(n)), default=10)
        for key, count in counter.most_common(n):
            print(f"  {count:>7}  {str(key)[:110]:<{min(width, 110)}}")

    def render(self, days: list[Day]) -> None:
        print(f"cawtalker.org, {days[0].day} to {days[-1].day}")
        print("\n  day         requests   human     bot")
        for d in days:
            human, bot = d.split()
            print(f"  {d.day}  {d.requests:>8}  {human:>6}  {bot:>6}")
        total = sum(d.requests for d in days)
        human_total = sum(d.split()[0] for d in days)
        print(f"  {'total':<10}  {total:>8}  {human_total:>6}  {total - human_total:>6}")

        human_rows = [r for d in days for r in d.rows if not is_bot(r["ua"])]
        bot_rows = [r for d in days for r in d.rows if is_bot(r["ua"])]

        def tally(rows: list[dict], key: str) -> Counter:
            c: Counter = Counter()
            for r in rows:
                c[r[key]] += r["count"]
            return c

        human_ips = defaultdict(int)
        for r in human_rows:
            human_ips[r["ip"]] += r["count"]
        print(f"\nlikely-human requests came from {len(human_ips)} distinct IPs")

        self.table("likely-human: pages (HTML and top-level only)", Counter(
            {k: v for k, v in tally(human_rows, "path").items() if not re.search(r"\.(js|css|png|jpg|woff2?|wav|mp4|ico|json)$", k)}
        ))
        self.table("likely-human: countries", tally(human_rows, "country"))
        self.table("likely-human: user agents", tally(human_rows, "ua"))
        self.table("likely-human: status codes", tally(human_rows, "status"), 6)
        self.table("bots: user agents", tally(bot_rows, "ua"))
        self.table("bots: paths", tally(bot_rows, "path"))

        print(
            "\nHuman-only page views with the beacon's own bot filtering are in the dashboard:"
            "\nAnalytics & Logs, Web Analytics. The API token cannot read that dataset."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7, help="days back, max 8 on the free plan")
    parser.add_argument("--json", action="store_true", help="dump the raw rows instead of tables")
    args = parser.parse_args()

    cf = Cloudflare(Token().read())
    report = Report(cf, cf.zone_id(), min(args.days, 8))
    days = report.pull()
    if args.json:
        json.dump([{"day": d.day.isoformat(), "rows": d.rows} for d in days], sys.stdout, indent=1)
        return
    report.render(days)


if __name__ == "__main__":
    main()
