"""Add the TRAX tracks to the scout layer, for bearings.

Ben reads the city by its rail lines, so the map carries them as reference
geometry in each route's own color — the Blue, Red and Green Lines and the
S-Line, with colors from the OSM route relations themselves. A way shared
by several routes (the downtown trunk) keeps the first route's color; a
glance needs the corridor, not a braided transit diagram.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
WEST, SOUTH, EAST, NORTH = -112.05, 40.50, -111.797, 40.90
FALLBACK = "#5c6bc0"


def overpass(query):
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "cawtalker-0084/rail"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def fetch_rail():
    payload = overpass(
        f'[out:json][timeout:120];'
        f'relation["route"~"light_rail|tram"]({SOUTH},{WEST},{NORTH},{EAST});'
        f'out body;way(r);out geom;')
    ways = {e["id"]: [[round(p["lat"], 5), round(p["lon"], 5)]
                      for p in e.get("geometry", [])]
            for e in payload["elements"] if e["type"] == "way"}
    relations = sorted(
        (e for e in payload["elements"] if e["type"] == "relation"),
        key=lambda r: r.get("tags", {}).get("ref", ""))
    segments, claimed = [], set()
    for relation in relations:
        tags = relation.get("tags", {})
        color = tags.get("colour", FALLBACK)
        name = tags.get("name", "?")
        count = 0
        for member in relation.get("members", []):
            if member["type"] != "way" or member["ref"] in claimed:
                continue
            coords = ways.get(member["ref"], [])
            if len(coords) >= 2:
                claimed.add(member["ref"])
                segments.append({"color": color, "coords": coords})
                count += 1
        print(f"{name}: {count} ways, {color}")
    return segments


def main():
    segments = fetch_rail()
    layer = json.loads((OUT / "scout_layer.json").read_text())
    layer["rail"] = segments
    (OUT / "scout_layer.json").write_text(json.dumps(layer) + "\n")
    points = sum(len(s["coords"]) for s in segments)
    print(f"{len(segments)} rail segments, {points} points")


if __name__ == "__main__":
    main()
