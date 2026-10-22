"""Generation worker — answers the dashboard's Crow Chat with actual caws.

Polls `generations`, samples a clip from the model the request addressed, and
writes the wav back. The shared SQLite DB is the only coupling to the API,
exactly as it is for the other two workers.

Runs under crowgpt's venv for the reason transcribe_worker.py documents at
length: birdnetlib permanently blinds torch to the GPU in-process, so torch
work lives in processes that never import the analyzer. This worker imports
crowgpt and nothing from analyzer.

Three models answer, each by its own recipe. The releases (CrowGPT1, CrowGPT2)
come whole from crowgpt.releases — checkpoint, decoder state and sampling in
one piece, because dropping a leg of a release recipe produces different audio
under the same name. model-calltype is not a release and its recipe is stated
here: it is the one checkpoint whose manifest carries call types, so it alone
answers the buttons, and its sampling stays at the defaults (T 1.0 / k 200 /
225 frames = 3 s) — 0069's T 1.1 adoption was measured on longctx and does not
transfer sight unseen. A request addressed to a release has call_type NULL by
the store's rule; the release models' manifests carry no call types, so the
prefix simply never writes one.

  ../crowgpt/.venv/bin/python worker/generate_worker.py
  # one pass then exit (cron / test):
  ../crowgpt/.venv/bin/python worker/generate_worker.py --once
  # against a specific DB:  FIELD_DB=/path/field.db  python worker/generate_worker.py
  # hold the model longer:  GENERATION_IDLE_MINUTES=60
"""

