"""The labelling desk for a kept scan, and the operator's view of the pile.

Two halves, like access.py.

The visitor's, under /label and /api/scan-desk: the page is the phone's own
labelling screen compiled for a browser (mobile/web), and the routes are what
that screen's services call. No token. The link carries the contribution's
unguessable `public_id`, which is the whole credential and opens one
recording. Same origin as the page, so there is no CORS to answer.

What bounds a tokenless write surface:

  - an allowance of writes per address;
  - a fixed ceiling of labels and context rows per recording (the store's);
  - every call type, caller role and context key is checked against the
    served vocabulary, so nothing free-text is stored at all;
  - a promoted recording is closed: its answers were carried onto a capture,
    and a later edit here would reach nobody.

The operator's, under /api/fleet/scan-contributions: list, listen, promote to
a capture (core/promotion.py), or delete.

NO WIRE_VERSION BUMP: the phone never calls any of this.
"""

import re
from pathlib import Path

from flask import abort, jsonify, request, send_from_directory, send_file

from ..core.promotion import NotPromotable, ScanPromotion
from ..core.throttle import Allowance
from ..core.transcode import TranscodeError
from ..stores.contributors import FLEET_ROLES
from ..stores.scan_desk import DeskFull, ScanDeskStore

DESK_DIR = Path(__file__).resolve().parents[1] / "static" / "label"

#: Taps, not uploads: a visitor working a ninety-second recording makes a few
#: dozen. This is what a script gets instead.
WRITES_PER_HOUR = 600

UUID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

LABELLED_KINDS = ("audio", "video")

MIMETYPES = {
    "wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac",
    "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg", "flac": "audio/flac",
    "mp4": "video/mp4", "mov": "video/quicktime", "m4v": "video/mp4",
    "webm": "video/webm", "mkv": "video/x-matroska",
}

NOT_BUILT = (
    "<h1>Labelling desk not built</h1>"
    "<p>Run <code>make -C mobile web-desk</code>, "
    "or <code>make field</code>, which builds it for you.</p>"
)


