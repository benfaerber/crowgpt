"""Re-analyze the corpus behind an analyzer change (first run: hp300, 2026-08).

Enqueues one analysis job per capture (newest complete audio media, oldest
capture first) and then watches the queue drain, reporting through Run so
the dashboard's Training panel shows the sweep. The worker does the actual
analysis; this tool never touches audio, which is why it runs from the
fieldserver venv.

Labels are human testimony and are untouched. detected_calls and candidates
regenerate under the new model_version — that is the point — and old and
new results stay distinguishable because the version string names the
preprocessing.

    .venv/bin/python tools/reanalyze_captures.py           # say what it would do
    .venv/bin/python tools/reanalyze_captures.py --apply   # enqueue and watch
"""

import argparse
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
REPO = FIELDSERVER.parent
sys.path.insert(0, str(FIELDSERVER / "src"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from fieldserver.stores.analysis import AnalysisStore  # noqa: E402

from crowgpt.progress import Run  # noqa: E402

DEFAULT_DB = FIELDSERVER / "instance" / "field.db"
POLL_SECONDS = 5


def worklist(jobs):
    """(capture_id, media_id) per capture, oldest capture first.

    Captures with a job already queued or running are skipped — the worker
    will analyze those under the current code anyway, and a second job would
    just double the queue.
    """
    with jobs._connect() as conn:  # noqa: SLF001 — a tool, on its own database
        busy = {r["capture_id"] for r in conn.execute(
            "SELECT DISTINCT capture_id FROM analysis_jobs "
            "WHERE state IN ('queued', 'running')")}
        rows = conn.execute(
            "SELECT capture_id, MAX(id) AS media_id FROM media "
            "WHERE kind = 'audio' AND upload_state = 'complete' "
            "GROUP BY capture_id ORDER BY capture_id").fetchall()
    return [(r["capture_id"], r["media_id"]) for r in rows
            if r["capture_id"] not in busy]


def states_of(jobs, ids):
    with jobs._connect() as conn:  # noqa: SLF001
        marks = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT state, COUNT(*) AS n FROM analysis_jobs "
            f"WHERE id IN ({marks}) GROUP BY state", list(ids)).fetchall()
    return {r["state"]: r["n"] for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="enqueue the jobs and watch them drain")
    args = parser.parse_args()

    jobs = AnalysisStore(Path(os.environ.get("FIELD_DB") or DEFAULT_DB))
    work = worklist(jobs)
    if not args.apply:
        print(f"would enqueue {len(work)} capture(s); rerun with --apply")
        return 0

    run = Run("REANALYZE — hp300 sweep", ["enqueue", "analyze"])
    try:
        with run.stage("enqueue") as stage:
            ids = []
            for n, (capture_id, media_id) in enumerate(work, 1):
                ids.append(jobs.enqueue(capture_id, media_id)["id"])
                stage.update(n, len(work), extra=f"capture {capture_id}")
        with run.stage("analyze") as stage:
            while True:
                states = states_of(jobs, ids)
                finished = states.get("done", 0) + states.get("failed", 0)
                stage.update(finished, len(ids),
                             extra=f"{states.get('failed', 0)} failed")
                if finished >= len(ids):
                    break
                time.sleep(POLL_SECONDS)
            run.note(f"{states.get('done', 0)} done, "
                     f"{states.get('failed', 0)} failed of {len(ids)}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
