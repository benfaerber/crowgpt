"""Who visited crowgpt.org, from Cloudflare, sorted into people and machines.

Stdlib only, so the traffic worker, the dashboard route and the
`make -C promo traffic` report all read the same rules.

Cloudflare's free plan keeps eight days of `httpRequestsAdaptiveGroups` and
answers one day per query. A day is pulled whole and reduced to a summary on
the spot; the visitor IPs are counted and then dropped, never stored.

The raw numbers hide who it was. Scanners send browser user agents, so page
views and visitors count only `/cdn-cgi/rum`, the beacon a browser fires by
running the page's JavaScript. Any other browser-looking request that failed
or hunted for secrets is a probe. The count includes Ben's own visits.

A name in a user agent is a claim, not a source: nothing here verifies the IP.
Scanners borrow assistant names, so a claimed AI agent that was not served a
page (a 404, or the 301 a scanner aiming at www or plain http gets) is a probe.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
ZONE = "crowgpt.org"
RETENTION_DAYS = 8
GROUP_LIMIT = 10000

BEACON = "/cdn-cgi/rum"
#: Requests the pages make for themselves, not pages anybody opened.
NOT_PAGES = re.compile(r"^/(cdn-cgi/|geo$)")
ASSET_PATHS = re.compile(r"\.(js|css|png|jpg|jpeg|webp|svg|woff2?|wav|mp3|mp4|ico|json|txt|xml|webmanifest)$", re.I)
PROBE_PATHS = re.compile(
    r"(^|/)\.([a-z]|$)|wp-|\.php|/(admin|login|xmlrpc|cgi-bin|actuator|server-status|phpmyadmin)"
    r"|docker|compose|\.ya?ml$|\.sql$|\.bak$|\.zip$|\.tar|\.key$|backup|config|\.aws|secrets?\b"
    r"|env|firebase|service-account|google-services|/proc/|graphql|nacos|\.\./",
    re.I,
)
BOT_MARKERS = re.compile(
    r"bot|crawl|spider|scan|fetch|python|curl|wget|go-http|java/|okhttp|libwww|"
    r"headless|phantom|slurp|research|censys|zgrab|nuclei|masscan|nmap|^$|^-$",
    re.I,
)


class TrafficError(RuntimeError):
    pass


class Kind(Enum):
    BROWSER = "browser"
    ASSISTANT = "assistant"
    AI_CRAWLER = "ai crawler"
    SEARCH = "search"
    PREVIEW = "preview"
    BOT = "other bot"
    PROBE = "probe"


#: The kinds whose agent names are worth listing, and never a raw user agent.
NAMED_KINDS = (Kind.ASSISTANT, Kind.AI_CRAWLER, Kind.SEARCH, Kind.PREVIEW)


class Classifier:
    """Sorts a request by what sent it. The path is checked before the name,
    and a claimed AI agent that was refused is filed as a probe."""

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
                if kind in (Kind.ASSISTANT, Kind.AI_CRAWLER) and status not in (200, 304):
                    return Kind.PROBE, user_agent
                return kind, name
        if BOT_MARKERS.search(user_agent):
            return Kind.BOT, user_agent
        if status >= 400:
            return Kind.PROBE, user_agent
        return Kind.BROWSER, user_agent


@dataclass(frozen=True)
class Request:
    count: int
    user_agent: str
    path: str
    country: str
    status: int
    ip: str
    kind: Kind
    agent: str

    @property
    def is_view(self) -> bool:
        return self.kind is Kind.BROWSER and self.path == BEACON

    @property
    def is_page(self) -> bool:
        return (self.kind is Kind.BROWSER and self.status in (200, 304)
                and not NOT_PAGES.search(self.path) and not ASSET_PATHS.search(self.path))


class Summary:
    """One day reduced to what the dashboard shows. No IPs survive it."""

    TOP = 15

    def __init__(self, requests: list[Request], truncated: bool = False):
        self.requests = requests
        self.truncated = truncated

    def as_dict(self) -> dict:
        views = [r for r in self.requests if r.is_view]
        countries: dict[str, set[str]] = {}
        for r in views:
            countries.setdefault(r.country or "Unknown", set()).add(r.ip)
        return {
            "requests": self.total(self.requests),
            "views": self.total(views),
            "visitors": len({r.ip for r in views}),
            "kinds": {kind.value: self.total(self.of(kind)) for kind in Kind},
            "countries": dict(Counter({name: len(ips) for name, ips in countries.items()}).most_common(self.TOP)),
            "pages": self.top([r for r in self.requests if r.is_page], "path"),
            "agents": {kind.value: self.top(self.of(kind), "agent") for kind in NAMED_KINDS},
            "probes": self.top(self.of(Kind.PROBE), "path", 8),
            "truncated": self.truncated,
        }

    def of(self, kind: Kind) -> list[Request]:
        return [r for r in self.requests if r.kind is kind]

    @staticmethod
    def total(requests: list[Request]) -> int:
        return sum(r.count for r in requests)

    def top(self, requests: list[Request], attribute: str, n: int | None = None) -> dict[str, int]:
        counts: Counter = Counter()
        for r in requests:
            counts[getattr(r, attribute)] += r.count
        return dict(counts.most_common(n or self.TOP))


class Token:
    """CLOUDFLARE_API_TOKEN from an env file, read without a shell."""

    NAME = "CLOUDFLARE_API_TOKEN"

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str:
        if not self.path.exists():
            raise TrafficError(f"no {self.path}")
        for line in self.path.read_text().splitlines():
            m = re.match(rf"\s*(?:export\s+)?{self.NAME}=(.*)", line)
            if m and m.group(1).strip().strip("'\""):
                return m.group(1).strip().strip("'\"")
        raise TrafficError(f"{self.NAME} not in {self.path}")


GROUPS = """
query($zone: String!, $start: Date!, $end: Date!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zone}) {
      groups: httpRequestsAdaptiveGroups(
        limit: $limit,
        filter: {date_geq: $start, date_leq: $end}
      ) {
        count
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


class Cloudflare:
    def __init__(self, token: str, zone: str = ZONE):
        self.token = token
        self.zone = zone
        self.classifier = Classifier()
        self._zone_id: str | None = None

    def requests(self, day: date) -> tuple[list[Request], bool]:
        """Every request group Cloudflare has for one UTC day, classified."""
        data = self._call(f"{API}/graphql", {"query": GROUPS, "variables": {
            "zone": self.zone_id(), "start": day.isoformat(), "end": day.isoformat(), "limit": GROUP_LIMIT,
        }})["data"]
        groups = data["viewer"]["zones"][0]["groups"]
        return [self._request(g) for g in groups], len(groups) >= GROUP_LIMIT

    def summary(self, day: date) -> dict:
        return Summary(*self.requests(day)).as_dict()

    def zone_id(self) -> str:
        if self._zone_id is None:
            zones = self._call(f"{API}/zones?name={self.zone}")["result"]
            if not zones:
                raise TrafficError(f"the token cannot see zone {self.zone}")
            self._zone_id = zones[0]["id"]
        return self._zone_id

    def _request(self, group: dict) -> Request:
        dims = group["dimensions"]
        user_agent = dims["userAgent"] or ""
        path = dims["clientRequestPath"]
        status = dims["edgeResponseStatus"]
        kind, agent = self.classifier.classify(user_agent, path, status)
        return Request(group["count"], user_agent, path, dims["clientCountryName"], status,
                       dims["clientIP"], kind, agent)

    def _call(self, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read() or b"{}")
        except (urllib.error.URLError, TimeoutError) as e:
            raise TrafficError(f"cloudflare unreachable: {e}") from e
        errors = payload.get("errors") or []
        if errors:
            message = "; ".join(err.get("message", str(err)) for err in errors)
            if "location" in message:
                message += (" (the token is locked to a client IP that is not this machine's:"
                            " dash.cloudflare.com, profile, API Tokens, Client IP Address Filtering)")
            raise TrafficError(f"cloudflare: {message}")
        return payload
