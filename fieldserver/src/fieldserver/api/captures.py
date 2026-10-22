"""The corpus arriving: captures, the families they belong to, and the media slots their audio is uploaded into, chunk by resumable chunk."""

import re
from flask import abort, jsonify, request

from ..core.coords import DEFAULT_FUZZ_MILES, fuzz_coords
from ..stores.captures import DISTANCE_BANDS
from .validate import number, span, whole

#: `bytes <start>-<end>/<total>`, and nothing else. `\d+` rather than a signed
#: number on purpose: a negative offset is not a range this server has a
#: sensible reading of, and it used to reach `seek()` and raise.
CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


def parse_content_range(header: str, received: int) -> tuple[int, int]:
    """Where these bytes go and how long the whole file is, or 400.

    Strict, because this header decides where a client's bytes land on disk. It
    used to be `split()` and `int()`, which meant a malformed header was a 500
    and an invented offset was taken at its word — one byte sent at offset 8 GiB
    made an 8 GiB sparse file that `finalize` then read back to hash it.

    The declared span has to match the bytes that actually arrived. Both clients
    send exactly that, and a header disagreeing with its own body is a bug
    wherever it came from.
    """
    match = CONTENT_RANGE.match(header.strip())
    if not match:
        abort(400, "Content-Range must read 'bytes <start>-<end>/<total>'")
    start, end, total = (int(group) for group in match.groups())
    if total == 0:
        abort(400, "Content-Range total must be more than zero bytes")
    if start > end or end >= total:
        abort(400, "Content-Range start-end must fall inside total")
    if end - start + 1 != received:
        abort(400, f"Content-Range covers {end - start + 1} bytes "
                   f"but {received} arrived")
    return start, total


