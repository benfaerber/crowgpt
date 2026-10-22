"""Does the "screaming" live in the codec round-trip, or only in generation?

Ben's words for the generated audio, 2026-08-07: "it sounds so scratchy, and it
sounds almost like a human screaming. So it's kinda taxing to grade." Two of
those words already have owners. "Scratchy" is the codec's — 0024 Part 3 heard
it on the round-trip with no model in it, and 0028 confirmed it blind at 40
points. "Screaming" has never been localised, and where it lives decides where
the next GPU-week goes:

  - if K=8 round-trips of REAL caws already scream, the model's share of the
    defect is near zero and the decoder finetune (TODO.txt) is the whole game
  - if the round-trip is scratchy-but-not-screaming and only the GENERATED rows
    scream, the scream is the model's contribution on top of the codec's
    scratch, and it earns its own experiment before any decoder work
  - K=32 separates a third case: if even 32 codebooks scream, the defect is the
    encoder/decoder pair itself rather than the 8-codebook truncation, and the
    finetune's premise (decode the SAME eight rows better) still stands but the
    ceiling argument changes

This is a DIAGNOSTIC LISTEN, not a sitting: a handful of labelled rows, no
blinding, no rates. 0053 finished at 110 trials (called, α unspent), so nothing
is mid-flight for these clips to leak into. The generated rows are drawn from
model-fair-k8 — the incumbent — by seed order, NOT curated by any instrument:
a best-of would answer "can the model scream less", and the question is what
its typical output does. Seeds are recorded so any clip can be regenerated.

Per 0044, nothing under MIN_GRADEABLE_SECONDS goes on the page.

What Ben is asked, per row: not "which is better" — describe. Which rows have
the SCREAM, as distinct from the scratch? (Description over comparison is the
measured strength: 0038's drift analysis and every structural find so far.)
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

from crowgpt.codec import Codec, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS, ComparePage
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
PAGE = HERE / "results" / "compare-scream-source.html"

SPECIES = "american-crow"
MODEL = HERE / "results" / "model-fair-k8"
N_REAL = 8        # real bouts: raw / K=8 / K=32 per row
N_GENERATED = 6   # typical fair-k8 draws, by seed order, uncurated
SR = 24000


def held_out_bouts(store, limit):
    """One bout per recording — 0028's rule, for 0028's reason."""
    splits = store.split(seed=0)
    held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
    seen, chosen = set(), []
    for i in held:
        recording = store.index[i]["recording_id"]
        if recording in seen:
            continue
        seen.add(recording)
        chosen.append(i)
        if len(chosen) >= limit:
            break
    return chosen


def main():
    run = Run(
        "0057 — DOES THE ROUND-TRIP SCREAM",
        ["roundtrip", "generate", "page"],
    )
    manifest = {"real": [], "generated": []}
    try:
        store = BoutStore(DATA / "bouts")
        codec = Codec(bandwidth=24.0)

        rows = []
        with run.stage("roundtrip") as stage:
            chosen = [
                i for i in held_out_bouts(store, N_REAL * 2)
                if store.index[i]["n_samples"] / SR >= MIN_GRADEABLE_SECONDS
            ][:N_REAL]
            for n, position in enumerate(chosen, 1):
                samples = normalise(store.audio(store.index[position]))
                codes = codec.encode(samples).numpy()[0]
                k8 = codec.decode(torch.from_numpy(codes[:8]))[0]
                k32 = codec.decode(torch.from_numpy(codes))[0]
                rows.append({
                    "species": f"real bout {n}",
                    "arms": [
                        ("RAW — the recording", "untouched", samples, None),
                        ("K=8 round-trip", "the tokenizer the incumbent lives in", k8, None),
                        ("K=32 round-trip", "EnCodec's own ceiling", k32, None),
                    ],
                })
                manifest["real"].append({
                    "bout": int(position),
                    "recording": store.index[position]["recording_id"],
                    "seconds": round(store.index[position]["n_samples"] / SR, 2),
                })
                stage.update(n, len(chosen))
            run.note(f"{len(rows)} real bouts round-tripped at K=8 and K=32")

        with run.stage("generate") as stage:
            sampler = Sampler(MODEL / "model.pt", token_dir=None)
            seed = 0
            while len(manifest["generated"]) < N_GENERATED and seed < 60:
                flat = sampler.tokens(SPECIES, seed=seed)
                grid = sampler.codec.unflatten(flat)
                audio = np.asarray(sampler.codec.decode(torch.from_numpy(grid))[0],
                                   dtype=np.float32)
                seconds = audio.size / SR
                if seconds >= MIN_GRADEABLE_SECONDS:
                    n = len(manifest["generated"]) + 1
                    rows.append({
                        "species": f"generated {n}",
                        "arms": [(
                            "GENERATED — model-fair-k8",
                            f"seed {seed}, by seed order, uncurated",
                            audio, None,
                        )],
                    })
                    manifest["generated"].append(
                        {"seed": seed, "seconds": round(seconds, 2)})
                seed += 1
                stage.update(len(manifest["generated"]), N_GENERATED,
                             extra=f"seed {seed}")
            del sampler
            torch.cuda.empty_cache()
            run.note(f"{len(manifest['generated'])} generated clips, "
                     f"seeds to {seed - 1}, none curated")

        with run.stage("page") as stage:
            ComparePage(rows, {
                "Question": "which rows carry the SCREAM — as distinct from the scratch",
                "Real rows": f"{len(manifest['real'])} held-out {SPECIES}, raw / K=8 / K=32",
                "Generated rows": f"{len(manifest['generated'])} from model-fair-k8, "
                                  "seed order, uncurated",
                "How to answer": "describe, don't rank — which rows scream, which "
                                 "merely scratch, and is RAW ever either",
            }).write(PAGE)
            stage.say(PAGE.name)

        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
        run.note(f"page at {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
