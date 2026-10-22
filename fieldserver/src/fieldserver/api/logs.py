"""What the phone says about itself, pushed in batches when it can reach us."""

from flask import abort, jsonify, request


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    logs = d.logs
    current_actor = d.current_actor

    # --- the phone's own log ---

    @app.post("/api/logs")
    def push_logs():
        """Take a batch of log lines from a handset.

        Answers with the client uuids it now holds, so the phone knows exactly
        which lines to mark sent. A count would not do: a batch that partly
        landed would either repeat forever or lose its tail.

        Never 4xx for a bad line. A log push failing is the worst possible time
        to be strict — the lines being rejected are, by definition, from a phone
        that is already having a bad day, and losing them to a validation error
        loses the evidence. Unknown levels become `info`, over-long messages are
        clipped, and only a missing idempotency key is refused.
        """
        device, contributor = current_actor()
        b = request.get_json(silent=True) or {}
        entries = b.get("entries")
        if not isinstance(entries, list):
            abort(400, "entries must be a list")
        return jsonify(logs.record(
            device_id=device["id"], contributor_id=contributor["id"],
            entries=entries[:500],
            app_version=request.headers.get("X-App-Version", type=int),
            app_commit=request.headers.get("X-App-Commit"),
        ))

