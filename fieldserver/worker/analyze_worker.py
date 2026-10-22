"""Inference worker — the heavy ML half of the field system.

Runs in the BirdNET venv, polls the field server's `analysis_jobs` table, runs the
analyzer's BirdNET pipeline on each uploaded media file, and writes
`analysis_results` + `detected_calls` back. The shared SQLite DB is the only
coupling to the mobile-facing API (no HTTP, no re-upload). Media is retained
(the analyzer itself is stateless — it is handed a path and returns findings).

  ../pipelines/representation/.venv-birdnet/bin/python worker/analyze_worker.py
  # one pass over queued jobs then exit (cron / test):
  ../pipelines/representation/.venv-birdnet/bin/python worker/analyze_worker.py --once
  # against a specific DB:  FIELD_DB=/path/field.db  python worker/analyze_worker.py
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
REPO = FIELDSERVER.parent
sys.path.insert(0, str(FIELDSERVER / "src"))
# The analyzer is its own component: it takes a path and returns findings, and
# knows nothing about jobs or the database. This worker is the part that does.
sys.path.insert(0, str(REPO))

from fieldserver.stores.analysis import AnalysisStore  # noqa: E402
from fieldserver.stores.captures import CaptureStore  # noqa: E402
from fieldserver.stores.media import MediaStore  # noqa: E402
from fieldserver.stores.quality import QualityStore  # noqa: E402

from analyzer import birdnet  # noqa: E402  — loads BirdNET + the heads at import
from analyzer import quality  # noqa: E402  — pure DSP, no model

DEFAULT_DB = FIELDSERVER / "instance" / "field.db"

# Fallback coordinates for captures with no GPS of their own — a clip dropped on
# the dashboard, mostly. Env rather than source: nothing location-specific
# belongs in the repo. Unset means no filter rather than a guessed one.
FLEET_LAT = float(os.environ["FIELD_LAT"]) if os.environ.get("FIELD_LAT") else None
FLEET_LON = float(os.environ["FIELD_LON"]) if os.environ.get("FIELD_LON") else None


def model_version() -> str:
    return birdnet.HEADS.version()


def recorded_on(capture):
    """The capture's date, for BirdNET's seasonal occurrence filter."""
    stamp = capture.get("recorded_at") or capture.get("created_at")
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def process(job, jobs, media_store, captures, qualities) -> int:
    media = media_store.get(job["media_id"])
    path = media_store.path(media)
    capture = captures.get(job["capture_id"]) or {}
    env, duration = birdnet.waveform_envelope(path)

    # Where and when it was recorded turns on BirdNET's occurrence filter. The
    # model is global, so without it a Utah recording comes back as Rook and
    # Torresian Crow — and since both have call-type heads, the wrong species
    # gets a confident call type hung off it. Captures uploaded from the browser
    # have no GPS; FIELD_LAT/FIELD_LON stand in for the fleet's home ground when
    # they are set, and nothing is guessed when they are not.
    lat = capture.get("latitude") if capture.get("latitude") is not None else FLEET_LAT
    lon = capture.get("longitude") if capture.get("longitude") is not None else FLEET_LON

    wav = None
    try:
        wav = birdnet.to_wav(path)
        calls = birdnet.analyze(wav, lat=lat, lon=lon, when=recorded_on(capture))
        # Same decoded WAV, so the quality numbers and the detections describe
        # one rendering of the audio. A quality failure must not fail the job:
        # `fail` is a dead end with no retries, and losing detections over a
        # decoration would be backwards. The miss is loud twice — here, and in
        # QualityStore.missing(), which the backfill tool doubles as the audit
        # for.
        try:
            qualities.upsert(job["capture_id"], job["media_id"],
                             quality.measure(wav))
        except Exception as exc:  # noqa: BLE001
            print(f"job {job['id']}: quality failed — {exc}", flush=True)
    finally:
        if wav:
            wav.unlink(missing_ok=True)
    jobs.complete(job["id"], job["capture_id"], duration, env,
                  birdnet.HEADS.reliability_payload(), calls, model_version())
    captures.set_status(job["capture_id"], "analyzed")
    return len(calls)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    once = "--once" in argv
    db = Path(os.environ.get("FIELD_DB") or DEFAULT_DB)
    jobs = AnalysisStore(db)
    media_store = MediaStore(db, db.parent / "media")
    captures = CaptureStore(db)
    qualities = QualityStore(db)
    poll = float(os.environ.get("WORKER_POLL", "2"))

    # Anything still marked 'running' belongs to a worker that is gone — this
    # one is only now starting, and it is the only one against this database.
    # Without this a kill mid-analysis stranded the job and left its capture in
    # 'analyzing' forever, which no dashboard number counts.
    requeued, abandoned = jobs.reclaim_running()
    if requeued:
        print(f"requeued {len(requeued)} job(s) left running by a stopped worker: "
              f"{requeued}", flush=True)
    if abandoned:
        print(f"failed {len(abandoned)} job(s) that have used up their attempts: "
              f"{abandoned} — their captures are back at 'uploaded'", flush=True)

    print(f"worker ready — {model_version()} — polling {db}"
          f"{' (--once)' if once else ''}", flush=True)

    while True:
        try:
            job = jobs.claim_next()
        except Exception as exc:  # noqa: BLE001 — a locked DB is a wait, not a death
            # The phone syncing is exactly when jobs arrive, and it is also
            # when SQLite says "database is locked". A poll that dies on that
            # leaves every later job queued forever with nothing to notice.
            if once:
                raise
            print(f"poll failed — {exc}; retrying", flush=True)
            time.sleep(poll)
            continue
        if job is None:
            if once:
                return 0
            time.sleep(poll)
            continue
        print(f"job {job['id']}: analyzing capture {job['capture_id']}…", flush=True)
        try:
            n = process(job, jobs, media_store, captures, qualities)
            print(f"job {job['id']}: done — {n} call region(s)", flush=True)
        except Exception as exc:  # noqa: BLE001 — one bad clip must not kill the loop
            try:
                jobs.fail(job["id"], exc)
            except Exception as unrecorded:  # noqa: BLE001
                print(f"job {job['id']}: could not record the failure — {unrecorded}",
                      flush=True)
            print(f"job {job['id']}: error — {exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
