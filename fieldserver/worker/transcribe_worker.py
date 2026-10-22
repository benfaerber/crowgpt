"""Transcription worker — turns a spoken field note into text.

Polls `dictation_jobs`, renders the memo to 16 kHz mono, runs Whisper on the GPU,
and writes the transcript back. The shared SQLite DB is the only coupling to the
API, exactly as it is for the analyze worker.

A SECOND PROCESS FOR A TECHNICAL REASON, NOT FOR TIDINESS. `analyze_worker.py`
does `from analyzer import birdnet` at import, and birdnetlib (through
tflite_runtime) leaves torch permanently unable to see the GPU in that process —
`torch.cuda.is_available()` is False afterwards with no error anywhere. Running
Whisper there would work, silently, at roughly 1/20th the speed. See
`crowgpt/src/crowgpt/gpu.py`, which is the written record of that costing a night
of training. This worker therefore imports nothing from `analyzer`, not even the
package: the lazy `__getattr__` there makes it safe today, and a future eager
import would poison this process with slowness as the only symptom.

  ../crowgpt/.venv/bin/python worker/transcribe_worker.py
  # one pass then exit (cron / test):
  ../crowgpt/.venv/bin/python worker/transcribe_worker.py --once
  # against a specific DB:  FIELD_DB=/path/field.db  python worker/transcribe_worker.py
  # a different model:      DICTATION_MODEL=openai/whisper-small.en
  # hold it longer:          DICTATION_IDLE_MINUTES=60
"""

import gc
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
REPO = FIELDSERVER.parent
sys.path.insert(0, str(FIELDSERVER / "src"))
# The transcriber is its own component: a path in, text out, knowing nothing
# about jobs or the database. This worker is the part that does.
sys.path.insert(0, str(REPO))

from fieldserver.stores.dictations import DictationStore  # noqa: E402

from transcriber import whisper  # noqa: E402  — loads torch; see the guard in it

DEFAULT_DB = FIELDSERVER / "instance" / "field.db"


#: How long the model may sit loaded with nothing to do, before it is dropped.
#:
#: Fifteen minutes rather than an hour, and the number is about this machine
#: rather than about Whisper. The same GPU trains crowgpt's models and a run
#: routinely holds 15 of the 16 GB, so the ~3 GB this model occupies is not
#: spare — it can be the difference between a training run fitting and not. The
#: cost of being wrong in this direction is about ten seconds on the next memo,
#: announced in the log; the cost of being wrong the other way is somebody's
#: overnight run failing to allocate. Raise it with DICTATION_IDLE_MINUTES if the
#: reload ever becomes the annoying half of that trade.
IDLE_MINUTES = float(os.environ.get("DICTATION_IDLE_MINUTES", "15"))


class LazyModel:
    """Whisper, loaded on the first job and dropped again once it goes quiet.

    Deliberate, and about sharing a machine rather than about speed. A worker
    that claimed VRAM at server startup and held it all day on the chance
    somebody dictates would be taking it from the trainer for nothing: memos
    arrive in bursts of a few minutes and then not again for hours.

    So: nothing held until the first job, held through a burst so a session of
    several notes pays the load once, and released once the burst is over. The
    GPU goes back to being free most of the time, which is what it actually is.
    """

    def __init__(self, name, idle_minutes=IDLE_MINUTES):
        self.name = name
        self.idle_seconds = idle_minutes * 60
        self._model = None
        self._last_used = 0.0

    def transcribe(self, path):
        if self._model is None:
            print(f"loading {self.name}…", flush=True)
            started = time.monotonic()
            try:
                self._model = whisper.Model(self.name)
            except Exception as exc:  # noqa: BLE001
                # Almost always the GPU being full — a training run next door.
                # The CPU is ~20x slower and still finishes a 90-second memo, so
                # it beats failing the job and losing the note.
                print(f"could not load on the GPU ({exc}); falling back to the CPU",
                      flush=True)
                self._model = whisper.Model(self.name, device="cpu")
            print(f"loaded on {self._model.device} in "
                  f"{time.monotonic() - started:.1f}s", flush=True)
        self._last_used = time.monotonic()
        try:
            return self._model.transcribe(path)
        finally:
            # After the work, not before: a memo that takes two minutes to
            # transcribe must not be counted as two minutes of idleness.
            self._last_used = time.monotonic()

    def release_if_idle(self) -> bool:
        """Drop the model if nothing has needed it for a while. Frees the VRAM.

        `empty_cache` is the part that actually hands the memory back — without
        it torch keeps the allocation in its own pool and `nvidia-smi` still
        shows it held, which looks exactly like this not working.
        """
        if self._model is None:
            return False
        if time.monotonic() - self._last_used < self.idle_seconds:
            return False
        was = self._model.device
        self._model = None
        gc.collect()
        try:
            import torch  # noqa: PLC0415
            if was == "cuda":
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — freeing is best effort
            pass
        print(f"unloaded {self.name} after "
              f"{self.idle_seconds / 60:.0f} idle minute(s) — the GPU is free "
              f"again; the next memo pays the load", flush=True)
        return True


