"""Spoken field notes: upload, transcription queue, and the confirmation that
turns a machine's guess at the recordist's words into the recordist's words."""

from flask import abort, jsonify, request, send_file

from .captures import parse_content_range
from .validate import number, whole


def register(app, d) -> None:
    """Attach this section's routes.

    Same shape as every other section — the stores are rebound as locals so the
    bodies close over them and `d` is the only new name in the room.
    """
    captures = d.captures
    dictations = d.dictations
    observations = d.observations
    current_actor = d.current_actor
    owned_capture = d.owned_capture

    def owned_dictation(dictation_id, contributor) -> dict:
        row = dictations.get(dictation_id)
        if not row:
            abort(404, "dictation not found")
        # Through the capture, always. Authorising on the dictation's own
        # contributor_id would let a memo uploaded by a second phone on the same
        # capture become unreachable to its owner.
        owned_capture(row["capture_id"], contributor)
        return row

    # --- upload -----------------------------------------------------------

    @app.post("/api/captures/<int:capture_id>/dictations")
    def create_dictation(capture_id):
        device, contributor = current_actor()
        owned_capture(capture_id, contributor)
        b = request.get_json(silent=True) or {}
        whole(b, "sample_rate", minimum=1)
        whole(b, "channels", minimum=1)
        number(b, "duration_sec", minimum=0)
        try:
            row = dictations.create(
                capture_id=capture_id,
                contributor_id=contributor["id"], device_id=device["id"],
                format=b.get("format", "wav"),
                sample_rate=b.get("sample_rate", 16000),
                channels=b.get("channels", 1),
                duration_sec=b.get("duration_sec"),
                recorded_at=b.get("recorded_at"),
                locale=b.get("locale", device.get("locale")),
                client_uuid=b.get("client_uuid"))
        except ValueError as error:
            abort(400, str(error))
        return jsonify(row), 201

    @app.put("/api/dictations/<int:dictation_id>")
    def upload_dictation(dictation_id):
        """Append a byte range, and queue the transcription when it completes.

        Enqueued here rather than by a second request from the phone. A capture
        might not want analysing, which is why `/analyze` is explicit; a memo has
        exactly one thing anyone ever wants done with it, and a separate call is
        a step that can fail and leave a memo sitting untranscribed with nothing
        to notice it. `DictationStore.enqueue` carries the idempotency, since
        re-sending a final chunk is routine on a bad link.
        """
        _, contributor = current_actor()
        owned_dictation(dictation_id, contributor)
        data = request.get_data() or b""
        start, total = parse_content_range(
            request.headers.get("Content-Range", ""), len(data))
        try:
            row = dictations.append(dictation_id, data, start)
        except ValueError as error:
            abort(400, str(error))
        job = None
        if start + len(data) >= total:
            row = dictations.finalize(dictation_id)
            job = dictations.enqueue(dictation_id, row["capture_id"])
        return jsonify({**row, "job": job})

    @app.get("/api/captures/<int:capture_id>/dictations")
    def list_dictations(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        return jsonify(dictations.for_capture(capture_id))

    @app.get("/api/dictations/<int:dictation_id>/raw")
    def dictation_raw(dictation_id):
        _, contributor = current_actor()
        row = owned_dictation(dictation_id, contributor)
        path = dictations.path(row)
        if not path.exists():
            abort(404, "dictation audio is not on this server")
        return send_file(path, mimetype=f"audio/{row['format']}")

    # --- the transcription queue ------------------------------------------

    @app.get("/api/dictation-jobs/<int:job_id>")
    def dictation_job(job_id):
        """Poll one job.

        Ownership is re-derived through the job's capture rather than trusting a
        valid device token, for the reason `api/analysis.py` records: without it
        any enrolled phone could walk job ids and learn which captures exist on
        other people's accounts.
        """
        _, contributor = current_actor()
        job = dictations.get_job(job_id)
        if not job:
            abort(404, "job not found")
        owned_capture(job["capture_id"], contributor)
        return jsonify(job)

    @app.post("/api/dictations/<int:dictation_id>/transcribe")
    def retranscribe(dictation_id):
        """Queue it again — for a failed decode or a changed model.

        The only way past `enqueue`'s guard, and deliberately a deliberate act.
        """
        _, contributor = current_actor()
        row = owned_dictation(dictation_id, contributor)
        if row["upload_state"] != "complete":
            abort(409, "the audio has not finished uploading")
        return jsonify(dictations.enqueue(dictation_id, row["capture_id"])), 202

    # --- promotion to testimony -------------------------------------------

    @app.post("/api/dictations/<int:dictation_id>/confirm")
    def confirm_dictation(dictation_id):
        """A human has read the transcript, so it becomes an observation.

        This route is the entire difference between the two trust tiers. Until
        it runs, the words are a machine's guess and `label-set` renders them
        with a hedge naming exactly what speech recognition gets wrong — names,
        counts, species. After it, somebody has read them and they sit under
        "what the recordist wrote", which is what that heading means.

        `text` is optional and is how a mis-heard name is corrected on the way
        through: what gets promoted is what the human stands behind, not what
        the model produced.

        Idempotent by re-using the dictation's own observation row, so confirming
        twice corrects the note rather than filing a second account of the same
        thirty seconds.
        """
        device, contributor = current_actor()
        row = owned_dictation(dictation_id, contributor)
        if not row["transcript"]:
            abort(409, "nothing to confirm — this dictation has no transcript yet")
        b = request.get_json(silent=True) or {}
        body = (b.get("text") or row["transcript"] or "").strip()
        if not body:
            abort(400, "cannot confirm an empty note")
        existing_id = row["observation_id"]
        if existing_id and observations.get(existing_id):
            obs = observations.update_body(existing_id, body)
        else:
            try:
                obs = observations.add(
                    capture_id=row["capture_id"], contributor_id=contributor["id"],
                    device_id=device["id"], body=body, source="voice",
                    locale=row["locale"])
            except ValueError as error:
                abort(400, str(error))
        return jsonify(dictations.confirm(dictation_id, contributor["id"], obs["id"]))
