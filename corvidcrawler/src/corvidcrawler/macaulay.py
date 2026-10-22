"""The Macaulay Library: catalogue in, audio out. No key.

Two ways to get the asset list. `MacaulaySearch` pages the JSON API the
search UI itself calls, caching pages on disk so a re-run costs nothing.
`read_catalogue` reads a CSV the UI exports for a signed-in human, capped at
10,000 rows. Both hand the same asset ids to the same media host.

Macaulay media is not Creative Commons. The licence and recordist are kept on
every row so attribution is possible, and the corpus stays out of git.
"""

import csv
import time
from pathlib import Path

import requests

from .download import Downloader, default_user_agent
from .errors import SourceError
from .pagecache import PageCache
from .taxonomy import ebird_code

SEARCH_URL = "https://search.macaulaylibrary.org/api/v2/search"
ASSET_URL = "https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset}/mp3"
PAGE_URL = "https://macaulaylibrary.org/asset/{asset}"
CATALOG_URL = "https://search.macaulaylibrary.org/catalog?taxonCode={code}&mediaType=audio"

EXPORT_CAP = 10000
CATALOG_NUMBER = "ML Catalog Number"
ATTRIBUTION = "Macaulay Library, Cornell Lab of Ornithology"
HOUSEKEEPING_TAGS = ("archive", "no_playback")


class MacaulayError(SourceError):
    pass


def _is_catalogue(query) -> bool:
    return str(query).lower().endswith(".csv")


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_catalogue(csv_path) -> list[dict]:
    """Rows from a Macaulay search export. The export carries a UTF-8 BOM, so
    read as plain utf-8 the first column is '﻿ML Catalog Number' and every
    lookup of it silently misses."""
    path = Path(csv_path)
    if not path.exists():
        raise MacaulayError(
            f"No catalogue at {path}. Export one from the Macaulay search UI:\n"
            f"  {CATALOG_URL.format(code='amecro')}\n"
            "  run the search, then Download to get a CSV of the results."
        )
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get(CATALOG_NUMBER)]
    if not rows:
        raise MacaulayError(f"{path} has no '{CATALOG_NUMBER}' column — is it a Macaulay export?")
    return rows


class AssetCache(PageCache):
    def __init__(self, root, taxon_code):
        super().__init__(root, "macaulay", taxon_code)
        self.assets_path = self.items_path