def process(job, store, model) -> str:
    """Transcribe one memo and finish its job. Returns the text, for the log."""
    row = store.get(job["dictation_id"])
    if not row:
        raise RuntimeError(f"dictation {job['dictation_id']} is gone")
    source = store.path(row)
    if not source.exists():
        raise RuntimeError(f"no audio at {source}")
    wav = whisper.to_wav(source)
    try:
        result = model.transcribe(wav)
    finally:
        wav.unlink(missing_ok=True)
    # Transcript and job state in one call, so "done with no transcript" is a
    # state that cannot be reached. Nothing here is wrapped in a swallowing
    # except: unlike quality on an analysis job, the transcript IS the product.
    store.complete(job["id"], row["id"], result["text"], model=result["model"],
                   language=result["language"], mean_logprob=result["mean_logprob"])
    return result["text"]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    once = "--once" in argv
    db = Path(os.environ.get("FIELD_DB") or DEFAULT_DB)
    store = DictationStore(db, db.parent / "dictations")
    poll = float(os.environ.get("WORKER_POLL", "2"))

    requeued, abandoned = store.reclaim_running()
    if requeued:
        print(f"requeued {requeued} job(s) left running by a stopped worker",
              flush=True)
    if abandoned:
        print(f"failed {abandoned} job(s) that have used up their attempts",
              flush=True)

    model = LazyModel(os.environ.get("DICTATION_MODEL") or whisper.DEFAULT_MODEL)
    # Says whether torch can see the GPU *now*, before anything is loaded, since
    # that is the question this worker exists in its own process to keep
    # answerable. False here means something took CUDA away before torch loaded
    # — the birdnetlib trap — and every transcript will be ~20x slower with no
    # other symptom.
    import torch  # noqa: PLC0415 — cheap here, and only for the ready line
    print(f"transcribe worker ready — {model.name}, cuda "
          f"{torch.cuda.is_available()} — polling {db}"
          f"{' (--once)' if once else ''}", flush=True)

    while True:
        try:
            job = store.claim_next()
        except Exception as exc:  # noqa: BLE001 — a locked DB is a wait, not a death
            if once:
                raise
            print(f"poll failed — {exc}; retrying", flush=True)
            time.sleep(poll)
            continue
        if job is None:
            if once:
                return 0
            model.release_if_idle()
            time.sleep(poll)
            continue
        print(f"job {job['id']}: transcribing dictation {job['dictation_id']}…",
              flush=True)
        started = time.monotonic()
        try:
            text = process(job, store, model)
            # Elapsed and length every time, so the runtime guess in the plan
            # gets replaced by a measurement on day one.
            print(f"job {job['id']}: done in {time.monotonic() - started:.1f}s — "
                  f"{len(text)} characters", flush=True)
        except Exception as exc:  # noqa: BLE001 — one bad memo must not kill the loop
            try:
                store.fail(job["id"], exc)
            except Exception as unrecorded:  # noqa: BLE001
                print(f"job {job['id']}: could not record the failure — {unrecorded}",
                      flush=True)
            print(f"job {job['id']}: error — {exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
