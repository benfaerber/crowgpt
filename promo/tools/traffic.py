#!/usr/bin/env python3
"""Pull a week of crowgpt.org traffic from Cloudflare and say who it was.

    make -C promo traffic            # last 7 days
    make -C promo traffic DAYS=3     # fewer

Reads `CLOUDFLARE_API_TOKEN` from `fieldserver/instance/secrets.env` (a zone
analytics read token scoped to crowgpt.org) and queries the GraphQL dataset
`httpRequestsAdaptiveGroups` one day at a time, which is the free plan's window.
Retention is eight days, so a promo event not pulled within a week is gone.

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
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "fieldserver" / "instance" / "secrets.env"
API = "https://api.cloudflare.com/client/v4"
ZONE = "crowgpt.org"

BEACON = "/cdn-cgi/rum"
ASSET_PATHS = re.compile(r"\.(js|css|png|jpg|svg|woff2?|wav|mp3|mp4|ico|json)$")
PROBE_PATHS = re.compile(r"(^|/)\.[a-z]|wp-|\.php$|/(admin|login|xmlrpc)", re.I)
BOT_MARKERS = re.compile(
    r"bot|crawl|spider|scan|fetch|python|curl|wget|go-http|java/|okhttp|libwww|"
    r"headless|phantom|slurp|research|censys|zgrab|nuclei|masscan|nmap|^$|^-$",
    re.I,
)


class Kind(Enum):
    BROWSER = "browser"
    ASSISTANT = "assistant"
    AI_CRAWLER = "ai crawler"
    SEARCH = "search"
    PREVIEW = "preview"
    BOT = "other bot"
    PROBE = "probe"


class Classifier:
    """Sorts a request by what sent it.

    The path is checked first because scanners borrow names: in the first week of
    this report most "ChatGPT" and "Claude" requests were asking for `/.env`. A name
    in a user agent is still only a claim, since nothing here verifies the source IP.
    """

    AGENTS = (
        ("ChatGPT-User", "ChatGPT", Kind.ASSISTANT),
        ("Claude-User", "Claude", Kind.ASSISTANT),
        ("Perplexity-User", "Perplexity", Kind.ASSISTANT),
        ("Gemini-Deep-Research", "Gemini", Kind.ASSISTANT),
        ("Google-NotebookLM", "NotebookLM", Kind.ASSISTANT),
        ("MistralAI-User", "Mistral", Kind.ASSISTANT),
        ("DuckAssistBot", "DuckAssist", Kind.ASSISTANT),
        ("GPTBot", "GPTBot", Kind.AI_CRAWLER),
        ("OAI-SearchBot", "OAI-SearchBot", Kind.AI_CRAWLER),
        ("ClaudeBot", "ClaudeBot", Kind.AI_CRAWLER),
        ("Claude-SearchBot", "Claude-SearchBot", Kind.AI_CRAWLER),
        ("PerplexityBot", "PerplexityBot", Kind.AI_CRAWLER),
        ("Amazonbot", "Amazonbot", Kind.AI_CRAWLER),
        ("Bytespider", "Bytespider", Kind.AI_CRAWLER),
        ("CCBot", "CCBot", Kind.AI_CRAWLER),
        ("meta-externalagent", "Meta AI", Kind.AI_CRAWLER),
        ("Googlebot", "Googlebot", Kind.SEARCH),
        ("bingbot", "Bingbot", Kind.SEARCH),
        ("Applebot", "Applebot", Kind.SEARCH),
        ("DuckDuckBot", "DuckDuckBot", Kind.SEARCH),
        ("facebookexternalhit", "Facebook/Instagram", Kind.PREVIEW),
        ("Twitterbot", "X", Kind.PREVIEW),
        ("LinkedInBot", "LinkedIn", Kind.PREVIEW),
        ("Slackbot", "Slack", Kind.PREVIEW),
        ("Discordbot", "Discord", Kind.PREVIEW),
        ("TelegramBot", "Telegram", Kind.PREVIEW),
        ("WhatsApp", "WhatsApp", Kind.PREVIEW),
        ("redditbot", "Reddit", Kind.PREVIEW),
    )

    def classify(self, user_agent: str, path: str, status: int) -> tuple[Kind, str]:
        if PROBE_PATHS.search(path):
            return Kind.PROBE, user_agent
        lowered = user_agent.lower()
        for marker, name, kind in self.AGENTS:
            if marker.lower() in lowered:
                return kind, name
        if BOT_MARKERS.search(user_agent):
            return Kind.BOT, user_agent
        if status >= 400:
            return Kind.PROBE, user_agent
        return Kind.BROWSER, user_agent


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

    def of(self, kind: Kind) -> list[dict]:
        return [r for r in self.rows if r["kind"] is kind]

    def beacons(self) -> list[dict]:
        return [r for r in self.of(Kind.BROWSER) if r["path"] == BEACON]


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
        self.classifier = Classifier()

    def pull(self) -> list[Day]:
        out = []
        for d in self.days:
            data = self.cf.graphql(
                GROUPS, {"zone": self.zone, "start": d.isoformat(), "end": d.isoformat(), "limit": 10000}
            )
            groups = data["viewer"]["zones"][0]["groups"]
            rows = [
                self._row(g)
                for g in groups
            ]
            out.append(Day(d, rows))
        return out

    def _row(self, group: dict) -> dict:
        dims = group["dimensions"]
        user_agent = dims["userAgent"] or ""
        path = dims["clientRequestPath"]
        status = dims["edgeResponseStatus"]
        kind, agent = self.classifier.classify(user_agent, path, status)
        return {
            "count": group["count"],
            "bytes": group["sum"]["edgeResponseBytes"],
            "ua": user_agent,
            "path": path,
            "country": dims["clientCountryName"],
            "status": status,
            "ip": dims["clientIP"],
            "kind": kind,
            "agent": agent,
        }

    @staticmethod
    def tally(rows: list[dict], key: str) -> Counter:
        counts: Counter = Counter()
        for row in rows:
            counts[row[key]] += row["count"]
        return counts

    @staticmethod
    def total(rows: list[dict]) -> int:
        return sum(row["count"] for row in rows)

    @staticmethod
    def table(title: str, counter: Counter, n: int = 12) -> None:
        print(f"\n{title}")
        if not counter:
            print("  none")
        for key, count in counter.most_common(n):
            print(f"  {count:>7}  {str(key)[:110]}")

    def render(self, days: list[Day]) -> None:
        print(f"{ZONE}, {days[0].day} to {days[-1].day}")
        print("\n  day         views  visitors  assistant  ai crawl  search  preview  other bot   probe  all reqs")
        for d in days:
            beacons = d.beacons()
            print(
                f"  {d.day}  {self.total(beacons):>5}  {len({r['ip'] for r in beacons}):>8}"
                f"  {self.total(d.of(Kind.ASSISTANT)):>9}  {self.total(d.of(Kind.AI_CRAWLER)):>8}"
                f"  {self.total(d.of(Kind.SEARCH)):>6}  {self.total(d.of(Kind.PREVIEW)):>7}"
                f"  {self.total(d.of(Kind.BOT)):>9}  {self.total(d.of(Kind.PROBE)):>6}  {d.requests:>8}"
            )

        rows = [row for d in days for row in d.rows]
        by_kind = {kind: [row for row in rows if row["kind"] is kind] for kind in Kind}
        beacons = [row for d in days for row in d.beacons()]
        print(
            f"\nvisitors: {len({r['ip'] for r in beacons})} distinct IPs ran the beacon, "
            f"{self.total(beacons)} page views. Includes your own visits."
        )

        self.table("visitors: countries", self.tally(beacons, "country"))
        self.table("browsers: pages that loaded", Counter({
            path: count
            for path, count in self.tally(
                [row for row in by_kind[Kind.BROWSER] if row["status"] in (200, 304)], "path"
            ).items()
            if path != BEACON and not ASSET_PATHS.search(path)
        }))
        self.table("AI assistants fetching a page for someone", self.tally(by_kind[Kind.ASSISTANT], "agent"))
        self.table("AI assistants: which pages", self.tally(by_kind[Kind.ASSISTANT], "path"), 6)
        self.table("AI crawlers", self.tally(by_kind[Kind.AI_CRAWLER], "agent"))
        self.table("search crawlers", self.tally(by_kind[Kind.SEARCH], "agent"))
        self.table("link previews, usually a link being shared", self.tally(by_kind[Kind.PREVIEW], "agent"))
        self.table("other bots", self.tally(by_kind[Kind.BOT], "agent"), 6)
        self.table("probes: browser-looking requests that failed or hunted for secrets", self.tally(by_kind[Kind.PROBE], "path"), 6)

        print(
            "\nWhere visitors came from, Gemini and other assistants included, is only in the"
            "\ndashboard (Analytics & Logs, Web Analytics), and only when a referrer was sent."
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
        json.dump([{"day": d.day.isoformat(), "rows": d.rows} for d in days], sys.stdout, indent=1, default=lambda kind: kind.value)
        return
    report.render(days)


if __name__ == "__main__":
    main()
