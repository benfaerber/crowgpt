"""Xeno-canto, through its v3 recordings API. Needs a free key."""

import os
import time
from typing import Callable, Iterator

import requests

from .download import default_user_agent
from .errors import SourceError

API_URL = "https://xeno-canto.org/api/3/recordings"


class XenoCantoError(SourceError):
    pass


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_length_seconds(length) -> int | None:
    """'4:07' -> 247. Xeno-canto reports length as clock text.

    Anything unparseable is None rather than zero: a duration of zero is not
    "unknown", it is a number that sums into an hours total.
    """
    if length is None:
        return None
    if isinstance(length, (int, float)):
        return int(length) if length >= 0 else None
    parts = str(length).strip().split(":")
    if not all(part.strip().isdigit() for part in parts):
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds


def _with_scheme(url) -> str | None:
    if not url:
        return None
    return "https:" + url if url.startswith("//") else url


def build_query(params: dict) -> str:
    """Structured builder params -> a v3 query string.

    Operator values must be quoted: `q:>C` is HTTP 400, `q:">C"` works.
    """
    terms = []

    def add(tag, value):
        value = (str(value) if value is not None else "").strip()
        if not value:
            return
        needs_quotes = " " in value or value[0] in "<>="
        terms.append(f'{tag}:"{value}"' if needs_quotes else f"{tag}:{value}")

    add("gen", params.get("gen"))
    add("sp", params.get("sp"))
    add("cnt", params.get("country"))
    add("type", params.get("call_type"))
    add("q", params.get("quality"))
    return " ".join(terms) or "gen:Corvus"


class XenoCantoSource:
    id = "xeno_canto"

    def __init__(self, api_url=None, key=None):
        self.api_url = api_url or os.environ.get("XENOCANTO_API", API_URL)
        self.key = key if key is not None else os.environ.get("XENOCANTO_KEY", "")
        self._cached_query = None
        self._cached_page_one = {}

    def _redact(self, text: str) -> str:
        return text.replace(self.key, "<key redacted>") if self.key else text

    def _get(self, query: str, page: int) -> dict:
        if not self.key:
            raise XenoCantoError(
                "No Xeno-canto API key configured. Get a free key at "
                "https://xeno-canto.org/account and set XENOCANTO_KEY."
            )
        # The key rides in the query string, so it rides into the message of
        # every exception urllib3 raises on the way back. Raising *outside* the
        # except block leaves no unredacted original on __context__ for a
        # reporter that walks the chain to find.
        failure = None
        try:
            resp = requests.get(
                self.api_url,
                params={"query": query, "key": self.key, "page": page},
                headers={"User-Agent": default_user_agent()},
                timeout=30,
            )
        except requests.RequestException as exc:
            failure = f"{type(exc).__name__}: {self._redact(str(exc))}"
        if failure is not None:
            raise XenoCantoError(f"Request to Xeno-canto failed: {failure}")
        if resp.status_code != 200:
            detail = self._redact(resp.text[:200].replace("\n", " "))
            raise XenoCantoError(f"Xeno-canto returned HTTP {resp.status_code}: {detail}")
        try:
            return resp.json()
        except ValueError as exc:
            raise XenoCantoError("Xeno-canto returned a non-JSON response") from exc

    def _page_one(self, query: str) -> dict:
        """Page 1, fetched at most once per query: the count and the first
        page are the same response."""
        if self._cached_query != query:
            self._cached_page_one = self._get(query, 1)
            self._cached_query = query
        return self._cached_page_one

    def count(self, query: str) -> int:
        return int(self._page_one(query).get("numRecordings", 0) or 0)

    def fetch(self, query: str, max_recordings: int, max_pages: int | None = None,
              delay: float = 1.0, should_stop: Callable[[], bool] | None = None,
              refresh: bool = False, **_) -> Iterator[dict]:
        """Yield normalised recordings, paging with a delay between calls.

        `refresh` is accepted and ignored: there is no local cache here, and
        the shared call site passes the flag to whichever source it holds.
        """
        yielded = 0
        page = 1
        while max_pages is None or page <= max_pages:
            data = self._page_one(query) if page == 1 else self._get(query, page)
            num_pages = int(data.get("numPages", 1) or 1)
            for rec in data.get("recordings", []) or []:
                if should_stop and should_stop():
                    return
                yield self.normalize(rec)
                yielded += 1
                if yielded >= max_recordings:
                    return
            if page >= num_pages:
                return
            page += 1
            time.sleep(delay)

    @staticmethod
    def normalize(rec: dict) -> dict:
        file_url = rec.get("file")
        if isinstance(file_url, dict):
            file_url = file_url.get("url")
        gen = (rec.get("gen") or "").strip()
        sp = (rec.get("sp") or "").strip()
        species = (rec.get("en") or f"{gen} {sp}").strip()
        return {
            "source": XenoCantoSource.id,
            "source_ref": str(rec.get("id", "")),
            "species": species or None,
            "call_type": (rec.get("type") or "").strip() or None,
            "country": rec.get("cnt"),
            "location": rec.get("loc"),
            "lat": _as_float(rec.get("lat")),
            "lng": _as_float(rec.get("lng")),
            "license": _with_scheme(rec.get("lic")),
            "quality": rec.get("q"),
            "length": rec.get("length"),
            "duration_seconds": parse_length_seconds(rec.get("length")),
            # Xeno-canto has no stable recordist id; `rec` is a display name.
            "recordist": rec.get("rec"),
            "recordist_id": None,
            "date": (rec.get("date") or "").strip() or None,
            "audio_url": _with_scheme(file_url),
            "page_url": _with_scheme(rec.get("url")),
            "raw": rec,
        }
