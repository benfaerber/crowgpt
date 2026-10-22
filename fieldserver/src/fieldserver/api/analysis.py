"""Queueing inference and reading what came back. Nothing here runs a model; the worker does that and writes its answers where these can find them."""

from flask import abort, jsonify


def register(app, d) -> None:
    """Attach this section's routes.

    The bodies below are unchanged from when they all lived in one file, which
    is deliberate: they close over the stores, and rebinding those as locals
    here means the move was a cut rather than a rewrite. `d` is the only new
    name in the room.
    """
    captures = d.captures
    media = d.media
    analysis = d.analysis
    current_actor = d.current_actor
    owned_capture = d.owned_capture

    # --- analysis (enqueue; the worker fills results) ---

    @app.post("/api/captures/<int:capture_id>/analyze")
    def analyze_capture(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        audio = media.complete_audio_for(capture_id)
        if not audio:
            abort(409, "no fully-uploaded audio for this capture")
        job = analysis.enqueue(capture_id, audio["id"])
        captures.set_status(capture_id, "analyzing")
        return jsonify(job), 202

    @app.get("/api/jobs/<int:job_id>")
    def get_job(job_id):
        """The state of one analysis job, for the client polling it.

        Readable by whoever may read the capture it names, which is the only
        thing it is about. It used to authenticate the device and stop there —
        so any enrolled phone could count up through the job ids and learn
        which captures and media existed on everybody else's account.
        """
        _, contributor = current_actor()
        job = analysis.get_job(job_id)
        if not job:
            abort(404, "job not found")
        owned_capture(job["capture_id"], contributor)
        return jsonify(job)

    @app.get("/api/captures/<int:capture_id>/calls")
    def capture_calls(capture_id):
        _, contributor = current_actor()
        owned_capture(capture_id, contributor)
        result = analysis.latest_calls_for_capture(capture_id)
        return jsonify(result or {"capture_id": capture_id, "calls": []})

