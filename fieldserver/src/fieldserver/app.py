"""CrowGPT field server — the fleet's command-and-control + ingest API.

One SQLite file, one store per table, assembled by an app factory. Stores are
constructed in FK-dependency order — ContributorStore -> DeviceStore ->
CaptureStore -> MediaStore, plus the standalone ConfigStore — because that order
is also the migration order (see create_app).

  uv run fieldserver     # serves on 127.0.0.1:5100
"""

import os
from pathlib import Path

from flask import Flask, abort, request

from .core import schema
from .stores.analysis import AnalysisStore
from .stores.captures import CaptureStore
from .stores.config_store import ConfigStore
from .stores.context_events import ContextStore
from .stores.contributors import FLEET_ROLES, ContributorStore
from .stores.dashboard import DashboardQueries
from .stores.devices import DeviceStore
from .stores.crows import CrowStore
from .stores.families import FamilyStore
from .stores.labels import LabelStore
from .stores.merges import MergeStore
from .stores.generations import GenerationStore
from .stores.scout_visits import ScoutVisitStore
from .stores.listening import ListeningStore
from .stores.logs import LogStore
from .stores.dictations import DictationStore
from .stores.media import MediaStore
from .stores.observations import ObservationStore
from .stores.quality import QualityStore
from .stores.ai_descriptions import AiDescriptionStore
from .stores.sightings import SightingStore

# From paths, which is the one place that knows. app.py used to work it out
# again from its own depth, and a module moving folders is all it takes for two
# copies of that arithmetic to disagree about which database is being served.
from .core.paths import DEFAULT_DB  # noqa: E402
from . import api
from .api.deps import Deps
from .core.secrets import (  # re-exported: tests and tools read them from here
    DASHBOARD_CONTRIBUTOR,
    DEFAULT_ENROLL_TOKEN,
    DEFAULT_OPERATOR_TOKEN,
    ENROLL_SECRET,
    LOOPBACK_HOSTS,
    OPERATOR_SECRET,
)





# The largest body the server will read. Uploads arrive in chunks — 256 KiB
# from the phone, 4 MiB from the dashboard — so this is well clear of both, and
# a capture larger than it still uploads because it is never one request.
#
# It exists because `request.get_data()` otherwise buffers whatever arrives,
# which makes a single POST a memory-exhaustion switch for anything holding an
# enrollment token. Werkzeug answers 413 above it, before a byte is read.
MAX_UPLOAD_BYTES = int(os.environ.get("FIELD_MAX_UPLOAD_MB", "16")) * 1024 * 1024