class MacaulaySearch:
    """Pages the search API the web UI calls.

    Pagination is by opaque cursor: only the LAST result on a page carries a
    cursorMark, fed back as initialCursorMark for the next page. There is no
    total count, no key and no published rate limit, which is why this sleeps
    between pages.
    """

    def __init__(self, delay=1.0, retries=4, timeout=30, page_size=100,
                 user_agent=None, session=None, cache_dir=None, on_page=None):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.page_size = page_size
        self.session = session or requests.Session()
        self.user_agent = user_agent or default_user_agent()
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.on_page = on_page

    def _page(self, taxon_code, cursor, count=None) -> list:
        params = {
            "taxonCode": taxon_code,
            "mediaType": "audio",
            "count": count or self.page_size,
            "sort": "rating_rank_desc",
        }
        if cursor:
            params["initialCursorMark"] = cursor
        for attempt in range(self.retries):
            try:
                response = self.session.get(
                    SEARCH_URL, params=params,
                    headers={"User-Agent": self.user_agent}, timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt == self.retries - 1:
                    raise MacaulayError(f"Macaulay search failed: {type(exc).__name__}") from None
                time.sleep(min(2 ** attempt, 30.0))
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** attempt, 30.0))
                continue
            if response.status_code != 200:
                raise MacaulayError(f"Macaulay search returned HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError:
                raise MacaulayError(self._not_json(taxon_code, response)) from None
        raise MacaulayError("Macaulay search kept failing after retries")

    @staticmethod
    def _not_json(taxon_code, response) -> str:
        """A browser challenge page is not transient, so it is not retried:
        the route that still works is a CSV exported by hand from the UI."""
        body = (getattr(response, "text", "") or "").lstrip()[:200].lower()
        if body.startswith("<") and "bot" in body:
            return ("Macaulay's search endpoint answered with a browser check, not JSON. "
                    f"Export the results as CSV from {CATALOG_URL.format(code=taxon_code)} "
                    "and pass --csv instead.")
        return "Macaulay search returned a non-JSON response"

    def assets(self, taxon_code, limit=None, should_stop=None, refresh=False):
        """Yield raw asset records, serving the cache before asking for more."""
        cache = AssetCache(self.cache_dir, taxon_code) if self.cache_dir else None
        if cache and refresh:
            cache.clear()

        seen = 0
        if cache:
            for asset in cache.read():
                if should_stop and should_stop():
                    return
                yield asset
                seen += 1
                if limit and seen >= limit:
                    return
            if cache.exhausted:
                return
            if seen and self.on_page:
                self.on_page(seen, cached=True)

        cursor = cache.cursor if cache else None
        while not limit or seen < limit:
            wanted = min(self.page_size, max(1, limit - seen)) if limit else self.page_size
            results = self._page(taxon_code, cursor, count=wanted)
            if not results:
                return
            cursor = results[-1].get("cursorMark")
            usable = [a for a in results if not a.get("restricted")]
            if cache:
                cache.append(usable, cursor)
            if self.on_page:
                self.on_page(len(usable), cached=False)
            for asset in usable:
                if should_stop and should_stop():
                    return
                yield asset
                seen += 1
                if limit and seen >= limit:
                    return
            if not cursor:
                return
            time.sleep(self.delay)


class MacaulaySource:
    """`query` is a path to an exported CSV, or a species slug / eBird taxon
    code to search for. Same count / fetch / normalize shape as Xeno-canto, so
    the runner and the store need no idea which one they hold."""

    id = "macaulay"

    def __init__(self, downloader=None, search=None, cache_dir=None, on_page=None):
        self.downloader = downloader or Downloader()
        self.search = search or MacaulaySearch(cache_dir=cache_dir, on_page=on_page)

    def count(self, query) -> int:
        """Only the CSV can be counted up front; the search API reports no total."""
        return len(read_catalogue(query)) if _is_catalogue(query) else 0

    def fetch(self, query, max_recordings, should_stop=None, refresh=False, **_):
        if not _is_catalogue(query):
            code = ebird_code(query) or query
            for asset in self.search.assets(code, limit=max_recordings,
                                            should_stop=should_stop, refresh=refresh):
                yield self.normalize_asset(asset)
            return
        rows = read_catalogue(query)
        if len(rows) >= EXPORT_CAP:
            print(f"   note: {len(rows)} rows is the export cap — the species may have "
                  "more, which needs a second export sliced by year or region", flush=True)
        for yielded, row in enumerate(rows):
            if should_stop and should_stop():
                return
            if yielded >= max_recordings:
                return
            yield self.normalize(row)

    @staticmethod
    def normalize_asset(asset: dict) -> dict:
        """One search-API result. `tags` (call, song, flight_call) is a
        controlled vocabulary, and userId a stable recordist key the CSV lacks."""
        asset_id = str(asset.get("assetId", ""))
        taxonomy = asset.get("taxonomy") or {}
        location = asset.get("location") or {}
        tags = [t for t in (asset.get("tags") or []) if t not in HOUSEKEEPING_TAGS]
        rating = asset.get("rating")
        return {
            "source": MacaulaySource.id,
            "source_ref": asset_id,
            "species": taxonomy.get("comName"),
            "call_type": "; ".join(tags) or None,
            "country": location.get("countryName"),
            "location": location.get("name") or location.get("locality"),
            "lat": _as_float(location.get("latitude")),
            "lng": _as_float(location.get("longitude")),
            "license": asset.get("licenseId") or ATTRIBUTION,
            "quality": f"{rating:.2f}" if isinstance(rating, (int, float)) else None,
            "length": None,
            "recordist": asset.get("userDisplayName"),
            "recordist_id": asset.get("userId"),
            "date": (asset.get("obsDt") or "")[:10] or None,
            "audio_url": ASSET_URL.format(asset=asset_id),
            "page_url": PAGE_URL.format(asset=asset_id),
            "raw": asset,
        }

    @staticmethod
    def normalize(row: dict) -> dict:
        asset = str(row.get(CATALOG_NUMBER, "")).strip()
        return {
            "source": MacaulaySource.id,
            "source_ref": asset,
            "species": (row.get("Common Name") or "").strip() or None,
            # Behaviors is free text and multi-valued ("Call; Flying"). Kept as recorded.
            "call_type": (row.get("Behaviors") or "").strip() or None,
            "country": row.get("Country") or None,
            "location": row.get("Locality") or None,
            "lat": _as_float(row.get("Latitude")),
            "lng": _as_float(row.get("Longitude")),
            "license": ATTRIBUTION,
            "quality": row.get("Average Community Rating") or None,
            "length": None,
            "recordist": (row.get("Recordist") or "").strip() or None,
            "recordist_id": None,
            "date": (row.get("Date") or "").strip() or None,
            "audio_url": ASSET_URL.format(asset=asset),
            "page_url": PAGE_URL.format(asset=asset),
            "raw": row,
        }

    def download(self, record, dest, on_bytes=None) -> bool:
        return self.downloader.fetch(record["audio_url"], dest, on_bytes=on_bytes)


def catalog_url(slug_or_code) -> str:
    return CATALOG_URL.format(code=ebird_code(slug_or_code) or slug_or_code)
