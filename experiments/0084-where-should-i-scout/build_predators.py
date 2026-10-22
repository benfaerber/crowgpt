"""Add per-species predator points + inline icons to the scout layer.

The icon test Ben asked for: the simple Great Horned head-style beside the
detailed full-body set, on the phone, over real streets. Icons ride inside
the layer as 64 px PNG data-URIs (~6 KB each), so future icon changes are a
republish, never a rebuild. Each species is capped so the test map stays a
map rather than a murmuration of markers.
"""
import base64
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
IMAGES = REPO / "images"
WEST, SOUTH, EAST, NORTH = -112.05, 40.50, -111.797, 40.90
CAP = 150

#: species -> (icon asset, style note for the in-field comparison)
SPECIES = {
    "Bubo virginianus": ("owl-icon", "detailed full-body"),
    "Megascops kennicottii": ("owl-icon", "detailed full-body"),
    "Buteo jamaicensis": ("hawk-icon", "detailed full-body"),
    # Kestrels were here until 2026-08-20; removed on Ben's call — a 110 g
    # vole-falcon threatens no crow (the raiding runs the other way), so a
    # kestrel sighting says nothing a scout can use. The drawn icon stays in
    # images/ for whenever a kestrel layer is wanted for its own sake.
    "Falco peregrinus": ("peregrine-icon", "detailed full-body"),
    # Icon None = purple dot until Ben draws one. Cooper's has carried a score
    # penalty since day one but was invisible here — a penalty you can't see
    # on the map is a number arguing with nothing. Ravens raid crow nests and
    # get mobbed; magpies threaten nobody but mark good corvid habitat.
    # Ben's 2026-08-20 batch, circles stripped, riding as cached PNGs in the
    # layer (images/*.png are the masters; no SVG trace for these three). The
    # raven barks on purpose — his call, "easy to tell apart and more agro".
    "Accipiter cooperii": ("coopers-hawk-icon", "detailed full-body"),
    "Astur cooperii": ("coopers-hawk-icon", "detailed full-body"),
    "Corvus corax": ("raven-icon", "detailed, barking"),
    "Pica hudsonia": ("magpie-icon", "detailed full-body"),
}
#: Community crow sightings ride the same list, flagged so the map can say
#: plainly "someone else's crow": they answer "where have crows been seen",
#: while Ben's own captures stay the full-colour markers with family glows.
CROW_TAXON = "Corvus brachyrhynchos"

COMMON = {
    "Bubo virginianus": "Great Horned Owl",
    "Megascops kennicottii": "Western Screech-Owl",
    "Buteo jamaicensis": "Red-tailed Hawk",
    "Falco peregrinus": "Peregrine Falcon",
    "Accipiter cooperii": "Cooper's Hawk",
    "Astur cooperii": "Cooper's Hawk",
    "Corvus corax": "Common Raven",
    "Pica hudsonia": "Black-billed Magpie",
}


def fetch(taxon):
    url = ("https://api.inaturalist.org/v1/observations"
           f"?taxon_name={urllib.parse.quote(taxon)}"
           f"&nelat={NORTH}&nelng={EAST}&swlat={SOUTH}&swlng={WEST}"
           "&quality_grade=research&per_page=200&order_by=observed_on")
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    points = []
    for obs in payload["results"]:
        loc = obs.get("location")
        if loc:
            lat, lon = (float(x) for x in loc.split(","))
            photos = obs.get("photos") or []
            # 'square' is the 75 px thumb; 'small' is ~240 px, right for a
            # popup. The phone loads it straight from iNat's CDN (the field
            # server is home-LAN only), and archive_scout_photos.py keeps the
            # server's own copy for the record.
            photo = (photos[0].get("url") or "").replace("square", "small") \
                if photos else ""
            # The date rides along: a 2020 owl and a last-week owl are very
            # different facts to someone deciding where to walk tonight.
            points.append((round(lat, 5), round(lon, 5),
                           obs.get("observed_on") or "", photo,
                           (obs.get("user") or {}).get("login", "")))
    return points[:CAP]


def icon_data_uri(name):
    import cairosvg
    png = cairosvg.svg2png(url=str(IMAGES / f"{name}.svg"), output_width=64)
    return "data:image/png;base64," + base64.b64encode(png).decode()


def main():
    layer = json.loads((OUT / "scout_layer.json").read_text())
    # Reuse the data-URIs already riding the layer; rasterising needs cairosvg
    # and only genuinely new icons should demand it.
    cached = layer.get("icons", {})
    icons, predators = {}, []

    def want_icon(name):
        if name and name not in icons:
            icons[name] = cached.get(name) or icon_data_uri(name)

    for taxon, (icon, style) in SPECIES.items():
        want_icon(icon)
        points = fetch(taxon)
        for lat, lon, date, photo, by in points:
            predators.append({"lat": lat, "lon": lon, "icon": icon,
                              "species": COMMON[taxon], "style": style,
                              "date": date, "photo": photo, "by": by})
        print(f"{COMMON[taxon]}: {len(points)} points ({style})")
    want_icon("crow-icon")
    crows = fetch(CROW_TAXON)
    for lat, lon, date, photo, by in crows:
        predators.append({"lat": lat, "lon": lon, "icon": "crow-icon",
                          "species": "American Crow", "community": True,
                          "date": date, "photo": photo, "by": by})
    print(f"American Crow (community): {len(crows)} points")
    # Cooper's rides under two taxon names (iNat's Accipiter -> Astur move)
    # and both return the same observations.
    seen, unique = set(), []
    for p in predators:
        key = (p["species"], p["lat"], p["lon"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    predators = unique
    layer["predators"] = predators
    layer["icons"] = icons
    (OUT / "scout_layer.json").write_text(json.dumps(layer) + "\n")
    total = sum(len(v) for v in icons.values()) // 1024
    print(f"{len(predators)} predators, {len(icons)} icons (~{total} KB inline)")


if __name__ == "__main__":
    main()
