"""Generated clips to browse and download. An audition, not a measurement.

Ben wanted a page showing a bunch of CrowGPT output where he can play through it
and keep the ones he likes. That is the opposite of `/listen/` in every way that
matters: nothing is blinded, nothing is pre-registered, no answer is recorded, and
the clip names say exactly what they are.

READ OFF DISK, NO TABLES. A gallery is a directory of wavs plus a `meta.json`
under `crowgpt/results/gallery/`, written by `crowgpt/tools/publish_gallery.py`.
Same precedent as `api/training.py`: the thing that produces the data is a
separate process in a separate venv and must not need this server to be up. So
there is no migration here and no store — a gallery published while the server is
down is simply there when it comes back.

WHY NOT SERVE THE EXPERIMENT FOLDER. It would work and it would be wrong. An
experiment's output is its record, and a browse page with a delete button would be
editing a measurement. A gallery is a copy; `meta.json` records which experiment it
came from.

NO WIRE_VERSION BUMP. Operator surface. The phone neither knows nor cares.
"""

import json
from pathlib import Path

from flask import abort, jsonify, redirect, send_from_directory

from ..stores.contributors import FLEET_ROLES

#: Where `publish_gallery.py` writes. Four levels up from this file is the repo
#: root, the same arithmetic `training.py` uses to find the progress directory.
GALLERY_ROOT = Path(__file__).resolve().parents[4] / "crowgpt" / "results" / "gallery"

#: The page, from the package rather than from this file.
GALLERY_DIR = Path(__file__).resolve().parents[1] / "static" / "gallery"

NOT_BUILT = ("<h1>Gallery page missing</h1>"
             "<p>Expected <code>static/gallery/index.html</code> in the "
             "fieldserver package.</p>")


def _sets():
    """Every published gallery, newest first, or an empty list.

    A directory without a readable `meta.json` is skipped rather than raised on:
    a publish interrupted half way through leaves clips and no manifest, and that
    should not take the page down.
    """
    if not GALLERY_ROOT.is_dir():
        return []
    found = []
    for folder in sorted(GALLERY_ROOT.iterdir()):
        manifest = folder / "meta.json"
        if not folder.is_dir() or not manifest.exists():
            continue
        try:
            meta = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        meta["clip_count"] = len(meta.get("clips") or ())
        meta["published_at"] = manifest.stat().st_mtime
        found.append(meta)
    found.sort(key=lambda m: -m["published_at"])
    return found


def register(app, d) -> None:
    """Attach this section's routes.

    Only the auth helper is taken from `d`; a gallery has no store behind it.
    """
    current_actor = d.current_actor

    # Rebuilt from FLEET_ROLES rather than borrowed from another section, for the
    # reason training.py gives: Deps exists so a section cannot quietly acquire a
    # dependency.
    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def _set_or_404(name):
        for meta in _sets():
            if meta["name"] == name:
                return meta
        abort(404, "no such gallery")

    # --- the page ---

    def index():
        if not (GALLERY_DIR / "index.html").exists():
            return NOT_BUILT, 503
        return send_from_directory(GALLERY_DIR, "index.html")

    # `/gallery/` is canonical because relative asset paths resolve against it.
    app.add_url_rule("/gallery/", "gallery_page", index, methods=["GET"])
    app.add_url_rule("/gallery", "gallery_page_bare",
                     lambda: redirect("/gallery/", code=308), methods=["GET"])

    @app.get("/gallery/asset/<path:asset>")
    def gallery_asset(asset):
        # Under /gallery/asset/ rather than /gallery/<asset> so a gallery named
        # like a filename cannot shadow the page's own files.
        return send_from_directory(GALLERY_DIR, asset)

    # --- the data ---

    @app.get("/api/gallery")
    def list_galleries():
        """Every published gallery, without its clip list."""
        current_operator()
        return jsonify([{k: v for k, v in meta.items() if k != "clips"}
                        for meta in _sets()])

    @app.get("/api/gallery/<name>")
    def get_gallery(name):
        current_operator()
        return jsonify(_set_or_404(name))

    @app.get("/api/gallery/<name>/clips/<path:clip>")
    def get_gallery_clip(name, clip):
        """One wav. `send_from_directory` is what makes the path safe.

        Named `get_gallery_clip` rather than `get_clip` because Flask derives the
        endpoint from the function name and that namespace is shared across every
        section — `listening.py` already has a `get_clip`, and the collision is an
        assertion at `create_app`, so it fails every test at once rather than the
        one route it affects.
        """
        current_operator()
        _set_or_404(name)
        folder = GALLERY_ROOT / name / "clips"
        if not folder.is_dir():
            abort(404, "gallery has no clips directory")
        return send_from_directory(folder, clip, mimetype="audio/wav")
