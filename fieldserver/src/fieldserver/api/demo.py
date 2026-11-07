"""Live CrowGPT on the promo page — the one surface a stranger may generate from.

crowgpt.org is a static page and can hold no secret. The browser presents a
single-use Turnstile token, which this server verifies. Other bounds remain:

  - a fixed menu (stores/demo.py): the visitor picks an item, never a model,
    a call type or a seed;
  - a shelf of clips generated ahead, so a press usually costs a file read
    and the worker only ever tops up;
  - an allowance per address on presses (core/throttle.py), and a cap on how
    many live jobs the demo may have open — the worker is sequential, so that
    cap is the longest wait the page promises anybody;
  - CORS that names the promo's origins, and nothing else of the API.

Addresses shared by a campus still share an allowance. Cloudflare's edge burst
limit is an additional layer; server verification also covers direct traffic.

Separate from generate.py on purpose: that is the operator's chat behind a
token, and nothing here may widen it. NO WIRE_VERSION BUMP — the phone never
calls this.
"""

import logging
import os
import threading
import time

from flask import abort, jsonify, request, send_from_directory

from ..core.throttle import Allowance
from ..core.turnstile import Turnstile, Unavailable
from ..stores.demo import MAX_WAITING, MENU, SHELF_DEPTH

#: Where the page lives. The field server also serves the promo at /promo,
#: same origin, which needs no CORS; the Vite dev server does.
DEFAULT_ORIGINS = ("https://crowgpt.org", "https://www.crowgpt.org",
                   "http://localhost:5174", "http://127.0.0.1:5174")

#: Presses an address gets an hour. Generous for a person, nothing for a loop.
PRESSES_PER_HOUR = 30


def allowed_origins() -> frozenset:
    raw = os.environ.get("FIELD_DEMO_ORIGINS")
    if raw is None:
        return frozenset(DEFAULT_ORIGINS)
    return frozenset(o.strip() for o in raw.split(",") if o.strip())


def describe(pool, row) -> dict:
    """What the page needs about a row, and nothing about the box."""
    body = {
        "id": row["id"],
        "state": row["state"],
        "seed": row["seed"],
        "model": row["model"],
        "call_type": row["call_type"],
    }
    if row["state"] == "done":
        body["duration_sec"] = row["duration_sec"]
        body["clip"] = f"/api/demo/clips/{row['id']}"
    elif row["state"] == "failed":
        body["error"] = "generation failed"
    else:
        body["ahead"] = pool.ahead_of(row)
    return body


def register(app, d) -> None:
    pool = d.demo
    presses = Allowance(allowed=PRESSES_PER_HOUR, per_seconds=3600)
    origins = allowed_origins()
    turnstile = Turnstile.from_env()
    verifying = threading.BoundedSemaphore(2)
    shelf_lock = threading.Lock()
    last_stocked = float("-inf")
    app.logger.setLevel(logging.INFO)

    @app.after_request
    def cors(response):
        if not request.path.startswith("/api/demo/"):
            return response
        if request.method == "POST":
            # No token/body, URL query or secret is logged. This is also the
            # post-flip check that the allowance sees the real visitor.
            app.logger.info("demo POST visitor=%s status=%s", request.remote_addr,
                            response.status_code)
        origin = request.headers.get("Origin")
        if origin in origins:
            # Preflights are Flask's automatic OPTIONS answers, which pass
            # through here like any response, so this is the whole of CORS.
            response.headers["Access-Control-Allow-Origin"] = origin
            response.vary.add("Origin")
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @app.get("/api/demo/menu")
    def demo_menu():
        nonlocal last_stocked
        if turnstile.required and not turnstile.configured:
            abort(503, "demo verification is unavailable")
        # Loading the page is what stocks the shelf: a server nobody visits
        # generates nothing, and the first visitor after a quiet spell waits
        # one bout rather than finding a demo that never warmed up.
        # Many page views must not each run cleanup and race to refill a shelf.
        if not shelf_lock.acquire(blocking=False):
            abort(503, "CrowGPT is busy")
        try:
            if time.monotonic() - last_stocked >= 60:
                pool.prune()
                pool.restock()
                last_stocked = time.monotonic()
            shelf = pool.shelf()
        finally:
            shelf_lock.release()
        return jsonify({
            "items": [item.describe() for item in MENU.values()],
            "shelf": shelf,
            "depth": SHELF_DEPTH,
            "turnstile_site_key": turnstile.site_key if turnstile.configured else None,
            "turnstile_required": turnstile.required,
        })

    @app.post("/api/demo/generate/<key>")
    def demo_generate(key):
        if key not in MENU:
            abort(404, "not on the menu")
        request.max_content_length = 8192
        token = request.form.get("cf-turnstile-response", "")
        # Staging accepts the old deployed page until Ben deploys the new one.
        # Any supplied token is verified even in staging; enforcement follows
        # the promo deploy and must precede the DNS flip.
        if turnstile.required or token:
            if not verifying.acquire(blocking=False):
                abort(503, "demo verification is busy")
            try:
                if not turnstile.verify(token, request.remote_addr or ""):
                    abort(403, "demo verification failed; refresh the page")
            except Unavailable:
                abort(503, "demo verification is unavailable")
            finally:
                verifying.release()
        if not presses.spend(request.remote_addr or "?"):
            abort(429, "that is enough caws for one hour from one address")
        if not shelf_lock.acquire(blocking=False):
            abort(503, "CrowGPT is busy — try again in a minute")
        try:
            if pool.shelf().get(key, 0) == 0 and pool.waiting() >= MAX_WAITING:
                abort(503, "CrowGPT is busy — try again in a minute")
            row = pool.take(key)
            pool.restock()
        finally:
            shelf_lock.release()
        return jsonify(describe(pool, row)), 200 if row["state"] == "done" else 202

    @app.get("/api/demo/generations/<int:generation_id>")
    def demo_generation(generation_id):
        row = pool.get(generation_id)
        if row is None or row["served_at"] is None:
            abort(404, "no such generation")
        return jsonify(describe(pool, row))

    @app.get("/api/demo/clips/<int:generation_id>")
    def demo_clip(generation_id):
        row = pool.get(generation_id)
        if row is None or row["served_at"] is None:
            abort(404, "no such generation")
        if row["state"] != "done":
            abort(409, f"generation is {row['state']}, not done")
        return send_from_directory(pool.generations.clip_dir, row["storage_ref"],
                                   mimetype="audio/wav")
