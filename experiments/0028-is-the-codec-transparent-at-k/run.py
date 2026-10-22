"""What does each additional EnCodec codebook actually buy?

WP1 of the timbre plan (since deleted), plus the cheapest kill gate for WP2.

THE PREMISE THIS IS TESTING. 0024 Part 3 established, by ear, that the 6 kbps
round-trip is audibly scratchy against raw ("through the codec it makes it
scratchy and worse"). That verdict reopened the tokenizer and is the founding
evidence for the whole timbre plan. It was given on a LABELLED page — the arms
said "RAW" and "through the codec" — so it has never been collected blind, and
every downstream work package inherits it.

THE CONTRADICTION WORTH RESOLVING. 0024 Part 1 also found that replacing
codebooks 5-7 with noise from the codec's own marginals is INAUDIBLE, and
concluded the artefact lives in codebooks 0-4. Those two results together
predict something the plan does not say out loud: if the last three of eight
rows carry nothing a listener can hear, then rows 8-31 — a strictly smaller
residual, since EnCodec's RVQ is greedy-sequential — should carry less still.
In which case no amount of extra bandwidth fixes the scratch, because the
scratch is in the coarse rows or in the encoder/decoder pair itself, and WP1
returns "nothing is transparent".

That is the outcome to watch for. It is the branch PLAN-TIMBRE spends three
lines on and the rest of the document assuming away.

THREE MEASUREMENTS, TWO OF THEM WITHOUT EARS.

  1. Truncation equality. Codes from a 6 kbps encode must equal the first 8
     rows of a 24 kbps encode. If they do not, every "decode at first-K"
     comparison below is measuring two different encoders, and Codec.keep in
     WP2 needs a different design. Five lines, and it gates the rest.

  2. The distance ladder. Spectral distance (multi-res STFT) and AST-embedding
     Frechet distance from raw, at K in {8, 12, 16, 24, 32}, over ~200 held-out
     bouts one per recording. If these are FLAT across K, the residual tail buys
     nothing measurable and the ear will not find anything either. If they fall
     sharply, WP1 has a real candidate. Either way this is known before a single
     minute of Ben's attention is spent.

  3. Per-stage marginal entropy, all 32 stages. 0014 measured this for eight
     stages on gated windows: [6.30, 7.06, 7.34, 7.50, 7.63, 7.73, 7.80, 7.84]
     bits of a possible 10. Nobody has extended it. WP2 proposes training a
     model to predict stages 8-15 from coarse context; if those stages sit at or
     near 10 bits they are close to incompressible noise, and the extender has
     nothing to learn. This costs minutes and can kill a GPU-day.

WHAT NEEDS EARS, AND HOW MUCH POWER IT HAS. The blinded rating page is three
arms of 20 disjoint bouts: raw, K=8, K=16. Disjoint rather than paired on
purpose — the same call heard three times in a 60-trial sitting is recognisable
even with the waveform hidden, and a listener who notices the repeat is rating
consistency rather than quality. The cost of that choice is power: at 20 per arm
the standard error on a good-rate is about 11 points, so this sitting resolves a
20-point difference and NOT the 10-point equivalence margin PLAN-TIMBRE's gates
are written around. Read it as a screen, not as a proof of transparency. A real
10-point equivalence test needs roughly 200 trials per arm, which is four
sittings, and is only worth spending once the ladder says there is something
there to find.
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

from crowgpt.codec import BANDWIDTH_CODEBOOKS, Codec, normalise
from crowgpt.demo import ComparePage, RatingPage
from crowgpt.embed import AstEmbedder
from crowgpt.metrics import (
    bootstrap_ci,
    codebook_entropy,
    frechet_distance,
    multi_res_stft_distance,
    paired_difference,
)
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
COMPARE_PAGE = HERE / "results" / "compare-codebook-ladder.html"
RATING_PAGE = HERE / "results" / "rate-codec-blind.html"

SPECIES = "american-crow"
N_BOUTS = 200          # for the automated ladder
N_COMPARE = 12         # labelled diagnostic rows
N_RATE_PER_ARM = 20    # blinded sitting, disjoint bouts per arm
KS = (8, 12, 16, 24, 32)
RATE_ARMS = (("raw", None), ("k8", 8), ("k16", 16))


def held_out_bouts(store, limit):
    """One bout per recording. Bouts are consecutive slices of one file, so
    held[:n] is n pieces of a single recording wearing a survey's clothes."""
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


