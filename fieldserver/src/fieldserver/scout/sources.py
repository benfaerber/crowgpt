"""Public-data clients for the scouting layer: iNaturalist and Overpass.

Both are injectable into ScoutLayerBuilder so tests run on canned payloads;
nothing below caches, because a scout build is a deliberate refresh.
"""

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

#: Both APIs are shared public infrastructure that sheds load with 429/5xx;
#: a scout build should shrug that off rather than die four fetches in.
RETRY_STATUSES = (429, 502, 503, 504)
RETRY_DELAYS_S = (10, 30)


def fetch_json(request, timeout):
    for delay in (*RETRY_DELAYS_S, None):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if delay is None or error.code not in RETRY_STATUSES:
                raise
        except urllib.error.URLError:
            if delay is None:
                raise
        time.sleep(delay)


@dataclass(frozen=True)
class Observation:
    lat: float
    lon: float
    date: str = ""
    photo: str = ""
    observer: str = ""


class INatClient:
    URL = "https://api.inaturalist.org/v1/observations"

    def __init__(self, timeout=60):
        self.timeout = timeout

    def _page(self, taxon, region, page, order_by=None):
        url = (f"{self.URL}?taxon_name={urllib.parse.quote(taxon)}"
               f"&nelat={region.north}&nelng={region.east}"
               f"&swlat={region.south}&swlng={region.west}"
               f"&quality_grade=research&per_page=200&page={page}")
        if order_by:
            url += f"&order_by={order_by}"
        return fetch_json(url, self.timeout)

    @staticmethod
    def _parse(obs):
        loc = obs.get("location")
        if not loc:
            return None
        lat, lon = (float(x) for x in loc.split(","))
        photos = obs.get("photos") or []
        # 'square' is the 75 px thumb; 'small' is ~240 px, right for a popup.
        # The phone loads it straight from iNat's CDN (the field server is
        # home-LAN only); archive_scout_photos.py keeps the server's copy.
        photo = (photos[0].get("url") or "").replace("square", "small") \
            if photos else ""
        return Observation(round(lat, 5), round(lon, 5),
                           obs.get("observed_on") or "", photo,
                           (obs.get("user") or {}).get("login", ""))

    def presence_points(self, taxon, region, max_pages=5):
        """(lat, lon) points, one vote per observer per ~275 m cell.

        Twenty uploads of the same resident birds by one devotee are one fact
        about birds and twenty about the devotee — measured 2026-08-21, when
        a single observer held 20 of 24 crow observations in the Taylorsville
        cluster that ranked four targets.
        """
        points, seen, page = [], set(), 1
        while True:
            payload = self._page(taxon, region, page)
            for raw in payload["results"]:
                obs = self._parse(raw)
                if not obs:
                    continue
                key = (obs.observer, round(obs.lat / 0.0025),
                       round(obs.lon / 0.0025))
                if key in seen:
                    continue
                seen.add(key)
                points.append((obs.lat, obs.lon))
            if page * 200 >= payload["total_results"] or page >= max_pages:
                return points
            page += 1

    def recent(self, taxon, region, cap=150):
        """The newest research-grade observations with date/photo/observer —
        what the map's predator pins show. Capped per species so the map
        stays a map rather than a murmuration of markers."""
        payload = self._page(taxon, region, 1, order_by="observed_on")
        parsed = (self._parse(raw) for raw in payload["results"])
        return [obs for obs in parsed if obs][:cap]


class EBirdClient:
    """The last 30 days beside iNat's history: crows seen THIS MORNING,
    counted ("n=6"), from the valley's very active checklist community. The
    recent-obs endpoint withholds observer names."""

    URL = "https://api.ebird.org/v2/data/obs/geo/recent"

    def __init__(self, api_key, timeout=30):
        self.api_key = api_key
        self.timeout = timeout

    def recent(self, species_code, region, back_days=30):
        lat = (region.south + region.north) / 2
        lon = (region.west + region.east) / 2
        half_height_km = (region.north - region.south) * 110.54 / 2
        half_width_km = ((region.east - region.west) * 111.32
                         * math.cos(math.radians(lat)) / 2)
        dist = min(50, math.ceil(math.hypot(half_height_km, half_width_km)))
        request = urllib.request.Request(
            f"{self.URL}/{species_code}?lat={lat:.4f}&lng={lon:.4f}"
            f"&dist={dist}&back={back_days}&includeProvisional=true",
            headers={"X-eBirdApiToken": self.api_key})
        observations = fetch_json(request, self.timeout)
        return [{"lat": round(obs["lat"], 5), "lon": round(obs["lng"], 5),
                 "date": (obs.get("obsDt") or "")[:16],
                 "count": obs.get("howMany") or 0}
                for obs in observations
                if obs.get("lat") is not None
                and region.contains(obs["lat"], obs["lng"])]


