"""Did the bigger corpus actually help, by ear?

Ben, after 0049: *"I think both models are much better than they once were. I
think the more data helped."*

0049 could not test that. It compared two v2 models against each other; neither
was compared against anything trained on the old corpus, and 0038 established
that absolute rates are not comparable across sittings even when the real anchor
holds. So the claim is untested and it is cheap to test.

IT IS NOT IN CONFLICT WITH 0048, WHICH IS WHY IT IS WORTH RUNNING. 0048 found
validation loss flat past 50% of the corpus and concluded more data would not
help. That measured LOSS. Ben is describing audible quality, and rule three of
this project — measured twice, in 0023 and 0027 — is that the two come apart. A
larger corpus could leave loss flat and still sound better.

WHAT ACTUALLY CHANGED, WHICH IS LESS THAN IT LOOKS. The sweep grew the whole
corpus by 57%, but almost none of that is the species being generated:

    american-crow   57,479 -> 59,654 bouts   (+4%),  29.6 -> 30.8 hours
    whole corpus    81,389 -> 127,553 bouts  (+57%), 41.7 -> 64.3 hours

So this is very nearly "6 species against 46 at the same American Crow" — which
0049 already answered as neutral. The honest expectation is therefore a null, and
the experiment is worth running anyway for two reasons: a null closes a claim
that would otherwise sit around as folklore, and if it is NOT a null then
something improved that the corpus numbers cannot explain, which would be far
more interesting than confirming what we think.

THE ARMS. `model-fair-k8` is the v1 incumbent: all 6 species of the old corpus,
81,389 bouts. `model-multi-v2` is its exact recipe — d384/L8/H6, effective batch
18, dropout 0, 30,000 steps — on all 46 species of the new one, 127,553 bouts.
Multi rather than mono on purpose: fair-k8 trained on every species it had, so
the matching arm is the one that trained on every species it has.

The vocabularies differ, 8,207 against 8,247, and that does not matter here
because the comparison is audio. It would matter if this compared losses, which
it does not.
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

from crowgpt.progress import Run

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
BOUTS = DATA / "bouts"
RESULTS = HERE / "results"
PAGE = RESULTS / "rate-corpus-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
ARMS = (("v2_46sp", RESULTS / "model-multi-v2"), ("v1_6sp", RESULTS / "model-fair-k8"))
N_PAIRS, N_CATCH = 50, 10
MIN_SECONDS = 1.0


def main():
    run = Run("0050 — DID THE BIGGER CORPUS HELP", ["generate", "page"])
    try:
        from crowgpt.codec import normalise
        from crowgpt.demo import PairPage
        from crowgpt.sample import Sampler
        from crowgpt.tokens import BoutStore

        made, done = {}, 0
        total = N_PAIRS * 2 + N_CATCH

        with run.stage("generate") as stage:
            for name, folder in ARMS:
                sampler = Sampler(folder / "model.pt", token_dir=None)
                kept, seed = [], 0
                while len(kept) < N_PAIRS and seed < N_PAIRS * 8:
                    audio = sampler.audio(SPECIES, temperature=1.0, top_k=200,
                                          seed=31000 + seed)
                    seed += 1
                    if len(audio) / 24000 >= MIN_SECONDS:
                        kept.append(normalise(np.asarray(audio, dtype=np.float32)))
                        done += 1
                        stage.update(done, total, extra=f"{name} {len(kept)}/{N_PAIRS}")
                made[name] = kept
                del sampler
                torch.cuda.empty_cache()

            # Catch bouts from the CURRENT store; every earlier sitting drew from
            # v1, whose indices no longer mean the same thing after the rebuild.
            store = BoutStore(BOUTS)
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, ordered = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                ordered.append(i)
            pool = [i for i in ordered
                    if store.index[i]["n_samples"] / 24000 >= MIN_SECONDS]
            made["real"] = [normalise(store.audio(store.index[i]))
                            for i in pool[:N_CATCH]]
            done += N_CATCH
            stage.update(done, total, extra="real")

        with run.stage("page") as stage:
            def clip(name, i):
                return {"audio": made[name][i], "sr": 24000, "arm": name}

            pairs = [{"a": clip("v2_46sp", i), "b": clip("v1_6sp", i)}
                     for i in range(N_PAIRS)]
            pairs += [{"a": clip("real", i), "b": clip("v1_6sp", N_PAIRS - 1 - i),
                       "catch": True} for i in range(N_CATCH)]
            PairPage(pairs, {
                "Question": "did the bigger corpus actually help, by ear",
                "Pairs": f"{N_PAIRS} v2 (46 species, 64.3 h) vs v1 (6 species, 41.7 h) "
                         f"· {N_CATCH} real vs v1 (catch)",
                "Same recipe": "both d384 L8 H6, effective batch 18, dropout 0, "
                               "30,000 steps — only the corpus differs",
                "Caveat": "American Crow itself grew only 4%; the other 53% is "
                          "other species",
                "Clips": f"all >= {MIN_SECONDS}s; sides and play order balanced 2x2",
            }, seed=0).write(PAGE)
            (OUT / "pairs.json").write_text(json.dumps(
                [{"a": p["a"]["arm"], "b": p["b"]["arm"], "catch": p.get("catch", False)}
                 for p in pairs], indent=2))
            stage.say(str(PAGE))
            run.note(f"{len(pairs)} pairs -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
