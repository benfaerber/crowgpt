"""Crow Chat — ask CrowGPT for a call, get the clip back as a reply.

The dashboard's chat page posts a request here and polls the list; the actual
generation runs in `worker/generate_worker.py` under crowgpt's venv, because
torch work never sits in a Flask request and this process must never import it.

The buttons come from the server (`models` in the list response, each with the
call types it takes) so the page cannot offer a model or a type the queue would
refuse. A model with no call types answers a bare caw request — call_type NULL.

NO WIRE_VERSION BUMP. Operator surface, like training.py. The phone neither
knows nor cares.
"""

from flask import abort, jsonify, request, send_from_directory

from ..stores.contributors import FLEET_ROLES
from ..stores.generations import DEFAULT_MODEL, MODELS


def register(app, d) -> None:
    generations = d.generations
    current_actor = d.current_actor

    # Rebuilt from FLEET_ROLES rather than imported from another section, for
    # the reason training.py gives: Deps exists so a section cannot quietly
    # acquire a dependency, and borrowing another module's closure would be
    # exactly that.
    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def list_generations():
        current_operator()
        return jsonify({
            "models": [{"name": name, "call_types": list(call_types)}
                       for name, call_types in MODELS.items()],
            "generations": generations.recent(),
        })

    def create_generation():
        operator = current_operator()
        body = request.get_json(silent=True) or {}
        model = (body.get("model") or DEFAULT_MODEL).strip()
        if model not in MODELS:
            abort(400, f"model must be one of: {', '.join(MODELS)}")
        allowed = MODELS[model]
        call_type = (body.get("call_type") or "").strip() or None
        if allowed and call_type not in allowed:
            abort(400, f"{model} takes a call_type from: {', '.join(allowed)}")
        if not allowed and call_type is not None:
            abort(400, f"{model} does not take a call_type")
        row = generations.request(call_type, model=model,
                                  contributor_id=operator["id"])
        return jsonify(row), 201

    def forget_generations():
        current_operator()
        return jsonify({"forgotten": generations.forget()})

    def generation_audio(generation_id):
        current_operator()
        row = generations.get(generation_id)
        if row is None:
            abort(404, "no such generation")
        if row["state"] != "done":
            abort(409, f"generation is {row['state']}, not done")
        # send_from_directory rather than send_file, because it refuses path
        # traversal — the ref is server-minted, but the property should not
        # depend on that staying true.
        return send_from_directory(generations.clip_dir, row["storage_ref"],
                                   mimetype="audio/wav")

    app.add_url_rule("/api/generations", "list_generations", list_generations,
                     methods=["GET"])
    app.add_url_rule("/api/generations", "create_generation", create_generation,
                     methods=["POST"])
    app.add_url_rule("/api/generations", "forget_generations",
                     forget_generations, methods=["DELETE"])
    app.add_url_rule("/api/generations/<int:generation_id>/audio",
                     "generation_audio", generation_audio, methods=["GET"])
