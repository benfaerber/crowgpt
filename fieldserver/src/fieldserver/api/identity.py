"""Who is holding the phone, and which phone it is. Enrolment, the claim code that joins a second handset to the same person, renaming, and the operator's own session."""

from flask import abort, jsonify, request

from ..core.secrets import (
    DASHBOARD_CONTRIBUTOR,
    ENROLL_SECRET,
    OPERATOR_SECRET,
    presented,
)
from ..core.throttle import Throttle
from ..stores.contributors import FLEET_ROLES

#: Wrong guesses allowed per caller per minute, across the three routes below.
#:
#: Generous for somebody typing a token into a phone by hand — nobody gets it
#: wrong ten times a minute — and useless to a script working through a
#: keyspace, which is the whole distinction worth drawing.
WRONG_GUESSES = 10
GUESS_WINDOW_SEC = 60


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    contributors = d.contributors
    devices = d.devices
    captures = d.captures
    current_actor = d.current_actor

    # Per app rather than per module: two servers in one process (the tests run
    # dozens) must not share a counter, or one of them locks the others out.
    guesses = Throttle(allowed=WRONG_GUESSES, per_seconds=GUESS_WINDOW_SEC)

    def guessing_caller() -> str:
        """The caller, refused outright if they have been guessing.

        Checked before the secret is compared, so a blocked caller learns
        nothing about whether the string they just tried was right.
        """
        caller = request.remote_addr or "unknown"
        if guesses.blocked(caller):
            abort(429, "too many failed attempts — wait a minute and retry")
        return caller

    @app.post("/api/devices/register")
    def register_device():
        """Enroll a phone — as a new contributor, or as another of someone's.

        Passing `claim_code` is what makes a second handset the *same* person:
        without it every install is a stranger, which is how one recordist ends
        up as six rows owning a sixth of their own corpus each.
        """
        caller = guessing_caller()
        body = request.get_json(silent=True) or {}
        if not presented(body, "enroll_token", ENROLL_SECRET):
            guesses.record_failure(caller)
            abort(403, "invalid enrollment token")
        # An operator can read every other contributor's captures, so the role
        # has to be earned with a second secret rather than asserted.
        is_operator = bool(body.get("is_operator"))
        if is_operator and not presented(body, "operator_token", OPERATOR_SECRET):
            guesses.record_failure(caller)
            abort(403, "operator enrollment requires a valid operator_token")

        claim_code = body.get("claim_code")
        contributor = contributors.by_claim_code(claim_code) if claim_code else None
        if claim_code and not contributor:
            # A claim code is a secret like the other two — it joins a handset
            # to somebody else's corpus — so a wrong one counts the same way.
            guesses.record_failure(caller)
            abort(403, "unrecognised claim code")
        fresh_claim_code = None
        if not contributor:
            contributor, fresh_claim_code = contributors.create(
                body.get("contributor_name"),
                role="operator" if is_operator else "contributor",
            )
        elif is_operator and contributor["role"] not in FLEET_ROLES:
            contributor = contributors.set_role(contributor["id"], "operator")

        device, token = devices.register(
            contributor_id=contributor["id"],
            label=body.get("label"),
            platform=body.get("platform"),
            locale=body.get("locale", "en"),
        )
        payload = {"device": device, "device_token": token, "contributor": contributor}
        # Shown exactly once, like the bearer token. A lost one is rotated via
        # /api/me/claim-code rather than recovered.
        if fresh_claim_code:
            payload["claim_code"] = fresh_claim_code
        return jsonify(payload), 201

    # --- who am I, and what am I carrying ---

    @app.get("/api/me")
    def whoami():
        device, contributor = current_actor()
        return jsonify({
            "contributor": contributor,
            "device": device,
            "devices": devices.for_contributor(contributor["id"]),
        })

    @app.patch("/api/me")
    def rename_me():
        _, contributor = current_actor()
        b = request.get_json(silent=True) or {}
        try:
            return jsonify(contributors.rename(contributor["id"], b.get("display_name")))
        except ValueError as error:
            abort(400, str(error))

    @app.patch("/api/me/location-precision")
    def set_my_location_precision():
        """How precisely this phone's owner is willing to say where they were.

        Theirs to set, from their own phone. Deliberately not something an
        operator can change for them — that is the difference between a setting
        and a policy.
        """
        _, contributor = current_actor()
        b = request.get_json(silent=True) or {}
        try:
            # `censor_coords` omitted leaves it as it was rather than clearing
            # it. A client that does not know about the field must not be able
            # to turn somebody's masking off by not mentioning it.
            return jsonify(contributors.set_location_precision(
                contributor["id"], b.get("location_precision"), b.get("region"),
                censor_coords=b.get("censor_coords"),
                fuzz_miles=b.get("fuzz_miles")))
        except ValueError as error:
            abort(400, str(error))

    @app.post("/api/me/claim-code")
    def new_claim_code():
        """Mint a fresh code for adding another phone, invalidating the old one."""
        _, contributor = current_actor()
        return jsonify({"claim_code": contributors.rotate_claim_code(contributor["id"])})

    @app.patch("/api/devices/<int:device_id>")
    def rename_device(device_id):
        _, contributor = current_actor()
        target = devices.get(device_id)
        if not target or target["contributor_id"] != contributor["id"]:
            abort(404, "device not found")
        b = request.get_json(silent=True) or {}
        if b.get("revoked"):
            return jsonify(devices.revoke(device_id))
        return jsonify(devices.rename(device_id, b.get("label")))

    @app.post("/api/operator/session")
    def operator_session():
        """Exchange the operator secret for a dashboard bearer token.

        The dashboard authenticates with a device token like everything else, but
        an operator holds the *operator secret* — a different string. Making them
        paste one and be told to fetch the other with curl is a trap, and it is
        the one people actually fell into, so the exchange happens here.
        """
        caller = guessing_caller()
        body = request.get_json(silent=True) or {}

        # A caller already holding a working session keeps it. Rotating on every
        # sign-in evicted every other tab and turned a stray refresh into
        # "paste the operator token again" — and handing back a token they
        # already sent us discloses nothing.
        auth = request.headers.get("Authorization", "")
        bearer = auth[7:] if auth.startswith("Bearer ") else None
        if bearer:
            device = devices.authenticate(bearer)
            contributor = contributors.get(device["contributor_id"]) if device else None
            if contributor and contributor["role"] in FLEET_ROLES:
                return jsonify({"device": device, "device_token": bearer,
                                "contributor": contributor}), 200

        if not presented(body, "operator_token", OPERATOR_SECRET):
            guesses.record_failure(caller)
            abort(403, "invalid operator token")
        # One browser row, reused. Minting a device per sign-in filled the fleet
        # list with dashboards that had never recorded anything, and every one of
        # them held a live token forever.
        operator = next((c for c in contributors.list_all()
                         if c["display_name"] == DASHBOARD_CONTRIBUTOR), None)
        if not operator:
            operator, _ = contributors.create(DASHBOARD_CONTRIBUTOR, role="operator")
        existing = devices.find(operator["id"], "web")
        if existing:
            device, token = devices.rotate_token(existing["id"])
        else:
            device, token = devices.register(
                contributor_id=operator["id"], label="Operator dashboard",
                platform="web", locale="en")
        return jsonify({"device": device, "device_token": token,
                        "contributor": operator}), 201

