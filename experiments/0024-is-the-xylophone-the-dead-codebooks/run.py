"""Is the "xylophone" the three codebooks that learned nothing?

Ben has described the defect twice without being asked to: "choppy and changes
tone rapidly", "modem sounds", and the output is bimodal — pretty good or pretty
bad with no middle. 0019 measured, independently and in bits, that stages 5, 6
and 7 predict no better than drawing from the codec's own marginal. Three of
eight codebooks carry no learned signal.

Those are plausibly the same fact reached from two directions, and nobody has
put it to the ear. This does.

THREE TREATMENTS OF EVERY SEQUENCE, decoded from the same tokens so the only
difference is what the fine stages contain:

  full              all eight codebooks as generated — what ships today
  coarse + marginal keep 0-4, redraw 5-7 from the codec's per-codebook marginals
  coarse only       keep 0-4, decode from five stages and drop the rest

If `full` and `coarse + marginal` are indistinguishable, 0019's measurement is
confirmed by ear: the model's fine stages carry no more than noise with the right
histogram. If `coarse only` is cleaner than both, those stages are actively
costing quality and removing them is a change worth making.

REAL BOUTS GET THE SAME THREE TREATMENTS, and that is the control that makes the
page readable. Five codebooks is a lower bitrate whatever produces it, so if
`coarse only` sounds muffled the question is immediately whether that is the
model or the codec. Real audio through the identical path answers it: muffled
there too means the bitrate did it, clean there means the model did.

No BirdNET anywhere — it cannot hear "robotic", which is the entire reason this
page exists.
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

from crowgpt.demo import ComparePage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
MODEL = HERE / "results" / "sweep-0023" / "batch-32-dropout-0" / "model.pt"
TOKENS = DATA / "tokens-calltype"
PAGE = HERE / "results" / "compare-codebooks.html"
OUT = Path(__file__).resolve().parent

KEEP = 5           # codebooks 0-4, the ones 0019 measured as carrying signal
PER_ARM = 12       # generated bouts, and the same number of real ones
SPECIES = "american-crow"


def treatments(codes, marginals, codec):
    """The same frames decoded three ways. codes is [K, frames]."""
    full = codec.decode(torch.from_numpy(codes))[0]  # noqa: E501

    swapped = codes.copy()
    rng = np.random.default_rng(0)
    for stage in range(KEEP, codes.shape[0]):
        swapped[stage] = rng.choice(len(marginals[stage]), size=codes.shape[1],
                                    p=marginals[stage])
    marginal = codec.decode(torch.from_numpy(swapped))[0]

    coarse = codec.decode(torch.from_numpy(codes[:KEEP]))[0]
    return full, marginal, coarse


def main():
    run = Run("0024 — IS THE XYLOPHONE THE DEAD CODEBOOKS",
              ["generated", "real", "page"])
    rows = []
    try:
        from crowgpt.sample import Sampler

        sampler = Sampler(MODEL, token_dir=TOKENS)
        codec = sampler.codec
        marginals = sampler._marginals()

        with run.stage("generated") as stage:
            for i in range(PER_ARM):
                flat = sampler.tokens(SPECIES, seed=5000 + i)
                if flat.size == 0:
                    continue
                codes = codec.unflatten(flat)
                full, marginal, coarse = treatments(codes, marginals, codec)
                rows.append({"species": f"generated {i + 1}", "arms": [
                    ("full 8 codebooks", "what ships today", full, None),
                    ("coarse + marginal", f"{KEEP} kept, rest redrawn", marginal, None),
                    ("coarse only", f"{KEEP} codebooks, rest dropped", coarse, None),
                ]})
                stage.update(i + 1, PER_ARM)
            stage.say(f"{len(rows)} generated bouts")

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts")
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            made = 0
            for position in held:
                if made >= PER_ARM:
                    break
                from crowgpt.codec import normalise
                samples = normalise(store.audio(store.index[position]))
                codes = codec.encode(samples).numpy()[0]
                full, marginal, coarse = treatments(codes, marginals, codec)
                rows.append({"species": f"REAL {made + 1}", "arms": [
                    # THE ONLY UNTOUCHED AUDIO ON THE PAGE, and its absence was a
                    # hole. Every other track is a codec round-trip, so a listener
                    # calling the real rows choppy had nothing to compare against
                    # and the codec could not be accused or cleared. This is what
                    # the tokenizer costs before any model is involved.
                    ("RAW — no codec", "the recording itself", samples, None),
                    ("full 8 codebooks", "real, through the codec", full, None),
                    ("coarse + marginal", f"{KEEP} kept, rest redrawn", marginal, None),
                    ("coarse only", f"{KEEP} codebooks, rest dropped", coarse, None),
                ]})
                made += 1
                stage.update(made, PER_ARM)
            stage.say(f"{made} real bouts")

        with run.stage("page") as stage:
            facts = {
                "Kept codebooks": f"{KEEP} of 8",
                "Dead stages (0019)": "5, 6, 7",
                "Checkpoint": "batch-32-dropout-0",
                "Rows": len(rows),
            }
            ComparePage(rows, facts).write(PAGE)
            stage.say(str(PAGE))
            (OUT / "results.json").write_text(json.dumps({
                "keep": KEEP, "generated": PER_ARM, "real": PER_ARM,
                "page": str(PAGE),
            }, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE)


if __name__ == "__main__":
    main()
