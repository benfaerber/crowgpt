"""Photo ID — upload a photo, get back which corvid the classifier thinks it is.

The dashboard's Photo ID page posts a photo here and polls the list; the
classifier runs in `worker/photo_worker.py` under analyzer/photo's venv,
because BioCLIP and the bird detector are torch and this process must never
import it.

A test bench for the classifier, not part of the corpus: nothing uploaded here
is a capture, and the phone never calls it.

NO WIRE_VERSION BUMP. Operator surface, like generate.py.
"""

from pathlib import PurePosixPath

from flask import abort, jsonify, request, send_from_directory

from ..stores.contributors import FLEET_ROLES


def register(app, d) -> None:
    photo_ids = d.photo_ids
    current_actor = d.current_actor

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def coordinate(name):
        raw = (request.form.get(name) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            abort(400, f"{name} must be a number")

    def list_photo_ids():
        current_operator()
        return jsonify({"identifications": photo_ids.recent()})

    def create_photo_id():
        operator = current_operator()
        upload = request.files.get("photo")
        if upload is None or not upload.filename:
            abort(400, "attach the photo as 'photo'")
        try:
            row = photo_ids.request(
                upload.read(),
                PurePosixPath(upload.filename).suffix,
                original_name=PurePosixPath(upload.filename).name[:200],
                latitude=coordinate("latitude"),
                longitude=coordinate("longitude"),
                contributor_id=operator["id"],
            )
        except ValueError as error:
            abort(400, str(error))
        return jsonify(row), 201

    def forget_photo_ids():
        current_operator()
        return jsonify({"forgotten": photo_ids.forget()})

    def photo_id_photo(identification_id):
        current_operator()
        row = photo_ids.get(identification_id)
        if row is None:
            abort(404, "no such photo")
        return send_from_directory(photo_ids.photo_dir, row["storage_ref"])

    app.add_url_rule("/api/photo-ids", "list_photo_ids", list_photo_ids, methods=["GET"])
    app.add_url_rule("/api/photo-ids", "create_photo_id", create_photo_id, methods=["POST"])
    app.add_url_rule("/api/photo-ids", "forget_photo_ids", forget_photo_ids, methods=["DELETE"])
    app.add_url_rule("/api/photo-ids/<int:identification_id>/photo", "photo_id_photo",
                     photo_id_photo, methods=["GET"])
