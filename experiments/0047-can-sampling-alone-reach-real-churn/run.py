"""Can any sampling knob reach real audio's coarse-codebook churn?

0046 found the defect behind Ben's "crow + modem": the generator holds coarse
codes too long. Stage 0 changes on 80% of adjacent frame pairs where real audio
changes on 87%, and stages 3-7 sit at or above real, so it is specific to the
stage carrying structure and pitch. A held code sustains one spectral shape for
13 ms at a time, which is what a modem is.

Half of that gap is top-k's: removing the truncation takes stage 0 from -0.066
to -0.031 against real. **The other half is the model's own.**

THIS IS THE FIRST IDEA THIS PROJECT CAN TRIAGE FOR FREE. Every previous
candidate cost a night of GPU and a sitting of Ben's ears before anyone knew
whether it did anything. Churn costs two minutes and needs no listener, so a
sampling knob can be swept, scored, and discarded before either is spent.

WHAT IS SWEPT, and why each could move a repeat:

    temperature     flattens or sharpens everything; the blunt instrument, and
                    already measured twice on other axes (0015, and the note in
                    sample.py). Included as the control every other knob has to
                    beat.
    top_k           the truncation 0046 already implicated. Swept rather than
                    just on/off, because 0044's sitting could not resolve
                    200-vs-none and the useful question may be "how much".
    top_p           nucleus: keeps a probability mass rather than a count, so it
                    widens exactly where the model is uncertain and narrows
                    where it is confident. A repeat happens where the model is
                    confident, which is where this cuts hardest.
    min_p           keeps ids above a fraction of the top id's probability. The
                    one knob whose threshold moves WITH the model's confidence,
                    which is the shape of the defect.
    repeat_penalty  divides the logit of the code this stage emitted in the
                    previous frame. The only knob aimed at the defect itself
                    rather than at the distribution's shape.

THE TARGET IS NOT "MAXIMUM CHURN". Real audio is 0.868 and a knob that overshoots
is making the stream jitter, which has its own sound and is not obviously better.
The score is |churn - 0.868|, and overshoot is penalised exactly as much as
stickiness.

WHAT THIS CANNOT DECIDE. Churn is a mechanism, not audibility. 0023 and 0027 both
moved an offline number for a listening difference of zero, and 0044 could not
hear the top-k change this predicts. So the output is a shortlist that has earned
a sitting, never a change to the sampling default.
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

OUT = Path(__file__).resolve().parent
MODEL = HERE / "results" / "model-fair-k8"
SPECIES = "american-crow"
N = 40
MIN_FRAMES = 40
TARGET = 0.868          # real audio's stage-0 churn, measured in 0046


def churn(grids):
    total, seen = np.zeros(8), 0
    for grid in grids:
        if grid.shape[1] < 2:
            continue
        total += (grid[:, 1:] != grid[:, :-1]).mean(axis=1)
        seen += 1
    return total / max(1, seen)


@torch.no_grad()
def sample(sampler, seed, temperature=1.0, top_k=200, top_p=None, min_p=None,
           repeat_penalty=None, max_frames=225):
    """`Sampler.tokens` with the extra knobs, so nothing in src changes yet.

    Deliberately a copy rather than an edit to `sample.py`: this is a sweep to
    find out whether any of these is worth having, and adding five parameters to
    the shipped sampler before that is known would be committing to them.
    """
    vocab = sampler.vocabulary
    torch.manual_seed(seed)
    prefix = sampler._prefix(SPECIES)
    sequence = torch.tensor([prefix], device=sampler.device, dtype=torch.long)
    limit = min(sampler.config.block_size, vocab.prefix_len + max_frames * vocab.n_codebooks)
    cache = sampler.model.empty_cache()
    logits, _ = sampler.model(sequence, cache=cache, offset=0)
    # THE FIRST SAMPLED TOKEN IS THE DURATION BUCKET, NOT A CODEC ID. `_prefix`
    # returns one token (the species) while `prefix_len` says two, because the
    # model picks the duration itself — which is why `Sampler.tokens` slices
    # from `prefix_len` rather than from len(prefix). Keeping it in `codes`
    # shifts every codec token by one position, the grid unflattens to noise,
    # and the churn of every arm comes out at 0.99. The baseline arm is what
    # caught it: it read 0.992 where 0046 measured the identical setup at 0.801.
    codes = []
    emitted = 0
    for _ in range(limit - vocab.prefix_len):
        grown = sequence.size(1)
        step = logits[:, -1, :].float()
        step = step.masked_fill(sampler.legal.forbidden[grown], float("-inf"))

        if repeat_penalty and len(codes) >= vocab.n_codebooks:
            # This stage's code one frame ago. Indexed into `codes`, which holds
            # codec ids only, so the lookback is exactly one frame.
            step[0, codes[len(codes) - vocab.n_codebooks]] /= repeat_penalty

        step = step / max(temperature, 1e-5)
        if top_k:
            kept = min(top_k, int((~torch.isinf(step)).sum().item()))
            if kept > 0:
                cutoff = torch.topk(step, kept, dim=-1).values[:, [-1]]
                step = step.masked_fill(step < cutoff, float("-inf"))
        probs = torch.softmax(step, dim=-1)
        if min_p:
            probs = probs.masked_fill(probs < min_p * probs.max(), 0.0)
        if top_p:
            ordered, index = torch.sort(probs, descending=True, dim=-1)
            cumulative = ordered.cumsum(dim=-1)
            drop = cumulative - ordered > top_p
            ordered = ordered.masked_fill(drop, 0.0)
            probs = torch.zeros_like(probs).scatter(1, index, ordered)
        total = probs.sum()
        if not torch.isfinite(total) or total <= 0:
            break
        nxt = torch.multinomial(probs / total, num_samples=1)
        if int(nxt) == vocab.eos:
            break
        emitted += 1
        if emitted > 1:            # skip the duration bucket
            codes.append(int(nxt))
        sequence = torch.cat([sequence, nxt], dim=1)
        logits, _ = sampler.model(nxt, cache=cache, offset=grown)
    flat = np.array(codes, dtype=np.int64)
    usable = (flat.size // vocab.n_codebooks) * vocab.n_codebooks
    return flat[:usable]


ARMS = [
    ("baseline top_k=200", dict()),
    ("no truncation", dict(top_k=None)),
    ("temperature 1.1", dict(temperature=1.1)),
    ("temperature 1.2", dict(temperature=1.2)),
    ("top_k 500", dict(top_k=500)),
    ("top_k 50", dict(top_k=50)),
    ("top_p 0.95", dict(top_k=None, top_p=0.95)),
    ("top_p 0.99", dict(top_k=None, top_p=0.99)),
    ("min_p 0.02", dict(top_k=None, min_p=0.02)),
    ("min_p 0.05", dict(top_k=None, min_p=0.05)),
    ("repeat 1.05", dict(repeat_penalty=1.05)),
    ("repeat 1.15", dict(repeat_penalty=1.15)),
    ("repeat 1.30", dict(repeat_penalty=1.30)),
    ("repeat 1.15 no-topk", dict(top_k=None, repeat_penalty=1.15)),
]


def main():
    run = Run("0047 — CAN SAMPLING REACH REAL CHURN",
              ["sweep", "report"])
    results = {}
    try:
        from crowgpt.sample import Sampler

        sampler = Sampler(MODEL / "model.pt", token_dir=None)
        with run.stage("sweep") as stage:
            for n, (label, kwargs) in enumerate(ARMS, 1):
                grids, seed, short = [], 0, 0
                while len(grids) < N and seed < N * 5:
                    flat = sample(sampler, seed, **kwargs)
                    seed += 1
                    grid = sampler.codec.unflatten(flat)
                    if grid.shape[1] >= MIN_FRAMES:
                        grids.append(grid)
                    else:
                        short += 1
                value = churn(grids)
                results[label] = {"stage0": round(float(value[0]), 4),
                                  "mean": round(float(value.mean()), 4),
                                  "gap": round(float(value[0] - TARGET), 4),
                                  "clips": len(grids), "fragments": short}
                stage.update(n, len(ARMS), extra=f"{label} {value[0]:.3f}")

        with run.stage("report") as stage:
            ranked = sorted(results.items(), key=lambda kv: abs(kv[1]["gap"]))
            (OUT / "results.json").write_text(json.dumps(
                {"target_stage0": TARGET, "arms": results}, indent=2))
            for label, row in ranked[:3]:
                run.note(f"{label}: stage-0 {row['stage0']:.3f} ({row['gap']:+.3f})")
            stage.say(f"best: {ranked[0][0]}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    for label, row in sorted(results.items(), key=lambda kv: abs(kv[1]["gap"])):
        print(f"{label:>22} stage0 {row['stage0']:.3f}  gap {row['gap']:+.3f}  "
              f"mean {row['mean']:.3f}  frags {row['fragments']}")


if __name__ == "__main__":
    main()
