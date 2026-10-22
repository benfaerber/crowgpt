"""Health and the served vocabulary. The only two routes anybody may call without a token — a phone needs the label set before it has enrolled, and every client polls health."""

from flask import jsonify, request

from ..core.build_info import BUILD


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    config = d.config

    # --- open endpoints ---

    @app.get("/api/health")
    def health():
        # `build` rides on health because that is what every client already
        # polls: the phone checks it before syncing and the dashboard on every
        # refresh, so neither needs a second round trip to know what it is
        # talking to.
        return jsonify({
            "ok": True,
            "config_version": config.current_version(),
            "build": BUILD,
        })

    @app.get("/api/config")
    def get_config():
        locale = request.args.get("locale", "en")
        since = request.args.get("since", type=int)
        version = config.current_version()
        if since is not None and since >= version:
            return "", 304
        return jsonify(config.get_config(locale))

