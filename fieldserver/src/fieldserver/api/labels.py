"""Ground truth. Human labels, the context a human witnessed at the moment of a call, sightings that are explicitly *not* that, and free-text notes."""

from flask import abort, jsonify, request

from ..stores.contributors import FLEET_ROLES
from .validate import number, span


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    config = d.config
    captures = d.captures
    media = d.media
    labels = d.labels
    observations = d.observations
    context = d.context
    sightings = d.sightings
    crows = d.crows
    current_actor = d.current_actor
    owned_capture = d.owned_capture

    # --- human labels (retrain fuel) ---

    @app.post("/api/captures/<int:capture_id>/labels")
    def add_label(capture_id):
        device, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        call_type = b.get("call_type")
        # Existence, not trainability: "not a crow" is a real judgement about the
        # detection that deliberately maps to no training class.
        if not config.label_exists(call_type):
            abort(400, f"unknown label '{call_type}' — must be an active label_def")
        media_id = b.get("media_id")
        if media_id is None:
            audio = media.complete_audio_for(capture_id)
            if not audio:
                abort(409, "no uploaded audio to label; pass media_id")
            media_id = audio["id"]
        start_sec, end_sec = span(b, "start_sec", "end_sec")
        # Which bird was watched making this call. Optional and never defaulted:
        # most calls have no visible caller, and turning "nobody looked" into
        # "nobody was there" is the failure experiment 0017 exists to prevent.
        # Checked against the roster so a caller cannot be invented per capture —
        # "Edgar" has to mean the same bird in July and in October or the whole
        # field is a free-text note with extra steps.
        crow_id = b.get("crow_id")
        if crow_id is not None:
            if not crows.owned_by(crow_id, contributor["id"]):
                abort(400, f"unknown crow {crow_id} — add it to a family first")
        # What kind of bird called, which is what a recordist can actually read
        # off behaviour without bands. Absent stays absent: no default, because
        # "nobody looked" and "nobody was there" are different answers.
        caller_role = b.get("caller_role")
        if caller_role is not None and not config.caller_role_exists(caller_role):
            abort(400, f"unknown caller role '{caller_role}'")
        label = labels.add(
            crow_id=crow_id, caller_role=caller_role,
            capture_id=capture_id, media_id=media_id,
            contributor_id=contributor["id"], device_id=device["id"],
            # The fleet records one species today; a label made in the field
            # shouldn't have to restate it on every tap. A label that trains
            # nothing claims no species either — saying "not a crow" and filing
            # it under American Crow would be a contradiction the export would
            # have to unpick.
            species=(b.get("species")
                     or ("unknown" if config.core_for_label(call_type) is None
                         else "American Crow")),
            call_type=call_type,
            start_sec=start_sec, end_sec=end_sec,
            label_source=b.get("label_source", "human"), notes=b.get("notes"),
            client_uuid=b.get("client_uuid"),
            # What the labeller was actually shown. Taken from the client rather
            # than from `config.current_version()` here: the phone caches the
            # vocabulary and labels offline, so this server's idea of current
            # can be several versions ahead of the list they chose from.
            config_version=b.get("config_version"),
        )
        # Finding a call in something marked silent is a correction, not an
        # error — so the stale claim is dropped rather than the label refused.
        captures.clear_silent_if_set(capture_id)
        # And a label is evidence that there WAS something to label, which
        # outranks somebody's earlier intention to skip it.
        captures.clear_nothing_to_label_if_set(capture_id)
        return jsonify(label), 201

    @app.patch("/api/labels/<int:label_id>")
    def set_label_caller(label_id):
        """Attach (or clear) which bird was watched making this call.

        Separate from creating the label because the two answers arrive at
        different moments: the call type is tapped from a list, the caller is
        whatever the recordist could see, and forcing them into one request
        would mean re-creating the label to change the caller — which cascades
        away its context chips, as re-tapping a call type already does.

        Only the caller is patchable here. A call type change is
        destroy-and-recreate on purpose, so that the chips attached to the old
        answer cannot silently survive onto a different one.
        """
        _, contributor = current_actor()
        label = labels.get(label_id)
        if not label:
            abort(404, "label not found")
        if (label["contributor_id"] != contributor["id"]
                and contributor["role"] not in FLEET_ROLES):
            abort(403, "not your label")
        b = request.get_json(silent=True) or {}
        if "caller_role" not in b and "crow_id" not in b:
            abort(400, "nothing to set; send caller_role and/or crow_id")
        caller_role = b.get("caller_role")
        if caller_role is not None and not config.caller_role_exists(caller_role):
            abort(400, f"unknown caller role '{caller_role}'")
        crow_id = b.get("crow_id")
        if crow_id is not None and not crows.owned_by(crow_id, contributor["id"]):
            abort(400, f"unknown crow {crow_id}")
        return jsonify(labels.set_caller(
            label_id,
            caller_role=caller_role if "caller_role" in b else label["caller_role"],
            crow_id=crow_id if "crow_id" in b else label["crow_id"]))

    @app.delete("/api/labels/<int:label_id>")
    def delete_label(label_id):
        """Retract a label.

        Ground truth that cannot be taken back is worse than none: a labeller
        who realises they marked the wrong span will otherwise leave it there,
        and it enters the training manifest as fact.
        """
        _, contributor = current_actor()
        label = labels.get(label_id)
        if not label:
            abort(404, "label not found")
        if (label["contributor_id"] != contributor["id"]
                and contributor["role"] not in FLEET_ROLES):
            abort(403, "not your label")
        labels.delete(label_id)
        return "", 204

    @app.get("/api/captures/<int:capture_id>/labels")
    def list_labels(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify(labels.for_capture(capture_id))

    # --- witnessed context: what was happening, as opposed to what was said ---

    @app.post("/api/captures/<int:capture_id>/context")
    def add_context(capture_id):
        """Tag what a human saw while a particular call was made.

        Attached to a *label*, not the capture. A two-minute recording might
        have a dog appear at 0:30 and leave at 0:50 — the alarm calls in that
        window are about the dog, the song at 1:40 is not. Tagging the capture
        would credit every situation to every call in it and report that crows
        sing at dogs.
        """
        device, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        key = b.get("key")
        if not config.context_exists(key):
            abort(400, f"unknown context '{key}' — must be an active context_def")

        label_id = b.get("label_id")
        if label_id is None:
            # The one honest exception to "context hangs off a call": a
            # recording confirmed to contain none.
            #
            # The rule exists so one situation cannot be credited to every call
            # in a recording — with zero calls there is nothing to miscredit,
            # and this is the only way to record "peanuts down, three crows
            # watching, nobody said anything". That row is the denominator every
            # co-occurrence number needs, so refusing it would not be caution,
            # it would be throwing away the control group.
            #
            # Gated on the silence mark, so it cannot become a back door to
            # capture-wide tagging on a recording nobody has checked.
            capture = captures.get(capture_id)
            if not capture or not capture.get("silent_confirmed_at"):
                abort(400, "label_id is required unless the capture is confirmed "
                           "silent — tag the call the situation belongs to")
            label = None
        else:
            label = labels.get(label_id)
            if label is None or label["capture_id"] != capture_id:
                abort(400, "label_id must name a label on this capture")

        event = context.add(
            capture_id=capture_id, label_id=label_id,
            contributor_id=contributor["id"], device_id=device["id"], key=key,
            start_sec=label["start_sec"] if label else None,
            end_sec=label["end_sec"] if label else None,
            notes=b.get("notes"), client_uuid=b.get("client_uuid"),
            config_version=b.get("config_version"),
        )
        return jsonify(event), 201

    @app.get("/api/captures/<int:capture_id>/context")
    def list_context(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify(context.for_capture(capture_id))

    @app.delete("/api/context/<int:event_id>")
    def delete_context(event_id):
        _, contributor = current_actor()
        event = context.get(event_id)
        if not event:
            abort(404, "context event not found")
        if (event["contributor_id"] != contributor["id"]
                and contributor["role"] not in FLEET_ROLES):
            abort(403, "not your context event")
        context.delete(event_id)
        return "", 204

    @app.post("/api/captures/<int:capture_id>/sightings")
    def add_sighting(capture_id):
        """Record something seen near this recording but not during it.

        Deliberately not a context event. Context is what a human witnessed
        while a particular call was being made, and it is what the calls x
        context matrix is built from. An after-the-fact sighting put in there
        would be circular: you infer "that was an alarm" from the hawk, tag the
        hawk, and the matrix then reports alarm calls co-occur with hawks — true
        by construction and unrecoverable later.

        `offset_sec` is required and signed: negative before the recording,
        positive after. It is what makes this a sighting rather than a context
        event somebody was loose about.
        """
        device, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        key = b.get("key")
        # The same vocabulary context events use, so the two can be compared —
        # which is the entire reason to record this in a structured way at all.
        if not config.context_exists(key):
            abort(400, f"unknown context '{key}' — must be an active context_def")
        offset = b.get("offset_sec")
        if offset is None:
            abort(400, "offset_sec is required — a sighting with no time is a "
                       "context event")
        try:
            offset = float(offset)
        except (TypeError, ValueError):
            abort(400, "offset_sec must be a number of seconds, signed")

        return jsonify(sightings.add(
            capture_id=capture_id, contributor_id=contributor["id"],
            device_id=device["id"], key=key, offset_sec=offset,
            # A guess in metres is welcome; "about a block" spelled as text is
            # not — it used to reach the store's float() as a 500.
            distance_m=number(b, "distance_m", minimum=0), notes=b.get("notes"),
            client_uuid=b.get("client_uuid"),
        )), 201

    @app.get("/api/captures/<int:capture_id>/sightings")
    def list_sightings(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify(sightings.for_capture(capture_id))

    @app.delete("/api/sightings/<int:sighting_id>")
    def delete_sighting(sighting_id):
        _, contributor = current_actor()
        found = sightings.get(sighting_id)
        if not found:
            abort(404, "sighting not found")
        if (found["contributor_id"] != contributor["id"]
                and contributor["role"] not in FLEET_ROLES):
            abort(403, "not your sighting")
        sightings.remove(sighting_id)
        return "", 204

    # --- free-text observations (written after the fact, alongside the presets) ---

    @app.post("/api/captures/<int:capture_id>/observations")
    def add_observation(capture_id):
        device, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        try:
            obs = observations.add(
                capture_id=capture_id, contributor_id=contributor["id"],
                device_id=device["id"], body=b.get("body"),
                source=b.get("source", "typed"),
                locale=b.get("locale", device.get("locale")),
                client_uuid=b.get("client_uuid"),
            )
        except ValueError as e:
            abort(400, str(e))
        return jsonify(obs), 201

    @app.get("/api/captures/<int:capture_id>/observations")
    def list_observations(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify(observations.for_capture(capture_id))


