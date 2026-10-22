"""The same-size control: is it the filter, or is it just less data?

0027 trained on 37,183 caw-filtered bouts and rated 3/14 against the full-corpus
model's 6/14 — worse, though at Fisher p=0.42 not significantly so. But the
filtered model also saw 30,162 sequences against 66,917 and early-stopped at
19,000 steps against 38,000, so the result cannot separate "the filter removed
something useful" from "removing 55% of the corpus costs something".

THIS IS THAT CONTROL. Same total size, same species proportions as the filtered
set, but the bouts within each species chosen AT RANDOM rather than by BirdNET
confidence and call type. Species proportions are matched deliberately: the
filter also shifted American Crow from 71% of the corpus to 58%, and a control
that did not match would confound the filter with the mix.

So the only difference between this model and the filtered one is WHICH bouts
were kept, not how many, and not of what species.

  control beats filtered   -> the filter removed useful audio
  control matches filtered -> the loss was volume, and filtering is neutral
  control loses to filtered -> the filter helped after all, and 0027 read the
                               data loss as a filter failure

Same split seed, same hyperparameters, same everything else.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np

from crowgpt.progress import Run
from crowgpt.tokens import BoutStore, TokenWriter
from crowgpt.train import Trainer

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
TOKENS = DATA / "tokens-randomcontrol"
MODEL = HERE / "results" / "model-randomcontrol"
OUT = Path(__file__).resolve().parent
FILTERED_RESULTS = OUT / "results.json"
STEPS = 40_000
SUBSET_SEED = 17


def main():
    run = Run("0027 CONTROL — SAME SIZE, RANDOM BOUTS",
              ["sample", "tokenise", "train"])
    try:
        store = BoutStore(DATA / "bouts")
        types = {int(k): v for k, v in json.loads(
            (DATA / "bouts" / "call_types.json").read_text())["call_types"].items()}

        with run.stage("sample") as stage:
            # The per-species target is exactly what the filter kept, so the mix
            # is held constant and only the selection rule varies.
            target = {"american-crow": 21685, "carrion-crow": 807,
                      "common-raven": 3771, "eurasian-jackdaw": 4360,
                      "hooded-crow": 887, "rook": 5673}
            by_species = {}
            for position, row in enumerate(store.index):
                by_species.setdefault(row["species"], []).append(position)

            rng = np.random.default_rng(SUBSET_SEED)
            keep = set()
            for species, want in target.items():
                pool = by_species.get(species, [])
                take = min(want, len(pool))
                keep.update(int(p) for p in rng.choice(pool, size=take, replace=False))

            splits = store.split(seed=0)
            selection = {name: [i for i in idxs if i in keep] for name, idxs in splits.items()}
            mix = Counter(store.index[i]["species"] for i in keep)
            stage.say(f"{len(keep)} bouts sampled at random")
            run.note("control mix: " + ", ".join(f"{k} {v}" for k, v in sorted(mix.items())))
            run.note("matches filtered mix: " + str(dict(mix) == target))

        with run.stage("tokenise") as stage:
            if (TOKENS / "manifest.json").exists():
                manifest = json.loads((TOKENS / "manifest.json").read_text())
                stage.say(f"reused {manifest['splits']['train']['sequences']} sequences")
            else:
                manifest = TokenWriter(store, TOKENS, bandwidth=6.0, variants=1,
                                       call_types=types).run(selection)
                stage.say(f"{manifest['splits']['train']['sequences']} sequences")

        with run.stage("train") as stage:
            trainer = Trainer(TOKENS, MODEL, steps=STEPS, n_embd=384, n_layer=8,
                              n_head=6, seed=0, dropout=0.0,
                              memory_budget=1_200_000_000)
            stage.say(f"batch {trainer.effective_batch}, dropout {trainer.config.dropout}")
            history = trainer.run(on_eval=lambda step, val: stage.update(
                step, STEPS, extra=f"val {val:.4f}"))
            last = history["history"][-1]
            run.note(f"best val {history['best_val']:.4f}, final gap {last['gap']:+.4f}")
            (OUT / "control.json").write_text(json.dumps({
                "kept_bouts": len(keep), "subset_seed": SUBSET_SEED,
                "best_val": history["best_val"], "final": last,
                "sequences": manifest["splits"]["train"]["sequences"],
            }, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("done")


if __name__ == "__main__":
    main()
