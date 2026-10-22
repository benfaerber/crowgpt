"""What the long-running jobs are doing, read off disk.

A run is a separate process, in a separate venv, usually under systemd — and
it must not need this server to be up in order to make progress. So nothing is
pushed: each run writes `<slug>.json` into the shared progress directory as it
goes, and this lists the directory when an operator opens the page.

A DIRECTORY, NOT A FILE, because two runs happened at once. A single shared
PROGRESS.json was the design until a corpus scan and a decoder finetune
overwrote each other's state and the panel flickered between them. One file
per run means runs coexist; the response is a list, active runs first.

NO WIRE_VERSION BUMP. This is dashboard surface. The phone neither knows nor
cares, and bumping compatibility for a UI change is how a version warning
turns into noise — see the entry in CLAUDE.md about the run that called a
server three tooling commits behind incompatible.
"""

import json
import os
import time
from pathlib import Path

from flask import abort, jsonify

from ..stores.contributors import FLEET_ROLES

REPO = Path(__file__).resolve().parents[4]

#: Past this, a file is reporting a run that is no longer writing. Training
#: writes on every eval — a thousand steps, about two minutes at batch 32 — so
#: ten minutes of silence means it stopped, crashed, or was killed.
STALE_AFTER = 600

#: Cap on how many runs the response carries; finished runs leave their files
#: behind, and the panel wants the recent story, not the archive.
MOST_RECENT = 20


def _progress_dir() -> Path:
    """The same resolution rule as crowgpt.progress.progress_dir, mirrored
    rather than imported — this server must not need crowgpt importable."""
    override = os.environ.get("PROGRESS_DIR")
    if override:
        return Path(override).expanduser()
    data = os.environ.get("DATA_DIR")
    base = Path(data).expanduser() if data else REPO / "data"
    return base / "progress"


def _entry(path: Path, run: dict) -> dict:
    age = time.time() - path.stat().st_mtime
    stale = age > STALE_AFTER
    return {
        "slug": run.get("slug") or path.stem,
        "path": str(path),
        "age_seconds": round(age),
        # A finished run leaves its file behind, so "is it moving" is a
        # question about the clock, not about the contents.
        "stale": stale,
        "active": not stale and not run.get("finished"),
        "run": run,
    }


def _dir_entries() -> list[dict]:
    folder = _progress_dir()
    if not folder.is_dir():
        return []
    entries = []
    for path in folder.glob("*.json"):
        try:
            run = json.loads(path.read_text())
        except (OSError, ValueError):
            # Rewritten on every update, so a read can land mid-write; the
            # run reappears intact on the next poll.
            continue
        if not isinstance(run, dict):
            continue
        entries.append(_entry(path, run))
    return entries


def register(app, d) -> None:
    # Same gate the fleet routes use, rebuilt from the same two pieces rather
    # than reached for across modules — Deps exists precisely so a section
    # cannot quietly acquire a dependency, and importing another section's
    # closure would be that. FLEET_ROLES itself comes from the store, so the
    # role list cannot drift between here and fleet.py.
    current_actor = d.current_actor

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    @app.get("/api/training")
    def training_status():
        """Every run with a status file, or an honest nothing."""
        current_operator()
        entries = _dir_entries()
        entries.sort(key=lambda e: (not e["active"], e["age_seconds"]))
        # One card per slug, freshest wins — the same rule Run itself applies
        # when a restarted run replaces its own card rather than growing a
        # second one. Two files claiming a slug otherwise both render.
        seen: set = set()
        unique = [e for e in entries
                  if e["slug"] not in seen and not seen.add(e["slug"])]
        return jsonify({"runs": unique[:MOST_RECENT],
                        "dir": str(_progress_dir())})
