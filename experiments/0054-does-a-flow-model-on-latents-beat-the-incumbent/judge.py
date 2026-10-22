"""Four-arm BirdNET judgement of the flow model.

THE ARMS, and the fourth is the only one that makes the third mean anything.

  A_real            real held-out bouts
  B_real_continuous the same bouts through the continuous cascade, no model.
                    The CEILING — anything the representation threw away is
                    already gone here, so B-versus-C is the model's score and
                    A-versus-C is the model plus the codec.
  C_flow            the model
  D_marginal        each channel drawn independently from its own train mean and
                    std, decoded the same way. Right marginals, NO temporal
                    structure. If C cannot beat D, the model has learned the
                    shape of the latent distribution and nothing about time.

D IS THE CONTINUOUS ANALOGUE OF THE UNIGRAM CONTROL, and it is what the original
README says the whole judgement turns on: tokens drawn from the right marginal
scored ZERO, "so 38.9% is structure the model learned rather than an artefact of
the ambience, the decoder or the 3-second framing". The same logic needs the same
control, rebuilt for a representation that has no codebook to draw from.

EVERY ARM IS 3.0 SECONDS OF REAL AMBIENCE. birdnetlib breaks out of its chunking
loop under 1.5 s and returns zero detections with no error, so a short clip judged
alone reads as rejection when nothing was analysed. And digital silence is itself
out of distribution and depresses confidence, so padding is not an option either.

THE CIRCULARITY CAVEAT IS NOT OPTIONAL HERE. 0022 recorded that BirdNET selected
this corpus, so every detection number in the project is partly a measure of
agreement with the thing that chose the training data — crowgpt scoring ABOVE
real audio (71.7% vs 65.0%) is the symptom. This is a sanity check that can say
"the model produces nothing crow-like at all". It cannot rank two models and it
is not the verdict. The verdict is a blinded sitting.
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

from crowgpt.codec import normalise
from crowgpt.judge import Ambience, BirdNetJudge
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
LATENTS = DATA / "latents"
# `python judge.py <model-dir>` so two checkpoints can be scored by one rig.
MODEL = (Path(sys.argv[1]) if len(sys.argv) > 1
         else HERE / "results" / "model-flow")
SPECIES = "american-crow"
PER_ARM = 36
MIN_SECONDS = 1.0
SR = 24000


def held_out(store, count, rng):
    """Real test-split bouts, one per recording, over the gradeable floor."""
    seen, rows = set(), []
    for i in store.split(seed=0)["test"]:
        row = store.index[i]
        if row["species"] != SPECIES or row["recording_id"] in seen:
            continue
        if row["n_samples"] / SR < MIN_SECONDS:
            continue
        seen.add(row["recording_id"])
        rows.append(row)
    rng.shuffle(rows)
    return rows[:count]


def marginal_clip(sampler, frames, generator):
    """Per-channel Gaussian noise at the corpus's own mean and spread.

    Drawn in NORMALISED space and then denormalised by the same statistics the
    model's output goes through, so the two arms differ in temporal structure and
    in nothing else.
    """
    shape = (1, int(frames), sampler.model.config.dim)
    latent = torch.randn(shape, device=sampler.device, generator=generator)
    latent = latent * sampler.std + sampler.mean
    return sampler.codec.decode(latent.transpose(1, 2))[0]


def main():
    from crowgpt.flow_sample import FlowSampler

    run = Run("0054 — FOUR-ARM JUDGE", ["build", "score", "report"])
    try:
        rng = np.random.default_rng(0)
        store = BoutStore(DATA / "bouts")
        sampler = FlowSampler(MODEL, LATENTS)
        generator = torch.Generator(device=sampler.device).manual_seed(54)

        with run.stage("build") as stage:
            rows = held_out(store, PER_ARM, rng)
            from crowgpt.corpus import Corpus

            # `recordings()` returns a DICT of slug -> [Recording], so iterating
            # it yields species slugs as strings. `Ambience._collect` reads
            # `rec.path` inside a bare `except Exception: continue`, so strings
            # are dropped one by one, the clip list ends up empty, and it falls
            # back to a single array of DIGITAL SILENCE. Every arm then gets
            # judged against silence, which is out of distribution and depresses
            # confidence on all four at once — a rig failure wearing the costume
            # of a uniformly disappointing model, with nothing printed.
            recordings = [r for recs in Corpus().recordings().values() for r in recs[:6]]
            if not recordings or isinstance(recordings[0], str):
                raise SystemExit(
                    "no corpus recordings for ambience — every arm would be judged "
                    "in silence, which depresses all four and looks like a bad model")
            ambience = Ambience(recordings, wanted=24, seed=0)

            arms = {k: [] for k in ("A_real", "B_real_continuous", "C_flow", "D_marginal", "E_incumbent")}
            for row in rows:
                real = normalise(store.audio(row))
                arms["A_real"].append(ambience.place(real))
                through = sampler.codec.roundtrip(real)[0][: real.size]
                arms["B_real_continuous"].append(ambience.place(through))
                stage.update(len(arms["A_real"]), PER_ARM, extra="real")

            clips = sampler.generate(count=PER_ARM, steps=32, seed=54)
            for clip in clips:
                arms["C_flow"].append(ambience.place(clip))
                arms["D_marginal"].append(
                    ambience.place(marginal_clip(sampler, max(8, len(clip) // 320), generator)))

            # E IS THE WHOLE POINT OF RUNNING THIS AGAIN. Comparing C against the
            # README's 38.9%/61.1%/66.7% would be a cross-sitting comparison
            # against numbers from a different corpus, a different codec and a
            # different BirdNET invocation — the exact mistake 0038 caught costing
            # 33 points and 0023 caught costing a whole quality verdict. The
            # incumbent generates here, in this process, into this ambience,
            # scored by this judge.
            #
            # FAIR DESPITE THE CORPUS DIFFERENCE, and the reason is measured: the
            # incumbent is a v1-token model and the flow model is v2, but neither
            # C arm touches held-out audio — both are pure generation — and 0050
            # found v1 against v2 a dead heat by ear (0.51, CI [0.36, 0.67]).
            from crowgpt.sample import Sampler

            incumbent = Sampler(HERE / "results" / "model-fair-k8" / "model.pt",
                                token_dir=DATA / "tokens")
            for i in range(PER_ARM):
                audio = incumbent.audio(SPECIES, seed=int(rng.integers(2**31)),
                                        max_frames=225)
                arms["E_incumbent"].append(ambience.place(audio))
                stage.update(i + 1, PER_ARM, extra="incumbent")
            stage.say(f"{sum(len(v) for v in arms.values())} clips")

        judge = BirdNetJudge()
        results = {}
        with run.stage("score") as stage:
            for i, (name, entries) in enumerate(arms.items()):
                scores = [c if c is not None else 0.0 for c in judge.confidences(entries)]
                scores = np.array(scores)
                detected = float((scores >= judge.crow_min).mean())
                results[name] = {"n": len(entries), "detected": round(detected, 4),
                                 "mean_conf": round(float(scores.mean()), 4),
                                 "median_conf": round(float(np.median(scores)), 4)}
                stage.update(i + 1, len(arms), extra=name)

        with run.stage("report") as stage:
            print(f"\n{'arm':20s} {'n':>4s} {'detected':>10s} {'mean conf':>10s}")
            for name in ("A_real", "B_real_continuous", "C_flow", "D_marginal", "E_incumbent"):
                r = results[name]
                print(f"{name:20s} {r['n']:4d} {r['detected']:10.1%} {r['mean_conf']:10.4f}")
            ceiling = results["B_real_continuous"]["detected"]
            got = results["C_flow"]["detected"]
            share = got / ceiling if ceiling else float("nan")
            print(f"\nB vs C is the comparison: {got:.1%} of a {ceiling:.1%} ceiling "
                  f"= {share:.0%} of it")
            print(f"D control at {results['D_marginal']['detected']:.1%} — if this is "
                  f"not near zero, C's score is not evidence of learned structure")
            print("\nBirdNET selected this corpus (0022). Sanity check, not a verdict.")
            results["share_of_ceiling"] = round(float(share), 4)
            (OUT / "judge.json").write_text(json.dumps(results, indent=2) + "\n")
            stage.say(f"C {got:.1%} of ceiling {ceiling:.1%}")
        run.note(f"C {got:.1%} · ceiling {ceiling:.1%} · control "
                 f"{results['D_marginal']['detected']:.1%}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
