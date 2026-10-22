"""Fresh eBird sightings into the scout layer, beside iNat's history.

iNat gave the layer years-old presence with photos; eBird gives the last 30
days — crows seen THIS MORNING, counted ("n=6"), from the valley's very
active checklist community. Both ride the predators list: iNat rows keep
their photos and observer logins, eBird rows carry date and count with
by="eBird" (the recent-obs endpoint withholds observer names). Idempotent:
each run replaces the previous eBird rows and leaves iNat's alone.

Key: EBIRD_API_KEY in fieldserver/instance/secrets.env (quotes tolerated).
"""
import json
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CENTER = (40.70, -111.92)
RADIUS_KM = 25
BACK_DAYS = 30

#: eBird species code -> (display species, icon, community)
SPECIES = {
    "amecro": ("American Crow", "crow-icon", True),
    "grhowl": ("Great Horned Owl", "owl-icon", False),
    "wesowl1": ("Western Screech-Owl", "owl-icon", False),
    "rethaw": ("Red-tailed Hawk", "hawk-icon", False),
    "coohaw": ("Cooper's Hawk", "coopers-hawk-icon", False),
    "perfal": ("Peregrine Falcon", "peregrine-icon", False),
    "comrav": ("Common Raven", "raven-icon", False),
    "bkbmag1": ("Black-billed Magpie", "magpie-icon", False),
}


def api_key():
    for line in (REPO / "fieldserver" / "instance" / "secrets.env").open():
        line = line.strip().removeprefix("export ")
        if line.startswith("EBIRD_API_KEY="):
            return line.split("=", 1)[1].strip('"').strip("'")
    raise SystemExit("EBIRD_API_KEY not in fieldserver/instance/secrets.env")


def fetch(code, key):
    url = ("https://api.ebird.org/v2/data/obs/geo/recent/" + code
           + f"?lat={CENTER[0]}&lng={CENTER[1]}&dist={RADIUS_KM}"
           + f"&back={BACK_DAYS}&includeProvisional=true")
    request = urllib.request.Request(url, headers={"X-eBirdApiToken": key})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    key = api_key()
    layer = json.loads((OUT / "scout_layer.json").read_text())
    kept = [p for p in layer["predators"] if p.get("src") != "ebird"]
    added = []
    for code, (species, icon, community) in SPECIES.items():
        observations = fetch(code, key)
        for obs in observations:
            if obs.get("lat") is None:
                continue
            entry = {
                "lat": round(obs["lat"], 5), "lon": round(obs["lng"], 5),
                "icon": icon, "species": species, "src": "ebird",
                "date": (obs.get("obsDt") or "")[:16],
                "count": obs.get("howMany") or 0,
                "by": "eBird", "photo": "",
            }
            if community:
                entry["community"] = True
            added.append(entry)
        print(f"{species}: {len(observations)} in the last {BACK_DAYS} days")
    layer["predators"] = kept + added
    (OUT / "scout_layer.json").write_text(json.dumps(layer) + "\n")
    print(f"{len(kept)} historical (iNat) + {len(added)} fresh (eBird) sightings")


if __name__ == "__main__":
    main()