def check_truncation(codec6, codec24, samples):
    """A 6 kbps encode must be the first 8 rows of a 24 kbps encode."""
    low = codec6.encode(samples).numpy()[0]
    high = codec24.encode(samples).numpy()[0]
    width = min(low.shape[1], high.shape[1])
    equal = bool(np.array_equal(low[:, :width], high[:8, :width]))
    return {
        "equal": equal,
        "rows_compared": 8,
        "frames_compared": int(width),
        "mismatched_frames": int((low[:, :width] != high[:8, :width]).any(axis=0).sum()),
    }


def main():
    run = Run(
        "0028 — WHAT DOES EACH CODEBOOK BUY",
        ["equality", "encode", "entropy", "ast", "pages"],
    )
    results = {}
    try:
        store = BoutStore(DATA / "bouts")
        chosen = held_out_bouts(store, N_BOUTS + N_RATE_PER_ARM * len(RATE_ARMS))
        ladder_idx = chosen[:N_BOUTS]
        # Disjoint from the ladder AND from each other, so no bout is heard twice.
        rating_pool = chosen[N_BOUTS:]

        codec24 = Codec(bandwidth=24.0)

        with run.stage("equality") as stage:
            codec6 = Codec(bandwidth=6.0)
            probe = normalise(store.audio(store.index[ladder_idx[0]]))
            results["truncation"] = check_truncation(codec6, codec24, probe)
            del codec6
            torch.cuda.empty_cache()
            verdict = "EQUAL" if results["truncation"]["equal"] else "DIFFERENT — keep design changes"
            stage.say(f"6 kbps vs first 8 rows of 24 kbps: {verdict}")
            run.note(f"truncation: {verdict}")

        raw_clips, decoded = [], {k: [] for k in KS}
        all_codes = []
        with run.stage("encode") as stage:
            for n, position in enumerate(ladder_idx, 1):
                samples = normalise(store.audio(store.index[position]))
                codes = codec24.encode(samples).numpy()[0]
                all_codes.append(codes)
                raw_clips.append(samples)
                for k in KS:
                    decoded[k].append(codec24.decode(torch.from_numpy(codes[:k]))[0])
                stage.update(n, len(ladder_idx))

        with run.stage("entropy") as stage:
            pooled = np.concatenate(all_codes, axis=1)
            bits = codebook_entropy(pooled)
            results["stage_entropy_bits"] = [round(b, 3) for b in bits]
            results["frames_pooled"] = int(pooled.shape[1])
            tail = float(np.mean(bits[8:]))
            stage.say(f"stages 0-7 mean {np.mean(bits[:8]):.2f} bits · stages 8-31 mean {tail:.2f} bits")
            run.note(f"fine-stage entropy (8-31): {tail:.2f} bits of 10 "
                     f"— {'near-uniform, WP2 has little to learn' if tail > 9.5 else 'structured'}")

        with run.stage("ast") as stage:
            stft = {}
            for k in KS:
                stft[k] = [
                    multi_res_stft_distance(r, d) for r, d in zip(raw_clips, decoded[k])
                ]
                stage.update(KS.index(k) + 1, len(KS) + 1)
            results["stft"] = {
                str(k): {
                    "mean": float(np.mean(v)),
                    "ci": bootstrap_ci(np.array(v)),
                }
                for k, v in stft.items()
            }
            results["stft_vs_k8"] = {
                str(k): paired_difference(np.array(stft[8]), np.array(stft[k]))
                for k in KS if k != 8
            }

            # CALIBRATION, WITHOUT WHICH THE LADDER IS UNREADABLE. "STFT 1.035"
            # is not a quantity anyone has intuition for, and neither is "FAD
            # 13.25". Two controls put a scale under them:
            #
            #   ceiling — each raw bout against a DIFFERENT raw bout. This is
            #     what the metric reads for two unrelated crow recordings, so a
            #     round-trip scoring near it is barely closer to its own source
            #     than to a stranger's, and the number is measuring the metric's
            #     insensitivity rather than the codec's quality.
            #   floor — FAD between two disjoint halves of the raw set. Same
            #     distribution on both sides, so whatever this reads is sampling
            #     noise, and a codec arm is only meaningfully far from raw if it
            #     clears it.
            rotated = raw_clips[1:] + raw_clips[:1]
            results["stft_ceiling_unrelated"] = float(np.mean([
                multi_res_stft_distance(a, b) for a, b in zip(raw_clips, rotated)
            ]))

            # EVERY FAD HERE IS 100 vs 100. Frechet distance on 768-dimensional
            # AST embeddings estimates a 768x768 covariance, so at these sample
            # sizes it is badly biased upward and the bias depends on n — which
            # makes a 200-vs-200 arm and a 100-vs-100 control incomparable, and
            # would have shown the best arm scoring "closer than raw is to
            # itself". Matching n is what makes the floor a floor.
            embedder = AstEmbedder()
            raw_emb = embedder.embed(raw_clips, 24000)
            half = len(raw_emb) // 2
            results["ast_fad_floor_raw_vs_raw"] = float(
                frechet_distance(raw_emb[:half], raw_emb[half:])
            )
            results["ast_fad"] = {
                str(k): float(frechet_distance(
                    raw_emb[:half], embedder.embed(decoded[k], 24000)[half:]
                ))
                for k in KS
            }
            stage.update(len(KS) + 1, len(KS) + 1)
            run.note(f"scale — unrelated real bouts STFT {results['stft_ceiling_unrelated']:.3f} "
                     f"(ceiling) · raw-vs-raw FAD {results['ast_fad_floor_raw_vs_raw']:.2f} (floor)")
            ladder = " · ".join(f"K{k}={results['stft'][str(k)]['mean']:.3f}" for k in KS)
            stage.say(f"STFT to raw: {ladder}")
            run.note("STFT distance to raw — " + ladder)
            run.note("AST FAD to raw — " + " · ".join(
                f"K{k}={results['ast_fad'][str(k)]:.2f}" for k in KS))

        with run.stage("pages") as stage:
            rows = []
            for n, position in enumerate(ladder_idx[:N_COMPARE]):
                arms = [("RAW — the recording", "untouched", raw_clips[n], None)]
                arms += [
                    (f"K={k}", f"{k} codebooks, {k * 0.75:g} kbps", decoded[k][n], None)
                    for k in KS
                ]
                rows.append({"species": f"bout {n + 1}", "arms": arms})
            ComparePage(rows, {
                "Question": "how many codebooks before the round-trip is transparent",
                "Rows": len(rows),
                "Arms": "raw + " + ", ".join(f"K={k}" for k in KS),
                "Bouts": "held-out American Crow, one per recording",
            }).write(COMPARE_PAGE)

            clips, cursor = [], 0
            for arm, k in RATE_ARMS:
                for position in rating_pool[cursor : cursor + N_RATE_PER_ARM]:
                    samples = normalise(store.audio(store.index[position]))
                    if k is None:
                        audio = samples
                    else:
                        codes = codec24.encode(samples).numpy()[0]
                        audio = codec24.decode(torch.from_numpy(codes[:k]))[0]
                    clips.append({
                        "audio": audio, "sr": 24000, "arm": arm,
                        "bout": int(position),
                        "recording": store.index[position]["recording_id"],
                    })
                cursor += N_RATE_PER_ARM
            RatingPage(clips, {
                "Question": "is the codec round-trip audible at all, blind",
                "Arms": "raw / K=8 / K=16, 20 disjoint bouts each",
                "Model involved": "none",
                "Power": "resolves a ~20-point difference, not a 10-point one",
            }, seed=0, title="Which of these sound good?").write(RATING_PAGE)
            stage.say(f"{COMPARE_PAGE.name} · {RATING_PAGE.name}")

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
        run.note(f"wrote {OUT / 'results.json'}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