def register(app, d) -> None:
    config = d.config
    current_actor = d.current_actor
    desk = ScanDeskStore(d.scans.db_path, d.scans.kept_dir)
    promotion = ScanPromotion(desk, config, d.contributors, d.devices, d.captures, d.media,
                              d.labels, d.context, d.analysis)
    writes = Allowance(allowed=WRITES_PER_HOUR, per_seconds=3600)

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def contribution_for(public_id) -> dict:
        row = desk.by_public_id(public_id)
        if row is None or row["kind"] not in LABELLED_KINDS:
            abort(404, "no such recording")
        return row

    def writable(public_id) -> dict:
        row = contribution_for(public_id)
        if row["promoted_capture_id"] is not None:
            abort(409, "this recording has been reviewed and its labels are final")
        if not writes.spend(request.remote_addr or "?"):
            abort(429, "that is enough changes for one hour from one address")
        return row

    def client_uuid(value) -> str:
        if not UUID.match(value or ""):
            abort(400, "not an id this desk issues")
        return value

    def span(body) -> tuple[float, float]:
        try:
            start, end = float(body["start_sec"]), float(body["end_sec"])
        except (KeyError, TypeError, ValueError):
            abort(400, "start_sec and end_sec must be numbers")
        if not 0 <= start < end <= 24 * 3600:
            abort(400, "a span starts at or after zero and ends after it starts")
        return start, end

    def optional_span(body) -> tuple[float | None, float | None]:
        if body.get("start_sec") is None and body.get("end_sec") is None:
            return None, None
        return span(body)

    def audio(row):
        path = desk.path(row)
        if not path.exists():
            abort(404, "the file is gone")
        return send_file(path, mimetype=MIMETYPES.get(path.suffix.lower().lstrip(".")),
                         conditional=True, max_age=0)

    def answers(row) -> dict:
        return {"labels": desk.labels(row["id"]), "context": desk.context(row["id"]),
                "silent_confirmed_at": row["silent_confirmed_at"]}

    # --- the page --------------------------------------------------------------

    @app.get("/label/<public_id>")
    def scan_desk_page(public_id):
        if not (DESK_DIR / "index.html").exists():
            return NOT_BUILT, 503
        return send_from_directory(DESK_DIR, "index.html", max_age=0)

    @app.get("/label/assets/<path:asset>")
    def scan_desk_asset(asset):
        return send_from_directory(DESK_DIR / "assets", asset)

    # --- the visitor's routes ----------------------------------------------------

    @app.get("/api/scan-desk/<public_id>")
    def scan_desk(public_id):
        row = contribution_for(public_id)
        result = row["result"] or {}
        return jsonify({
            "id": row["public_id"], "kind": row["kind"], "created_at": row["created_at"],
            "duration_sec": result.get("duration_sec"),
            "waveform": result.get("waveform") or [],
            "calls": result.get("calls") or [],
            "truncated": bool(result.get("truncated")),
            "closed": row["promoted_capture_id"] is not None,
            "audio_url": f"/api/scan-desk/{row['public_id']}/audio",
            "config": config.get_config(request.args.get("locale", "en")),
            **answers(row),
        })

    @app.get("/api/scan-desk/<public_id>/audio")
    def scan_desk_audio(public_id):
        return audio(contribution_for(public_id))

    @app.put("/api/scan-desk/<public_id>/labels/<label_uuid>")
    def scan_desk_put_label(public_id, label_uuid):
        request.max_content_length = 4096
        row = writable(public_id)
        body = request.get_json(silent=True) or {}
        call_type = body.get("call_type")
        if not config.label_exists(call_type):
            abort(400, f"unknown call type '{call_type}'")
        start, end = span(body)
        try:
            label = desk.put_label(row["id"], client_uuid(label_uuid), start, end, call_type,
                                   from_detection=bool(body.get("from_detection")),
                                   config_version=config.current_version())
        except DeskFull as full:
            abort(409, str(full))
        return jsonify(label)

    @app.patch("/api/scan-desk/<public_id>/labels/<label_uuid>")
    def scan_desk_set_caller(public_id, label_uuid):
        request.max_content_length = 4096
        row = writable(public_id)
        caller_role = (request.get_json(silent=True) or {}).get("caller_role")
        if caller_role is not None and not config.caller_role_exists(caller_role):
            abort(400, f"unknown caller role '{caller_role}'")
        label = desk.set_caller(row["id"], client_uuid(label_uuid), caller_role)
        if label is None:
            abort(404, "no such label")
        return jsonify(label)

    @app.delete("/api/scan-desk/<public_id>/labels/<label_uuid>")
    def scan_desk_delete_label(public_id, label_uuid):
        row = writable(public_id)
        desk.delete_label(row["id"], client_uuid(label_uuid))
        return "", 204

    @app.put("/api/scan-desk/<public_id>/context/<event_uuid>")
    def scan_desk_put_context(public_id, event_uuid):
        request.max_content_length = 4096
        row = writable(public_id)
        body = request.get_json(silent=True) or {}
        key = body.get("key")
        if not config.context_exists(key):
            abort(400, f"unknown context '{key}'")
        label_uuid = body.get("label_uuid")
        start, end = optional_span(body)
        try:
            event = desk.put_context(
                row["id"], client_uuid(event_uuid), key,
                label_uuid=client_uuid(label_uuid) if label_uuid else None,
                start_sec=start, end_sec=end, config_version=config.current_version())
        except LookupError as missing:
            abort(404, str(missing))
        except DeskFull as full:
            abort(409, str(full))
        return jsonify(event)

    @app.delete("/api/scan-desk/<public_id>/context/<event_uuid>")
    def scan_desk_delete_context(public_id, event_uuid):
        row = writable(public_id)
        desk.delete_context(row["id"], client_uuid(event_uuid))
        return "", 204

    @app.post("/api/scan-desk/<public_id>/silent")
    def scan_desk_silent(public_id):
        request.max_content_length = 4096
        row = writable(public_id)
        silent = bool((request.get_json(silent=True) or {}).get("silent"))
        if silent and desk.labels(row["id"]):
            abort(409, "this recording has labelled calls, so it is not silent")
        return jsonify(answers(desk.confirm_silent(row["id"], silent)))

    # --- the operator's routes ---------------------------------------------------

    def operator_view(row, detail=False) -> dict:
        result = row["result"] or {}
        out = {
            "id": row["id"], "kind": row["kind"], "bytes": row["bytes"],
            "latitude": row["latitude"], "longitude": row["longitude"],
            "created_at": row["created_at"],
            "duration_sec": result.get("duration_sec"),
            "call_count": len(result.get("calls") or []),
            "silent_confirmed_at": row["silent_confirmed_at"],
            "promoted_capture_id": row["promoted_capture_id"],
            "desk_url": (request.url_root.rstrip("/") + f"/label/{row['public_id']}"
                         if row["public_id"] and row["kind"] in LABELLED_KINDS else None),
        }
        if detail:
            out.update(result=result, labels=desk.labels(row["id"]),
                       context=desk.context(row["id"]))
        else:
            out.update(label_count=row["label_count"], context_count=row["context_count"])
        return out

    def owned(contribution_id) -> dict:
        current_operator()
        row = desk.get(contribution_id)
        if row is None:
            abort(404, "no such contribution")
        return row

    @app.get("/api/fleet/scan-contributions")
    def list_scan_contributions():
        current_operator()
        return jsonify({"contributions": [operator_view(row) for row in desk.list_all()]})

    @app.get("/api/fleet/scan-contributions/<int:contribution_id>")
    def get_scan_contribution(contribution_id):
        return jsonify(operator_view(owned(contribution_id), detail=True))

    @app.get("/api/fleet/scan-contributions/<int:contribution_id>/file")
    def scan_contribution_file(contribution_id):
        return audio(owned(contribution_id))

    @app.post("/api/fleet/scan-contributions/<int:contribution_id>/promote")
    def promote_scan_contribution(contribution_id):
        row = owned(contribution_id)
        try:
            capture = promotion.promote(row)
        except (NotPromotable, TranscodeError) as refused:
            abort(409, str(refused))
        return jsonify({"capture_id": capture["id"],
                        "contribution": operator_view(desk.get(contribution_id), detail=True)})

    @app.delete("/api/fleet/scan-contributions/<int:contribution_id>")
    def delete_scan_contribution(contribution_id):
        owned(contribution_id)
        desk.delete(contribution_id)
        return "", 204
