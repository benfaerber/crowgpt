"""The operator dashboard: the whole fleet, read-only, plus the bundle that renders it and the audio it plays."""

import logging
from pathlib import Path

from flask import abort, jsonify, request, send_file, send_from_directory

from ..stores.contributors import FLEET_ROLES

log = logging.getLogger(__name__)

#: The largest page a fleet route hands out. The dashboard asks for 200; an
#: unbounded ?limit= ran the full cross-table query for whoever asked.
MAX_PAGE = 1000


def page_limit() -> int:
    asked = request.args.get("limit", 200, type=int) or 200
    return max(1, min(asked, MAX_PAGE))


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    config = d.config
    contributors = d.contributors
    devices = d.devices
    families = d.families
    captures = d.captures
    media = d.media
    analysis = d.analysis
    quality = d.quality
    labels = d.labels
    observations = d.observations
    context = d.context
    sightings = d.sightings
    ai_descriptions = d.ai_descriptions
    dictations = d.dictations
    logs = d.logs
    board = d.board
    current_actor = d.current_actor
    owned_capture = d.owned_capture
    counts = d.counts

    # --- operator dashboard ---

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def current_admin() -> dict:
        contributor = current_operator()
        if contributor["role"] != "admin":
            abort(403, "admin role required")
        return contributor

    # From the package, not from this file: these routes moved into api/ and
    # "next to me" quietly became a directory that does not exist.
    react_dir = Path(__file__).resolve().parents[1] / "static" / "app"

    @app.get("/")
    def dashboard_page():
        """The operator dashboard.

        A built bundle rather than a served file, so a checkout that hasn't run
        the build has nothing to show. Say so plainly: the alternative is a bare
        404 on the fleet's only web view, which reads as "the server is broken".
        """
        if not (react_dir / "index.html").exists():
            return (
                "<h1>Dashboard not built</h1>"
                "<p>Run <code>make -C dashboard build</code>, "
                "or <code>make field</code>, which builds it for you.</p>",
                503,
            )
        return send_from_directory(react_dir, "index.html")

    @app.get("/app/<path:asset>")
    def dashboard_asset(asset):
        return send_from_directory(react_dir, asset)

    @app.get("/api/fleet/summary")
    def fleet_summary():
        current_operator()
        return jsonify({**board.fleet_summary(),
                        "config_version": config.current_version()})

    @app.get("/api/fleet/devices")
    def fleet_devices():
        current_operator()
        return jsonify(board.devices())

    @app.get("/api/fleet/contributors")
    def fleet_contributors():
        current_operator()
        return jsonify(board.contributors())

    @app.patch("/api/fleet/contributors/<int:contributor_id>")
    def update_contributor(contributor_id):
        """Change someone's role or suspend them — the admin half of the split.

        Deliberately admin-only and deliberately not able to *create* an admin
        from nothing: promotion to admin is done by `tools/admin.py`, on the box,
        because an HTTP route that mints administrators over plain http hands the
        fleet to whoever reaches it.
        """
        current_admin()
        b = request.get_json(silent=True) or {}
        if not contributors.get(contributor_id):
            abort(404, "contributor not found")
        try:
            result = None
            if b.get("role") is not None:
                if b["role"] == "admin":
                    abort(403, "admin is granted with tools/admin.py, not over the API")
                result = contributors.set_role(contributor_id, b["role"])
            if b.get("status") is not None:
                result = contributors.set_status(contributor_id, b["status"])
        except ValueError as error:
            abort(400, str(error))
        if result is None:
            abort(400, "nothing to change — pass role or status")
        return jsonify(result)

    @app.get("/api/fleet/relabel-queue")
    def fleet_relabel_queue():
        """Labels whose vocabulary changed after they were made.

        Not a to-do list the server generates on its own — it is a question
        only answerable because each label records which version of the
        vocabulary it was chosen from.
        """
        current_operator()
        return jsonify(board.relabel_queue(
            limit=page_limit()))

    @app.get("/api/fleet/logs")
    def fleet_logs():
        """What the phones have been saying.

        `level` selects that level and above, because "show me warnings" that
        hides errors is a trap rather than a filter.
        """
        current_operator()
        return jsonify(logs.recent(
            limit=page_limit(),
            level=request.args.get("level"),
            device_id=request.args.get("device_id", type=int),
            tag=request.args.get("tag"),
            search=request.args.get("q"),
        ))

    @app.get("/api/fleet/logs/summary")
    def fleet_log_summary():
        current_operator()
        return jsonify({"counts": logs.counts(), "tags": logs.tags()})

    @app.delete("/api/fleet/logs")
    def clear_logs():
        """Throw them away — the one table here where that is not a loss.

        Deliberately available, and deliberately not admin-only: the useful move
        after fixing something is to wipe the log and see whether it comes back,
        and an operator who cannot do that keeps reading the failure they
        already fixed.
        """
        current_operator()
        return jsonify({"deleted": logs.clear(
            device_id=request.args.get("device_id", type=int))})

    @app.get("/api/fleet/captures")
    def fleet_captures():
        current_operator()
        return jsonify(board.captures(limit=page_limit()))

    @app.get("/api/fleet/labels")
    def fleet_label_totals():
        current_operator()
        return jsonify(board.label_totals())

    @app.get("/api/fleet/semantics")
    def fleet_semantics():
        """Which calls co-occur with which witnessed situations.

        The question the whole project is for. Every other fleet view counts
        things; this one is the only one that could ever answer "what does a
        crow say about a dog", and it is deliberately blunt — co-occurrence, not
        inference. With a corpus this small it is a prompt for where to record
        next, not a finding.
        """
        current_operator()
        # Default to kept captures only: the corpus is mostly seeded and test
        # material, so the unfiltered matrix describes the pipeline rather than
        # any crow. ?all=1 shows everything, for checking the plumbing.
        return jsonify(board.call_context_matrix(
            kept_only=not request.args.get("all")))

    @app.get("/api/fleet/families")
    def fleet_families():
        """Every family across the fleet, with where and when it has been heard."""
        current_operator()
        return jsonify(board.families())

    @app.get("/api/fleet/families/<int:family_id>")
    def fleet_family_detail(family_id):
        """One family, examined: its captures, and what it is heard saying.

        The vocal profile is the reason this endpoint is worth having — it is the
        first view in which a *family* rather than a clip is the subject, which
        is what "this is family A in SLC" eventually needs to be answerable.
        """
        current_operator()
        family = board.family(family_id)
        if not family:
            abort(404, "family not found")
        return jsonify({
            "family": family,
            "captures": board.family_captures(family_id),
            "call_types": board.family_call_types(family_id),
        })

    @app.get("/api/fleet/captures/<int:capture_id>")
    def fleet_capture_detail(capture_id):
        current_operator()
        cap = board.capture(capture_id)
        if not cap:
            abort(404, "capture not found")
        return jsonify({
            "capture": cap,
            "media": board.media_for_capture(capture_id),
            "analysis": analysis.latest_calls_for_capture(capture_id),
            "quality": quality.for_capture(capture_id),
            "labels": labels.for_capture(capture_id),
            "observations": observations.for_capture(capture_id),
            "context": context.for_capture(capture_id),
            # Kept a separate key, not merged into "context". They are different
            # kinds of evidence and the dashboard must not be able to render one
            # as the other by accident.
            "sightings": sightings.for_capture(capture_id),
            # Machine-written, and a separate key for the same reason: it must
            # not be renderable as anything the recordist said.
            "ai_descriptions": ai_descriptions.for_capture(capture_id),
            # The recordist's own voice, machine-transcribed. Its own key rather
            # than folded into "observations" because until a human has read it
            # the words are his and the spelling is a guess — and the page must
            # not be able to render one as the other by accident. A confirmed
            # one is ALSO in "observations", which is what confirming means.
            "dictations": dictations.for_capture(capture_id),
        })

    @app.get("/api/media/<int:media_id>/raw")
    def media_raw(media_id):
        """Stream the stored audio so the dashboard can play it back.

        `?format=wav` renders a WAV instead, for the phone. It parses RIFF
        headers directly — to draw a waveform, to normalise playback, to crop
        before upload — so handing it the stored FLAC would leave a restored
        capture playable but flat and unboostable, failing quietly in three
        places at once. Browsers need no such help and get the stored bytes.
        """
        _, contributor = current_actor()
        m = media.get(media_id)
        if not m:
            abort(404, "media not found")
        owned_capture(m["capture_id"], contributor)
        wanted = request.args.get("format")
        if wanted == "wav" and m["kind"] == "audio" and m["format"] != "wav":
            try:
                return send_file(media.as_wav(m), mimetype="audio/wav",
                                 download_name=f"capture{m['capture_id']}.wav")
            except Exception:  # noqa: BLE001 — reported below, refused to the client
                # The 503 the client sees carries no detail on purpose; this
                # line is where the actual reason survives.
                log.exception("WAV render failed for media %s", media_id)
                abort(503, "could not render this capture as WAV")
        path = media.path(m)
        if not path.exists():
            abort(404, "media file missing on disk")
        # The kind decides the type, not a guess. Serving an mp4 as audio/mp4
        # makes a browser refuse to render it as video, which reads as "the file
        # is broken" rather than "the header is wrong".
        media_type = "video" if m["kind"] == "video" else "audio"
        return send_file(path, mimetype=f"{media_type}/{m['format']}",
                         download_name=f"capture{m['capture_id']}.{m['format']}")

