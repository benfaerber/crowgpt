"""The tall-trees overlay — scouting data the map screen draws.

Server-served reference data, not app-bundled, so a regenerated canopy
analysis (experiment 0083 today; new data or a different height floor
tomorrow) reaches every phone without an app release. Published by
`tools/publish_trees.py` into `instance/trees.geojson`; absent means 404 and
the app simply doesn't offer the layer.

NO WIRE_VERSION BUMP. The wire number guards what the server can *store* of
what phones send; a read-only GET the app degrades gracefully without is
tooling, and an earlier version of this rule already cost one false
incompatibility warning.
"""

from flask import abort, send_file


def register(app, d) -> None:
    current_actor = d.current_actor
    trees_path = d.instance_dir / "trees.geojson"

    def get_trees():
        current_actor()
        if not trees_path.exists():
            abort(404, "no tree layer published — see tools/publish_trees.py")
        return send_file(trees_path, mimetype="application/geo+json",
                         conditional=True)

    app.add_url_rule("/api/trees", "get_trees", get_trees, methods=["GET"])