def honoured_coords(contributor, body):
    """The coordinates a capture may keep, as (latitude, longitude, fuzz_miles).

    The second place the location choice is kept, and the reason it is kept
    twice: the phone is where it can actually be enforced, and this is where it
    survives a phone that got the rule wrong. Region-only refuses coordinates
    outright; fuzzed re-snaps whatever arrives — snapping is idempotent, so
    coordinates the phone already snapped pass through unmoved.

    `fuzz_miles` is how coarse the stored coordinates are. The client's own
    claim is trusted first (it says what the phone actually did, and a capture
    can arrive before the setting that shaped it), with the contributor's
    setting filling in when the backstop had to do the snapping itself. The
    mark matters as much as the snap: snapped coordinates stored without it
    would read as exact fixes forever.
    """
    precision = contributor.get("location_precision")
    if precision == "region":
        return None, None, None
    latitude = number(body, "latitude", -90, 90)
    longitude = number(body, "longitude", -180, 180)
    fuzz = number(body, "coord_fuzz_miles", 0, 100)
    if precision == "fuzzed" and latitude is not None and longitude is not None:
        miles = contributor.get("fuzz_miles") or DEFAULT_FUZZ_MILES
        latitude, longitude = fuzz_coords(latitude, longitude, miles)
        fuzz = fuzz or miles
    return latitude, longitude, fuzz


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    config = d.config
    families = d.families
    captures = d.captures
    media = d.media
    current_actor = d.current_actor
    owned_capture = d.owned_capture
    merges = d.merges
    counts = d.counts

    # --- authenticated ingest ---

    @app.post("/api/captures")
    def create_capture():
        device, contributor = current_actor()
        b = request.get_json(silent=True) or {}
        family_id = b.get("family_id")
        # Silently accepting someone else's family id would attach captures to
        # birds another person is tracking — the one thing family identity must
        # not allow.
        if family_id is not None and not families.owned_by(family_id, contributor["id"]):
            abort(400, "unknown family_id for this contributor")
        # Rejected rather than stored loose: an ungated value here could not be
        # grouped, and grouping is the entire reason to record it.
        observer_role = b.get("observer_role")
        if observer_role is not None and not config.observer_role_exists(observer_role):
            abort(400, f"unknown observer_role: {observer_role}")
        distance = b.get("distance_band")
        if distance is not None and distance not in DISTANCE_BANDS:
            abort(400, f"distance_band must be one of {DISTANCE_BANDS}")
        # "auto" means the phone's idle-mode trigger started the recording, and
        # absent means a person did. Gated like observer_role: a loose value
        # here could never be filtered on, and filtering unattended captures
        # out of counts is the entire reason the column exists.
        trigger = b.get("trigger")
        if trigger is not None and trigger != "auto":
            abort(400, 'trigger must be "auto" or absent')
        # Numbers checked at the door — these used to reach a bare float() in
        # the store and come back as a 500 with no field named, or land in a
        # REAL column as text.
        whole(b, "app_version", minimum=0)
        number(b, "duration_sec", minimum=0)
        crop_start, crop_end = span(b, "crop_start_sec", "crop_end_sec")
        # See honoured_coords: a contributor who asked for region-only gets
        # region-only whatever arrives, and a fuzzed one gets snapped.
        latitude, longitude, coord_fuzz_miles = honoured_coords(contributor, b)
        cap = captures.add(
            contributor_id=contributor["id"], device_id=device["id"],
            latitude=latitude, longitude=longitude,
            coord_fuzz_miles=coord_fuzz_miles,
            # Falls back to where the contributor said they are: a capture with
            # no fix still belongs to a population, and that is the question
            # place is asked for at this level.
            region=b.get("region") or contributor.get("region"),
            location_name=b.get("location_name"), recorded_at=b.get("recorded_at"),
            duration_sec=b.get("duration_sec"), notes=b.get("notes"),
            family_id=family_id, client_uuid=b.get("client_uuid"),
            name=b.get("name"), keep=bool(b.get("keep")),
            # Falls back to the build the phone is running *now*. Not as good as
            # the stamp — a capture recorded last week and synced today gets
            # today's number — but for a client too old to stamp itself, the
            # uploading build is a bound on the recording build rather than
            # nothing at all.
            app_version=b.get("app_version", device.get("app_version")),
            app_commit=b.get("app_commit", device.get("app_commit")),
            trigger=trigger,
            observer_role=observer_role,
            behavior_guess=b.get("behavior_guess"),
            # Sent at create only, describing the bytes actually uploaded. Not
            # editable afterwards: changing the span would need the corrected
            # audio re-uploaded, and metadata that moves without the bytes is
            # worse than none.
            crop_start_sec=crop_start,
            crop_end_sec=crop_end,
            distance_band=distance,
            **counts(b),
        )
        return jsonify(cap), 201

    @app.post("/api/families")
    def create_family():
        device, contributor = current_actor()
        b = request.get_json(silent=True) or {}
        try:
            family = families.add(
                contributor_id=contributor["id"], device_id=device["id"],
                name=b.get("name"), color=b.get("color"),
                notes=b.get("notes"), client_uuid=b.get("client_uuid"),
            )
        except ValueError as error:
            abort(400, str(error))
        return jsonify(family), 201

    @app.get("/api/families")
    def list_families():
        _, contributor = current_actor()
        return jsonify(families.for_contributor(contributor["id"]))

    @app.get("/api/captures")
    def list_captures():
        _, contributor = current_actor()
        return jsonify(captures.for_contributor(contributor["id"]))

    @app.get("/api/captures/<int:capture_id>")
    def get_capture(capture_id):
        _, contributor = current_actor()
        return jsonify(owned_capture(capture_id, contributor))

    @app.patch("/api/captures/<int:capture_id>")
    def update_capture(capture_id):
        """Apply an edit made after the capture was uploaded.

        Tagging a family, or fixing a note, happens back at the desk far more
        often than in the moment — and the create-only path meant those edits
        re-synced forever without ever landing.
        """
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        family_id = b.get("family_id")
        if family_id is not None and not families.owned_by(family_id, contributor["id"]):
            abort(400, "unknown family_id for this contributor")
        role = b.get("observer_role")
        if role is not None and not config.observer_role_exists(role):
            abort(400, f"unknown observer_role: {role}")
        band = b.get("distance_band")
        if band is not None and band not in DISTANCE_BANDS:
            abort(400, f"distance_band must be one of {DISTANCE_BANDS}")
        # The same backstop create applies, for the same reason. Enforcing it on
        # create alone left the promise open at the other end: a region-only
        # contributor's coordinates were refused on the way in and then accepted
        # by an edit a moment later, which honours the setting exactly until
        # somebody taps twice.
        latitude, longitude, coord_fuzz_miles = honoured_coords(contributor, b)
        updated = captures.update(
            capture_id, name=b.get("name"), family_id=family_id, notes=b.get("notes"),
            keep=None if b.get("keep") is None else int(bool(b["keep"])),
            location_name=b.get("location_name"), observer_role=role,
            latitude=latitude, longitude=longitude,
            coord_fuzz_miles=coord_fuzz_miles,
            behavior_guess=b.get("behavior_guess"), distance_band=band,
            region=b.get("region"),
            **counts(b),
        )
        # Separate from update(), which drops None values and so could never
        # clear a mark once set.
        if b.get("silent") is not None:
            updated = captures.confirm_silent(capture_id, bool(b["silent"]))
        if b.get("nothing_to_label") is not None:
            updated = captures.mark_nothing_to_label(
                capture_id, bool(b["nothing_to_label"]))
        return jsonify(updated)

    @app.post("/api/captures/<int:capture_id>/media")
    def create_media(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        whole(b, "sample_rate", minimum=1)
        whole(b, "channels", minimum=1)
        number(b, "pre_roll_sec", minimum=0)
        try:
            m = media.create(
                capture_id, kind=b.get("kind", "audio"), format=b.get("format", "wav"),
                sample_rate=b.get("sample_rate", 48000), channels=b.get("channels", 1),
                client_uuid=b.get("client_uuid"),
                input_device=b.get("input_device"),
                input_honoured=b.get("input_honoured"),
                pre_roll_sec=b.get("pre_roll_sec"),
            )
        except ValueError as error:
            abort(400, str(error))
        return jsonify(m), 201

    @app.get("/api/captures/<int:capture_id>/media")
    def list_capture_media(capture_id):
        """What was uploaded for this capture, for a client restoring it.

        Sync is push-only by design — the phone is the source of truth and the
        server never contradicts it. Restore is the deliberate exception: a
        phone that has *lost* a capture has no truth to contradict, and the
        recording is on the server precisely so that is survivable.
        """
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify(media.for_capture(capture_id))

    @app.put("/api/media/<int:media_id>")
    def upload_media(media_id):
        _, contributor = current_actor()
        m = media.get(media_id)
        if not m:
            abort(404, "media not found")
        owned_capture(m["capture_id"], contributor)
        data = request.get_data()
        content_range = request.headers.get("Content-Range")
        if content_range:
            start, total = parse_content_range(content_range, len(data))
        else:
            start, total = 0, len(data)
        try:
            m = media.append(media_id, data, start)
        except ValueError as error:
            abort(400, str(error))
        if start + len(data) >= total:
            m = media.finalize(media_id)
            captures.set_status(m["capture_id"], "uploaded")
        return jsonify(m)


    @app.post("/api/captures/<int:capture_id>/merge")
    def record_merge(capture_id):
        """Note that this capture is several earlier ones joined together.

        The joining happened on the phone, which uploaded the result through the
        ordinary capture route — by the time this is called the audio is already
        here and indistinguishable from any other recording. What this adds is
        the fact that some other captures on this server are the same birds.

        The parts are kept, rows and audio both, so the merge can be undone.
        That means the corpus now holds those calls twice, which is only safe
        because `merges.part_ids()` exists for anything doing arithmetic over
        it.

        `offset_ms` is the number worth sending: it depends on how much silence
        the client put between segments, so the server cannot recompute it, and
        without it a label made against a part cannot be moved onto the merged
        timeline or back off it.
        """
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        body = request.get_json(silent=True) or {}
        parts = body.get("parts")
        # One is enough, and two is the wrong minimum here. A merge does need
        # two captures, but that rule belongs on the phone — this records what
        # the *server* is holding, and a part that never synced was never here
        # to be superseded. Merge three recordings where only one had reached
        # the server and there is exactly one row to point at; refusing it would
        # leave that capture silently duplicated by the merged audio, which is
        # the situation this endpoint exists to prevent.
        if not isinstance(parts, list) or len(parts) < 1:
            abort(400, "parts must list at least one capture")

        cleaned = []
        for part in parts:
            part_id = part.get("capture_id") if isinstance(part, dict) else None
            if not isinstance(part_id, int):
                abort(400, "each part needs an integer capture_id")
            if part_id == capture_id:
                abort(400, "a capture cannot be a part of itself")
            # Ownership per part, not just on the merged capture: otherwise a
            # merge is a way to write a row referencing somebody else's
            # recording.
            owned_capture(part_id, contributor)
            offset = part.get("offset_ms")
            if not isinstance(offset, int) or offset < 0:
                abort(400, f"part {part_id} needs a non-negative integer offset_ms")
            cleaned.append({"capture_id": part_id, "offset_ms": offset})

        try:
            recorded = merges.record(capture_id, cleaned, contributor["id"])
        except ValueError as error:
            abort(409, str(error))
        return jsonify({"merged_capture_id": capture_id, "parts": recorded}), 201

    @app.get("/api/captures/<int:capture_id>/merge")
    def read_merge(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify({"merged_capture_id": capture_id,
                        "parts": merges.for_merged(capture_id)})