def create_app(db_path: Path | str | None = None) -> Flask:
    # In create_app, not only in main(): gunicorn, `flask run` and any other WSGI
    # entry point never call main(), and the default secrets are published
    # constants in this repo. Keyed on the same FIELD_HOST main() binds, so the
    # loopback convenience and the tests (which never set FIELD_HOST) are
    # unaffected, and a network bind with dev secrets is refused however it starts.
    refuse_default_secrets_off_loopback(os.environ.get("FIELD_HOST", "127.0.0.1"))
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    resolved_db = Path(db_path or os.environ.get("FIELD_DB") or DEFAULT_DB)
    media_dir = resolved_db.parent / "media"

    # Schema first, from Alembic. The stores below create no tables and add no
    # columns: they read and write a shape that is already there.
    schema.upgrade(resolved_db)
    problems = schema.drift(resolved_db)
    if problems:
        # Before the stores, not after: a table of the wrong shape takes a store
        # down during construction, and "no such column: labels.device_id" says
        # nothing about which migration is missing.
        #
        # Refuse rather than serve. A server whose tables are the wrong shape
        # accepts writes and silently drops the fields it does not recognise,
        # which is exactly how a sync reported success while losing
        # observer_role and silent. Failing is loud, local, and costs a restart.
        raise RuntimeError(
            "database schema does not match the migrations:\n  "
            + "\n  ".join(problems)
            + "\nRun: uv run alembic upgrade head"
        )

    config = ConfigStore(resolved_db)
    contributors = ContributorStore(resolved_db)
    devices = DeviceStore(resolved_db)          # -> contributors
    families = FamilyStore(resolved_db)         # -> contributors, devices
    crows = CrowStore(resolved_db)              # -> families
    captures = CaptureStore(resolved_db)        # -> contributors, devices, families
    media = MediaStore(resolved_db, media_dir)  # -> captures
    analysis = AnalysisStore(resolved_db)       # -> captures, media
    quality = QualityStore(resolved_db)         # -> captures, media
    labels = LabelStore(resolved_db)            # -> captures, media, contributors
    observations = ObservationStore(resolved_db)  # -> captures, contributors
    # Its own directory beside media/, never inside it: media/ means "somebody's
    # recording of birds", and everything that walks it relies on that.
    dictations = DictationStore(resolved_db, resolved_db.parent / "dictations")
    # -> captures, contributors, devices, observations
    context = ContextStore(resolved_db)         # -> captures, contributors
    sightings = SightingStore(resolved_db)      # -> captures, contributors
    ai_descriptions = AiDescriptionStore(resolved_db)  # -> captures
    merges = MergeStore(resolved_db)            # -> captures, contributors
    logs = LogStore(resolved_db)                # -> contributors, devices
    # Owns no foreign keys at all: a listening pool is about model checkpoints and
    # corpus bouts, neither of which this database knows anything about.
    listening = ListeningStore(resolved_db)
    # Synthetic clips beside media/, never inside it, same as dictations.
    generations = GenerationStore(resolved_db, resolved_db.parent / "generated")
    scout_visits = ScoutVisitStore(resolved_db)
    board = DashboardQueries(resolved_db)   # read-only joins across all of the above

    def current_device() -> dict:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        device = devices.authenticate(
            token,
            app_version=request.headers.get("X-App-Version", type=int),
            app_commit=request.headers.get("X-App-Commit"),
        )
        if not device:
            abort(401, "valid device bearer token required")
        return device

    def current_actor() -> tuple[dict, dict]:
        """The device that called, and the person it belongs to.

        Nearly every route wants both: the contributor decides what may be read
        or written, the device records which phone did it.
        """
        device = current_device()
        contributor = contributors.get(device["contributor_id"])
        if not contributor:
            abort(401, "device has no contributor")
        return device, contributor


    def counts(body):
        """The three head counts, refusing anything that is not one."""
        out = {}
        for key in ("adult_count", "juvenile_count", "unaged_count"):
            value = body.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                abort(400, f"{key} must be a whole number of birds, or omitted")
            out[key] = value
        return out

    def owned_capture(capture_id, contributor) -> dict:
        cap = captures.get(capture_id)
        if not cap:
            abort(404, "capture not found")
        if (cap["contributor_id"] != contributor["id"]
                and contributor["role"] not in FLEET_ROLES):
            abort(403, "not your capture")
        return cap

    api.register_all(app, Deps(
        config=config, contributors=contributors, devices=devices,
        families=families, crows=crows, captures=captures, media=media,
        analysis=analysis,
        quality=quality, labels=labels, observations=observations, context=context,
        dictations=dictations,
        sightings=sightings, ai_descriptions=ai_descriptions,
        merges=merges, logs=logs, listening=listening, generations=generations,
        instance_dir=resolved_db.parent, scout_visits=scout_visits,
        board=board,
        current_actor=current_actor,
        owned_capture=owned_capture, counts=counts,
    ))

    return app


def refuse_default_secrets_off_loopback(host: str) -> None:
    """Off loopback, the built-in dev secrets are the same as no secrets at all.

    On 127.0.0.1 they're a convenience — you already have to be on this machine.
    Bound to the network they're published constants, and anyone who reads this
    file can enroll as an operator and pull the whole corpus. Refuse loudly
    rather than serve something that looks protected and isn't.
    """
    if host in LOOPBACK_HOSTS:
        return
    weak = [name for name, value, default in (
        ("FIELD_ENROLL_TOKEN", ENROLL_SECRET, DEFAULT_ENROLL_TOKEN),
        ("FIELD_OPERATOR_TOKEN", OPERATOR_SECRET, DEFAULT_OPERATOR_TOKEN),
    ) if not value or value == default]
    if not weak:
        return
    raise SystemExit(
        f"Refusing to serve {host} with the default {' and '.join(weak)}.\n"
        "Anything on this network could enroll — as an operator — and read every\n"
        "capture. `make -C fieldserver dev` mints real secrets for you, or set\n"
        "them yourself:\n\n"
        + "".join(f"  export {name}=$(python3 -c 'import secrets;"
                  f"print(secrets.token_urlsafe(24))')\n" for name in weak)
        + "\nOr keep it on this machine only:  FIELD_HOST=127.0.0.1"
    )


def main() -> None:
    """Serve the field API.

    Binds loopback by default. Set FIELD_HOST=0.0.0.0 to serve the whole local
    network, which is how phones reach it over Wi-Fi instead of USB — worth
    knowing that this exposes the enrollment token and every capture to anything
    else on that network, since there is no TLS and the token is a shared secret.
    """
    host = os.environ.get("FIELD_HOST", "127.0.0.1")
    port = int(os.environ.get("FIELD_PORT", "5100"))
    # The refusal now lives in create_app(), keyed on the same FIELD_HOST, so it
    # fires for every entry point rather than this one alone.
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
