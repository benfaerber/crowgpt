"""crowgpt.org's traffic, for the dashboard's Traffic page.

Read from the rows the traffic worker writes; this process never calls
Cloudflare, so opening the page costs nothing and works with the worker down.
Dashboard surface only, so no WIRE_VERSION bump.
"""

from datetime import datetime, timedelta, timezone

from flask import abort, jsonify, request

from ..core.traffic import RETENTION_DAYS
from ..stores.contributors import FLEET_ROLES

DEFAULT_DAYS = 30
MAX_DAYS = 366


def register(app, d) -> None:
    current_actor = d.current_actor
    traffic = d.traffic

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    @app.get("/api/traffic")
    def traffic_days():
        """Each day's summary over the last `days` UTC days, today included."""
        current_operator()
        days = max(1, min(request.args.get("days", DEFAULT_DAYS, type=int), MAX_DAYS))
        first = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
        return jsonify({
            "days": traffic.since(first),
            "first": first.isoformat(),
            "last_fetched": traffic.last_fetched(),
            "retention_days": RETENTION_DAYS,
        })
