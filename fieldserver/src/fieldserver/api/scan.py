"""The promo's Scan page — a stranger uploads a photo, a recording or a video.

crowgpt.org is static and holds no secret, so this is the second tokenless
surface beside demo.py, and it is bounded the same way plus what an upload
adds:

  - a single-use Turnstile token per upload (action `demo-scan`), verified
    here whenever verification is required or a token is offered. The page
    sends it in the X-Turnstile-Token header, and it is checked before the
    body is parsed: a 40 MB form is otherwise the cost of every refusal.
    A token in the form is not read at all;
  - an allowance per address, and a cap on how many uploads may be waiting;
  - a size limit per kind, set on the request before any of it is read;
  - only formats the two workers open, decided from the file's extension;
  - the file is deleted when its worker finishes, the row an hour later, and
    the row is addressed by an unguessable id (stores/scans.py);
  - the one exception is the visitor's own: `keep=1`, from a box on the page
    that starts unticked, keeps the file as a contribution, up to a fixed
    budget of disk;
  - a kind is only offered while its worker is alive, so a server with no
    photo worker refuses photos instead of accepting them and never answering.

Lives under /api/demo/ so demo.py's CORS answer covers it: the promo's
origins, and nothing else of the API. NO WIRE_VERSION BUMP — the phone never
calls this.
"""

import threading

from flask import abort, jsonify, request

from ..core.throttle import Allowance
from ..core.turnstile import Turnstile, Unavailable
from ..stores.scans import FORMATS, MAX_BYTES, MAX_WAITING, SOUND_SECONDS, queue_of

ACTION = "demo-scan"

#: Uploads an address gets an hour. Each one is seconds of a worker's CPU.
SCANS_PER_HOUR = 12

#: Where the page puts its Turnstile token, so it can be checked first.
TOKEN_HEADER = "X-Turnstile-Token"

#: Room for the largest file plus the form around it.
MAX_REQUEST_BYTES = max(MAX_BYTES.values()) + 64 * 1024


def describe(scans, row) -> dict:
    """What the page needs about a scan, and nothing about the box."""
    body = {"id": row["public_id"], "kind": row["kind"], "state": row["state"]}
    if row["state"] == "done":
        body["result"] = row["result"]
        body["kept"] = bool(row["keep"])
    elif row["state"] == "failed":
        body["error"] = row["error"] or "could not read this file"
    else:
        body["ahead"] = scans.ahead_of(row)
        body["eta_seconds"] = scans.seconds_left(row)
    return body


def register(app, d) -> None:
    scans = d.scans
    uploads = Allowance(allowed=SCANS_PER_HOUR, per_seconds=3600)
    turnstile = Turnstile.from_env()
    verifying = threading.BoundedSemaphore(2)

    def coordinate(name):
        raw = (request.form.get(name) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            abort(400, f"{name} must be a number")

    def verify_visitor(token):
        if not (turnstile.required or token):
            return
        if not verifying.acquire(blocking=False):
            abort(503, "verification is busy; try again in a moment")
        try:
            if not turnstile.verify(token, request.remote_addr or "", action=ACTION):
                abort(403, "verification failed; refresh the page")
        except Unavailable:
            abort(503, "verification is unavailable")
        finally:
            verifying.release()

    @app.get("/api/demo/scan")
    def scan_config():
        if turnstile.required and not turnstile.configured:
            abort(503, "verification is unavailable")
        return jsonify({
            "kinds": {kind: scans.alive(queue_of(kind)) for kind in FORMATS},
            "formats": {kind: list(extensions) for kind, extensions in FORMATS.items()},
            "max_mb": {kind: size // (1024 * 1024) for kind, size in MAX_BYTES.items()},
            "sound_seconds": SOUND_SECONDS,
            "turnstile_site_key": turnstile.site_key if turnstile.configured else None,
            "turnstile_required": turnstile.required,
        })

    @app.post("/api/demo/scan")
    def scan_upload():
        request.max_content_length = MAX_REQUEST_BYTES
        caller = request.remote_addr or "?"
        # Everything that can refuse without the body does so first.
        if uploads.spent(caller):
            abort(429, "that is enough scans for one hour from one address")
        verify_visitor(request.headers.get(TOKEN_HEADER, ""))
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            abort(400, "attach the file as 'file'")
        latitude, longitude = coordinate("latitude"), coordinate("longitude")
        try:
            kind, storage_ref, path = scans.allocate(upload.filename)
        except ValueError as error:
            abort(400, str(error))
        queue = queue_of(kind)
        if not scans.alive(queue):
            abort(503, f"{kind} scanning is not available right now")
        if not uploads.spend(caller):
            abort(429, "that is enough scans for one hour from one address")
        scans.prune()
        if scans.waiting(queue) >= MAX_WAITING:
            abort(503, "the scanner is busy; try again in a minute")
        upload.save(path)
        try:
            row = scans.request(kind, storage_ref, latitude, longitude,
                                keep=request.form.get("keep") == "1")
        except ValueError as error:
            abort(400, str(error))
        return jsonify(describe(scans, row)), 202

    @app.get("/api/demo/scan/<public_id>")
    def scan_result(public_id):
        row = scans.get_public(public_id)
        if row is None:
            abort(404, "no such scan")
        return jsonify(describe(scans, row))
