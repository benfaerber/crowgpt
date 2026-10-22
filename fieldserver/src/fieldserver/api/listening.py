"""A listening sitting served ten trials at a time, from a URL you come back to.

Every crowgpt sitting so far has been one self-contained HTML file: all the audio
embedded as data URIs, graded in one 50-60 trial sitting, downloaded as JSON by
hand. That was the right shape for a page that had to work from `file://` on a
phone with no server. It is the wrong shape for grading ten at a time over two
weeks, which is what Ben asked for, and for the reason he gave: *"most are so
close it is hard to pick."*

WHAT THIS SECTION REFUSES TO DO, which is most of its value:

  - It will not return a result before `reveal_at`. Coming back to a page invites
    reading the running total and stopping when it looks resolved; that is
    optional stopping and it takes a nominal 5% test to 20-30%. `/results` is a
    409 until the pre-committed count is answered. Progress is a count, never a
    score.
  - It will not hand out a dose that crosses a block boundary. The store does
    that; this only exposes it. A dose is a session, twenty doses are twenty
    sessions, and 0038 measured 8.3 points of drift overnight — so arms are
    balanced inside each block and never assigned to one.
  - It has no left and no right. The answer is a signed five-point grade toward
    the first clip heard, with 0 a first-class response. Pooled over 317 saved
    pairwise trials P(chose left) = 0.628, resolved, while P(chose first-heard) =
    0.495 — the bias is the button, so the button is gone.
  - It will not hand out a second dose inside the pool's cooldown, 429 with the
    seconds remaining. Asked for as enforcement — "only let me do 10 every 30
    minutes" — and enforced here rather than by a timer in the page, because a
    timer survives neither a reload nor the phone. Finishing a dose you started
    is always allowed; only starting the next one waits.

Audio is served from the pool's own directory rather than copied in. Derived
units from CC BY-NC-ND recordings are not redistributable and the corpus is
gitignored; the answers are the durable part.

NO WIRE_VERSION BUMP. Operator surface, like `training.py`. The phone neither
knows nor cares.
"""

from pathlib import Path

from flask import abort, jsonify, redirect, request, send_from_directory

from ..stores.contributors import FLEET_ROLES
from ..stores.listening import DEFECTS, GRADES

#: The page itself, from the package rather than from this file — these routes
#: live in api/ and "next to me" is not where the static tree is.
LISTEN_DIR = Path(__file__).resolve().parents[1] / "static" / "listen"