class OverpassClient:
    URL = "https://overpass-api.de/api/interpreter"
    FOOD_AMENITIES = ("fast_food", "restaurant", "waste_disposal",
                      "waste_transfer_station")

    def __init__(self, timeout=180):
        self.timeout = timeout

    def _query(self, query, agent="cawtalker-scout"):
        request = urllib.request.Request(
            self.URL, data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": agent})
        return fetch_json(request, self.timeout)

    def habitat(self, region):
        """(green, water, food) point lists, each (lat, lon, name)."""
        west, south, east, north = region.bbox
        bbox = f"({south},{west},{north},{east})"
        payload = self._query(f"""[out:json][timeout:90];
(
  way["leisure"~"park|golf_course"]{bbox};
  way["landuse"~"cemetery|grass|recreation_ground"]{bbox};
  relation["leisure"="park"]{bbox};
);
out center;
(
  way["waterway"~"river|stream|canal"]{bbox};
  way["natural"="water"]{bbox};
);
out center;
(
  node["amenity"~"fast_food|restaurant|waste_disposal|waste_transfer_station"]{bbox};
  node["shop"="supermarket"]{bbox};
  node["tourism"="picnic_site"]{bbox};
  way["landuse"="landfill"]{bbox};
  way["amenity"~"fast_food|restaurant"]{bbox};
  way["shop"="supermarket"]{bbox};
);
out center;""")
        green, water, food = [], [], []
        for element in payload["elements"]:
            center = element.get("center") or (
                {"lat": element.get("lat"), "lon": element.get("lon")})
            if not center.get("lat"):
                continue
            tags = element.get("tags", {})
            point = (center["lat"], center["lon"], tags.get("name", ""))
            if (tags.get("amenity") in self.FOOD_AMENITIES
                    or tags.get("shop") == "supermarket"
                    or tags.get("tourism") == "picnic_site"
                    or tags.get("landuse") == "landfill"):
                food.append(point)
            elif tags.get("waterway") or tags.get("natural") == "water":
                water.append(point)
            else:
                green.append(point)
        return green, water, food

    def rail(self, region, fallback_color="#5c6bc0"):
        """Rail reference geometry, each route in its own OSM colour.

        Ben reads the city by its rail lines. A way shared by several routes
        (the downtown trunk) keeps the first route's colour — a glance needs
        the corridor, not a braided transit diagram. Which route classes draw
        is the region's call: the valley wants TRAX and the S-Line, a county
        with no light rail wants `train` for FrontRunner.
        """
        west, south, east, north = region.bbox
        # The bbox on way(r) matters: a matched relation hands over ALL its
        # member ways, and the California Zephyr crosses this box on its way
        # from Chicago to the Bay — 2 MB of Nebraska in the phone's layer
        # until the ways were clipped too.
        payload = self._query(
            f'[out:json][timeout:120];'
            f'relation["route"~"{region.rail_routes}"]'
            f'({south},{west},{north},{east});'
            f'out body;way(r)({south},{west},{north},{east});out geom;')
        ways = {e["id"]: [[round(p["lat"], 5), round(p["lon"], 5)]
                          for p in e.get("geometry", [])]
                for e in payload["elements"] if e["type"] == "way"}
        relations = sorted(
            (e for e in payload["elements"] if e["type"] == "relation"),
            key=lambda r: r.get("tags", {}).get("ref", ""))
        segments, claimed = [], set()
        for relation in relations:
            color = relation.get("tags", {}).get("colour", fallback_color)
            for member in relation.get("members", []):
                if member["type"] != "way" or member["ref"] in claimed:
                    continue
                coords = ways.get(member["ref"], [])
                if len(coords) >= 2:
                    claimed.add(member["ref"])
                    segments.append({"color": color, "coords": coords})
        return segments
