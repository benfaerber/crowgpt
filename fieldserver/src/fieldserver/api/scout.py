"""The scouting layer — 0084's ranked targets and the owls that shaped them.

Same served-artifact pattern as trees.py, restated rather than shared, for
the dictations reason: two layers that happen to rhyme should not be coupled
by an import. Published by `tools/publish_scout.py` into
`instance/scout.json`; absent means 404 and the app doesn't offer the layer.

NO WIRE_VERSION BUMP — read-only GET the app degrades gracefully without.
"""

import math

from flask import abort, jsonify, request, send_file

VISIT_KINDS = ("tree", "target", "spot")
VISIT_OUTCOMES = ("crows", "nothing")

M_PER_LAT = 110_540


def register(app, d) -> None:
    current_actor = d.current_actor
    scout_visits = d.scout_visits
    scout_path = d.instance_dir / "scout.json"
    grid_dir = d.instance_dir / "scout_grid"

    def get_scout():
        current_actor()
        if not scout_path.exists():
            abort(404, "no scout layer published — see tools/publish_scout.py")
        return send_file(scout_path, mimetype="application/json",
                         conditional=True)

    def get_scout_spots():
        """The best cells inside a circle the recordist drew on the map.

        Answered from the score grids the builder persists beside the
        layer (instance/scout_grid/<region>.npz) — a lookup over surfaces
        already computed, not a rebuild. A circle outside every scouted
        region gets an empty list and a note, not an error: the map drew
        the circle in good faith.
        """
        current_actor()
        import numpy as np
        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except (KeyError, ValueError):
            abort(400, "lat and lon are required numbers")
        radius = min(max(float(request.args.get("radius_m", 2000)), 200), 8000)
        count = min(max(int(request.args.get("count", 5)), 1), 12)

        candidates, greens = [], []
        for path in sorted(grid_dir.glob("*.npz")) if grid_dir.exists() else []:
            z = np.load(path)
            lats, lons, score = z["lats"], z["lons"], z["score"]
            m_per_lon = 111_320 * math.cos(math.radians(float(lats.mean())))
            dy = (lats - lat) * M_PER_LAT
            dx = (lons - lon) * m_per_lon
            inside = ((dy[:, None] ** 2 + dx[None, :] ** 2) <= radius * radius) \
                & (score > 0)
            if inside.any():
                names = [k[4:] for k in z.files if k.startswith("sig_")]
                for j, i in zip(*(a.tolist() for a in inside.nonzero())):
                    candidates.append({
                        "lat": round(float(lats[j]), 5),
                        "lon": round(float(lons[i]), 5),
                        "score": round(float(score[j, i]), 3),
                        "region": path.stem,
                        "signals": {n: round(float(z["sig_" + n][j, i]), 2)
                                    for n in names},
                    })
            greens.append((z["green_lat"], z["green_lon"], z["green_name"],
                           m_per_lon))
        if not candidates:
            return jsonify({"spots": [], "radius_m": radius,
                            "note": "outside the scouted regions"})

        # Greedy with separation, like the published targets: five spots
        # should be five places, and a bigger circle deserves wider spacing.
        separation = max(400.0, radius / 5)
        m_per_lon_here = 111_320 * math.cos(math.radians(lat))
        candidates.sort(key=lambda c: -c["score"])
        picked = []
        for c in candidates:
            if len(picked) >= count:
                break
            if any(math.hypot((c["lat"] - p["lat"]) * M_PER_LAT,
                              (c["lon"] - p["lon"]) * m_per_lon_here)
                   < separation for p in picked):
                continue
            picked.append(c)
        for rank, c in enumerate(picked, 1):
            c["rank"] = rank
            c["near"] = ""
            for glat, glon, gname, m_per_lon in greens:
                if not len(glat):
                    continue
                dist = np.hypot((glat - c["lat"]) * M_PER_LAT,
                                (glon - c["lon"]) * m_per_lon)
                best = int(dist.argmin())
                if dist[best] < 600:
                    c["near"] = str(gname[best])
                    break
        return jsonify({"spots": picked, "radius_m": radius})

    def create_scout_visit():
        device, contributor = current_actor()
        body = request.get_json(silent=True) or {}
        for key in ("client_uuid", "latitude", "longitude", "visited_at"):
            if not body.get(key):
                abort(400, f"{key} is required")
        if body.get("kind") not in VISIT_KINDS:
            abort(400, f"kind must be one of: {', '.join(VISIT_KINDS)}")
        if body.get("outcome") not in VISIT_OUTCOMES:
            abort(400, f"outcome must be one of: {', '.join(VISIT_OUTCOMES)}")
        row = scout_visits.record(
            body["client_uuid"], body["kind"], body["latitude"],
            body["longitude"], body["outcome"], body["visited_at"],
            note=(body.get("note") or "").strip() or None,
            contributor_id=contributor["id"], device_id=device["id"])
        return jsonify(row), 201

    def list_scout_visits():
        current_actor()
        return jsonify(scout_visits.list())

    app.add_url_rule("/api/scout", "get_scout", get_scout, methods=["GET"])
    app.add_url_rule("/api/scout/spots", "get_scout_spots", get_scout_spots,
                     methods=["GET"])
    app.add_url_rule("/api/scout/visits", "create_scout_visit",
                     create_scout_visit, methods=["POST"])
    app.add_url_rule("/api/scout/visits", "list_scout_visits",
                     list_scout_visits, methods=["GET"])