import gc
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
REPO = FIELDSERVER.parent
sys.path.insert(0, str(FIELDSERVER / "src"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt import releases  # noqa: E402 — stdlib-only until .sampler()
from fieldserver.stores.generations import (  # noqa: E402
    CALL_TYPES, MODELS, GenerationStore)

DEFAULT_DB = FIELDSERVER / "instance" / "field.db"

SAMPLE_RATE = 24_000


class Recipe:
    """One addressable model: its checkpoint, decoder and sampling, in one piece."""

    def __init__(self, name, checkpoint, decoder_state, species, sampling,
                 call_types=()):
        self.name = name
        self.checkpoint = checkpoint
        self.decoder_state = decoder_state
        self.species = species
        self.sampling = sampling
        self.call_types = tuple(call_types)

    @classmethod
    def from_release(cls, name):
        release = releases.load(name)
        return cls(name, release.checkpoint, release.decoder_state,
                   release.species, release.sampling)


RECIPES = {
    # The 0063 adversarial decoder is checkpoint-agnostic — tokens are
    # bit-identical across models — so calltype clips get the same decode
    # quality the listening sittings graded, not the frozen decoder they
    # would default to.
    "model-calltype": Recipe(
        "model-calltype",
        REPO / "crowgpt" / "results" / "model-calltype" / "model.pt",
        "finetuned", "american-crow",
        {"temperature": 1.0, "top_k": 200, "max_frames": 225},
        call_types=CALL_TYPES),
    "crowgpt1": Recipe.from_release("crowgpt1"),
    "crowgpt2": Recipe.from_release("crowgpt2"),
    # The standing crowgpt3 candidate at its serving cell — 0075's batch-32
    # retrain, in chat for the ear test, not a release. See the 0075 README.
    "model-longctx-ct-b32": Recipe(
        "model-longctx-ct-b32",
        REPO / "crowgpt" / "results" / "model-longctx-ct-b32" / "model.pt",
        "finetuned", "american-crow",
        {"temperature": 1.1, "top_k": 200, "max_frames": 460},
        call_types=CALL_TYPES),
}

if set(RECIPES) != set(MODELS):
    raise RuntimeError(
        f"the server offers {sorted(MODELS)} but this worker answers "
        f"{sorted(RECIPES)} — fix one list")

#: Same trade as the transcriber's fifteen minutes: the GPU trains models most
#: days, and a chat that goes quiet for hours must not hold VRAM on the chance
#: somebody presses a button. Being wrong costs seconds on the next request.
IDLE_MINUTES = float(os.environ.get("GENERATION_IDLE_MINUTES", "15"))


class LazySampler:
    """One resident Sampler, loaded on request and dropped once chat goes quiet.

    One at a time, not one per recipe: the GPU trains models most days, so a
    chat that switches models pays a checkpoint load rather than holding
    several checkpoints' VRAM. One Sampler still serves many generations —
    tokens()/audio() are stateless apart from the seed — so a burst on one
    model pays its load once.
    """

    def __init__(self, idle_minutes=IDLE_MINUTES):
        self.idle_seconds = idle_minutes * 60
        self._name = None
        self._sampler = None
        self._last_used = 0.0

    def audio(self, recipe, call_type, seed):
        if self._name != recipe.name:
            self._drop()
            from crowgpt.sample import Sampler  # noqa: PLC0415 — torch, on demand
            print(f"loading {recipe.name}…", flush=True)
            started = time.monotonic()
            sampler = Sampler(recipe.checkpoint,
                              decoder_state=recipe.decoder_state)
            missing = set(recipe.call_types) - set(
                sampler.vocabulary.call_types or ())
            if missing:
                raise RuntimeError(
                    f"{recipe.name} cannot condition on: "
                    f"{', '.join(sorted(missing))}")
            self._sampler = sampler
            self._name = recipe.name
            print(f"loaded on {sampler.device} in "
                  f"{time.monotonic() - started:.1f}s", flush=True)
        try:
            return self._sampler.audio(recipe.species, call_type=call_type,
                                       seed=seed, **recipe.sampling)
        finally:
            # After the work, not before: a slow generation must not be counted
            # as idle time.
            self._last_used = time.monotonic()

    def release_if_idle(self) -> bool:
        if self._sampler is None:
            return False
        if time.monotonic() - self._last_used < self.idle_seconds:
            return False
        name = self._name
        self._drop()
        print(f"unloaded {name} after {self.idle_seconds / 60:.0f} idle "
              "minute(s) — the GPU is free again", flush=True)
        return True

    def _drop(self):
        if self._sampler is None:
            return
        was = self._sampler.device
        self._sampler = None
        self._name = None
        gc.collect()
        try:
            import torch  # noqa: PLC0415
            if was == "cuda":
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — freeing is best effort
            pass


def process(job, store, sampler) -> float:
    """Generate one clip and finish its row. Returns the duration, for the log."""
    import numpy as np  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415

    recipe = RECIPES[job["model"]]
    audio = sampler.audio(recipe, job["call_type"], seed=job["seed"])
    peak = float(np.max(np.abs(audio))) or 1.0
    ref = store.allocate_ref()
    # Peak-normalised PCM_16, the house rule for anything a human listens to —
    # pool._write is the precedent.
    sf.write(store.path({"storage_ref": ref}), audio / peak * 0.95, SAMPLE_RATE,
             format="WAV", subtype="PCM_16")
    duration = len(audio) / SAMPLE_RATE
    store.complete(job["id"], ref, duration, recipe.name,
                   recipe.sampling["temperature"], recipe.sampling["top_k"])
    return duration


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    once = "--once" in argv
    db = Path(os.environ.get("FIELD_DB") or DEFAULT_DB)
    store = GenerationStore(db, db.parent / "generated")
    poll = float(os.environ.get("WORKER_POLL", "2"))

    # The server runs its migrations at startup and `make field` starts both of
    # us together, so on a fresh schema this table may not exist for a few
    # seconds yet. Crashing here is how the first boot of this worker died
    # silently — wait for the migration instead.
    while True:
        try:
            requeued, abandoned = store.reclaim_running()
            break
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc) or once:
                raise
            print("waiting for the server's migration to create generations…",
                  flush=True)
            time.sleep(poll)
    if requeued:
        print(f"requeued {requeued} request(s) left running by a stopped worker",
              flush=True)
    if abandoned:
        print(f"failed {abandoned} request(s) that have used up their attempts",
              flush=True)

    sampler = LazySampler()
    import torch  # noqa: PLC0415 — cheap here, and only for the ready line
    print(f"generate worker ready — {', '.join(RECIPES)}, cuda "
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
            sampler.release_if_idle()
            time.sleep(poll)
            continue
        print(f"request {job['id']}: {job['model']} generating "
              f"{job['call_type'] or 'a caw'!r} (seed {job['seed']})…",
              flush=True)
        started = time.monotonic()
        try:
            duration = process(job, store, sampler)
            print(f"request {job['id']}: done in "
                  f"{time.monotonic() - started:.1f}s — {duration:.1f}s of audio",
                  flush=True)
        except Exception as exc:  # noqa: BLE001 — one bad request must not kill the loop
            try:
                store.fail(job["id"], exc)
            except Exception as unrecorded:  # noqa: BLE001
                print(f"request {job['id']}: could not record the failure — "
                      f"{unrecorded}", flush=True)
            print(f"request {job['id']}: error — {exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