NOT_BUILT = ("<h1>Listening page missing</h1>"
             "<p>Expected <code>static/listen/index.html</code> in the "
             "fieldserver package.</p>")


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below close over the stores, so `d` is unpacked once here and the
    routes read as if the stores were module globals — the same shape every other
    section uses.
    """
    listening = d.listening
    current_actor = d.current_actor

    # Rebuilt from FLEET_ROLES rather than imported from another section, for the
    # reason training.py gives: Deps exists so a section cannot quietly acquire a
    # dependency, and borrowing another module's closure would be exactly that.
    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def _pool_or_404(pool_id) -> dict:
        pool = listening.pool(pool_id)
        if pool is None:
            abort(404, "no such pool")
        return pool

    # --- the page ---

    def index():
        if not (LISTEN_DIR / "index.html").exists():
            return NOT_BUILT, 503
        return send_from_directory(LISTEN_DIR, "index.html")

    # Both spellings. `/listen/` is canonical because relative asset paths
    # resolve against it, and a link written the other way should not 404.
    app.add_url_rule("/listen/", "listen_page", index, methods=["GET"])
    app.add_url_rule("/listen", "listen_page_bare",
                     lambda: redirect("/listen/", code=308), methods=["GET"])

    @app.get("/listen/<path:asset>")
    def listen_asset(asset):
        return send_from_directory(LISTEN_DIR, asset)

    # --- pools ---

    @app.get("/api/listening/pools")
    def list_pools():
        """Every pool with its counts. No scores, by design."""
        current_operator()
        return jsonify(listening.pools())

    @app.get("/api/listening/pools/<int:pool_id>")
    def get_pool(pool_id):
        current_operator()
        return jsonify(_pool_or_404(pool_id))

    @app.post("/api/listening/pools")
    def create_pool():
        """Register a pool built by `crowgpt pool`.

        The trials arrive already ordered and blocked. This does not reorder
        them, and deliberately does not try to check the balance: whether each
        block holds every arm evenly is a property the builder can guarantee and
        this cannot, since it does not know what the arms mean.
        """
        current_operator()
        b = request.get_json(silent=True) or {}
        for field in ("name", "question", "clip_dir", "trials"):
            if not b.get(field):
                abort(400, f"{field} is required")
        if not isinstance(b["trials"], list):
            abort(400, "trials must be a list")
        try:
            pool = listening.create_pool(
                name=b["name"], question=b["question"], clip_dir=b["clip_dir"],
                trials=b["trials"], dose_size=int(b.get("dose_size", 10)),
                reveal_at=b.get("reveal_at"), spec=b.get("spec"),
                cooldown_minutes=b.get("cooldown_minutes"))
        except (KeyError, TypeError) as error:
            abort(400, f"malformed trial: {error}")
        except ValueError as error:
            abort(400, str(error))
        return jsonify(pool), 201

    @app.get("/api/listening/pools/<int:pool_id>/dose")
    def get_dose(pool_id):
        """The next dose, or an empty list when the pool is finished.

        The trials come back with their presentation order already fixed and
        their arm names stripped: the page is blind, so it is told which files to
        play and nothing about what they are.
        """
        current_operator()
        pool = _pool_or_404(pool_id)
        if pool["locked_for"]:
            # 429, not 403: nothing is wrong with the caller, they are early. The
            # page shows a countdown from this, but the refusal is here because a
            # timer in JavaScript survives neither a reload nor a second browser,
            # and this pool is graded from a phone and a laptop.
            return jsonify({
                "error": "cooling down",
                "why": ("a dose lands on fresh ears or it is not worth grading; "
                        "the wait is what the dose design is for"),
                "locked_for": pool["locked_for"],
                "cooldown_minutes": pool["cooldown_minutes"],
                "answered": pool["answered"],
                "remaining": pool["remaining"],
            }), 429
        trials = []
        for trial in listening.dose(pool_id):
            trials.append({
                "id": trial["id"],
                "ordinal": trial["ordinal"],
                "block": trial["block"],
                "kind": trial["kind"],
                "anchor_clip": trial["anchor_clip"],
                "first_clip": trial["first_clip"],
                "second_clip": trial["second_clip"],
            })
        return jsonify({
            "pool": {"id": pool["id"], "name": pool["name"],
                     "question": pool["question"], "dose_size": pool["dose_size"],
                     "trials": pool["trials"], "answered": pool["answered"],
                     "remaining": pool["remaining"],
                     "cooldown_minutes": pool["cooldown_minutes"]},
            "grades": list(GRADES),
            "defects": list(DEFECTS),
            "trials": trials,
        })

    @app.get("/api/listening/pools/<int:pool_id>/clips/<path:clip>")
    def get_clip(pool_id, clip):
        """One wav, out of the pool's own directory.

        `send_from_directory` is what makes the path safe — it refuses anything
        that escapes the root, so a clip name from the database cannot be turned
        into a traversal.
        """
        current_operator()
        pool = _pool_or_404(pool_id)
        clip_dir = Path(pool["clip_dir"])
        if not clip_dir.is_dir():
            abort(404, "pool clip directory is missing")
        return send_from_directory(clip_dir, clip, mimetype="audio/wav")

    # --- answering ---

    @app.post("/api/listening/trials/<int:trial_id>/answer")
    def answer_trial(trial_id):
        """Record one graded answer. Re-answering the same trial replaces it."""
        current_operator()
        b = request.get_json(silent=True) or {}
        if "grade" not in b:
            abort(400, "grade is required")
        try:
            grade = int(b["grade"])
        except (TypeError, ValueError):
            abort(400, "grade must be an integer")
        defects = b.get("defects") or []
        if not isinstance(defects, list):
            abort(400, "defects must be a list")
        try:
            row = listening.answer(
                trial_id, grade,
                defects=defects,
                note=b.get("note"),
                decision_ms=b.get("decision_ms"),
                plays_anchor=b.get("plays_anchor"),
                plays_first=b.get("plays_first"),
                plays_second=b.get("plays_second"),
                engaged_ms=b.get("engaged_ms"))
        except ValueError as error:
            abort(400, str(error))
        return jsonify(row), 201

    # --- reading out, once it is allowed ---

    @app.get("/api/listening/pools/<int:pool_id>/results")
    def get_results(pool_id):
        """Un-randomised answers, refused until `reveal_at` is met.

        409 rather than 403: nothing is wrong with the caller, the measurement is
        simply not finished, and the body says how many trials are left.
        """
        current_operator()
        pool = _pool_or_404(pool_id)
        if not pool["can_reveal"]:
            return jsonify({
                "error": "not yet",
                "why": ("results are withheld until the pre-committed trial count "
                        "is answered, so the sitting cannot be stopped when it "
                        "happens to look resolved"),
                "answered": pool["answered"],
                "reveal_at": pool["reveal_at"],
                "remaining": pool["reveal_at"] - pool["answered"],
            }), 409
        return jsonify({"pool": pool, "rows": listening.rows(pool_id)})
