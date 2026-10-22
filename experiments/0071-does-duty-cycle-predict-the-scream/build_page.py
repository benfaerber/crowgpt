"""Build 0071's blind scream-tag page: 30 fresh fair-k8 draws, stats hidden.

The statistic on trial (duty cycle) is written to manifest.json here and
NOT into the page's post-rating reveal — a number visible mid-page trains
the ear on the instrument and makes the later tags circular. The reveal
shows only the seed.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import torch

from crowgpt.demo import MIN_GRADEABLE_SECONDS, RatingPage
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter

sys.path.insert(0, str(REPO / "experiments" / "0059-what-makes-a-draw-scream"))
from run import describe

OUT = Path(__file__).resolve().parent
PAGE = HERE / "results" / "scream-tag-0071.html"
MODEL = HERE / "results" / "model-fair-k8" / "model.pt"
SPECIES = "american-crow"
SR = 24000
N_CLIPS = 30
SEED_START = 100

INSTRUCTIONS = """
  <h1>Tag the screams</h1>
  <p class="lede">One judgement per clip: does it <b>scream</b>? A scream is the
    sustained, held-note failure you tagged on the 0057 page — "a scream. That is
    a clear example" — as against the pulsed caw-caw-caw of a normal bout.</p>
  <p class="lede"><b>Scream</b> — any part of the clip holds that sustained tone.<br>
    <b>No scream</b> — pulsed caws only, however good or bad they sound otherwise.<br>
    <b>Unsure</b> — genuinely cannot say. A real answer, not a cop-out.</p>
  <p class="caveat"><b>This is not a quality rating.</b> A terrible robotic clip with
    no held note is No scream; a clean-sounding clip that holds one is Scream.</p>
  <p class="caveat">The waveform stays flat until you tag, on purpose — a scream is
    visible as a solid block, and this has to come from the ear.</p>
"""


def main():
    run = Run("0071 — SCREAM TAG PAGE", ["draw", "page"])
    try:
        sampler = Sampler(MODEL, token_dir=None)
        segmenter = Segmenter()
        clips, manifest, seed = [], [], SEED_START
        with run.stage("draw") as stage:
            while len(clips) < N_CLIPS and seed < SEED_START + N_CLIPS * 6:
                flat = sampler.tokens(SPECIES, seed=seed)
                grid = sampler.codec.unflatten(flat)
                audio = np.asarray(sampler.codec.decode(
                    torch.from_numpy(grid))[0], dtype=np.float32)
                seed += 1
                if audio.size / SR < MIN_GRADEABLE_SECONDS:
                    continue
                stats = describe(audio, grid, segmenter)
                clip_id = len(clips)
                clips.append({"audio": audio, "clip_id": clip_id,
                              "seed": seed - 1})
                manifest.append({"clip_id": clip_id, "seed": seed - 1, **stats})
                stage.update(len(clips), N_CLIPS, extra=f"seed {seed}")

        with run.stage("page") as stage:
            page = RatingPage(
                clips, seed=0,
                facts={"model": "model-fair-k8, frozen decoder",
                       "clips": str(len(clips)),
                       "question": "0059's nominated signature, tested blind"},
                title="0071 — tag the screams",
                labels=(("No scream", "no-scream"), ("Unsure", "unsure"),
                        ("Scream", "scream")),
                instructions=INSTRUCTIONS)
            page.write(PAGE)
            (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
            run.note(f"{PAGE} — {len(clips)} clips, stats in manifest.json only")
            stage.update(1, 1)
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(f"open {PAGE}")


if __name__ == "__main__":
    main()
