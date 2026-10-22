"""Stage-0 churn for the flow model, with a reference measured rather than borrowed.

TWO WAYS TO GET THIS WRONG, AND BOTH GIVE A CLEAN-LOOKING NUMBER.

**0.868 IS AN ENCODEC CONSTANT.** 0046 measured real audio's stage-0 churn at
0.868 using EnCodec at 8 codebooks, and every experiment since (0047, 0048, 0049,
0051, 0053) has scored against it — correctly, because they all use the same
tokenizer. This model emits DAC latents. Quantising those gives DAC indices,
whose churn has no reason to equal an EnCodec number and which nobody has
measured. So the real-audio reference is measured here, on DAC, from the same
held-out audio, and 0.868 is not used anywhere in this file.

**THE INDICES MUST BE EXTRACTED THE SAME WAY ON BOTH SIDES.** For real audio the
obvious route is `model.encode`, whose codes follow the quantized residual chain:
each stage sees a residual that earlier codebook errors have already shifted. The
flow model has no such chain — it emits a continuous latent directly, and the
only way to read indices off it is to quantise each stage's slice independently.
Comparing chain-derived indices against slice-derived ones would be comparing two
procedures, not two models, and the difference would look exactly like a result.
Both sides here go through `slice_indices`.

CHURN IS TRIAGE AND NOTHING MORE. 0049 put it at 1-for-2 against the ear and
demoted it; 0047 states plainly that it is a mechanism, not audibility, and must
never move a default. It can say a run is broken before an ear-hour is spent on
it. It cannot say a run is good.
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
from crowgpt.continuous import ContinuousCodec
from crowgpt.flow_sample import FlowSampler
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
LATENTS = DATA / "latents"
# `python judge.py <model-dir>` so two checkpoints can be scored by one rig.
MODEL = (Path(sys.argv[1]) if len(sys.argv) > 1
         else HERE / "results" / "model-flow")
SPECIES = "american-crow"
N = 60
MIN_FRAMES = 40


def slice_indices(codec, latent):
    """[B, dim, frames] continuous -> [B, stages, frames] codebook indices.

    Each stage's 8-d slice is snapped to its own codebook independently. This is
    what `from_latents` does internally, and it is the only index extraction that
    is defined for a latent nothing quantised on the way in.
    """
    codes = []
    for i, quantizer in enumerate(codec.quantizers):
        _, indices = quantizer.decode_latents(latent[:, i * 8 : (i + 1) * 8, :])
        codes.append(indices)
    return torch.stack(codes, dim=1).cpu().numpy()


def churn(grids, n_stages):
    """Per stage, the fraction of adjacent frames whose code differs.

    1.0 means every frame picks a new entry; 0.0 means the code is held for the
    whole bout. Real audio is the only meaningful reference — there is no correct
    value in the abstract.
    """
    total, seen = np.zeros(n_stages), 0
    for grid in grids:
        if grid.shape[1] < 2:
            continue
        total += (grid[:, 1:] != grid[:, :-1]).mean(axis=1)
        seen += 1
    return total / max(1, seen)


def real_grids(codec, stage):
    store = BoutStore(DATA / "bouts")
    held = [i for i in store.split(seed=0)["test"]
            if store.index[i]["species"] == SPECIES]
    seen, grids = set(), []
    for i in held:
        row = store.index[i]
        if row["recording_id"] in seen:
            continue
        if codec.frames(row["n_samples"]) < MIN_FRAMES:
            continue
        seen.add(row["recording_id"])
        grids.append(slice_indices(codec, codec.encode(normalise(store.audio(row))))[0])
        stage.update(len(grids), N)
        if len(grids) >= N:
            break
    return grids


def generated_grids(codec, stage, steps=32, seed=0):
    """The model's own latents, quantised — never re-encoded from its audio.

    Decoding to audio and encoding back would put DAC's decoder and encoder in
    series between the model and the measurement, and both are lossy in ways that
    move exactly this statistic.
    """
    sampler = FlowSampler(MODEL, LATENTS, n_stages=codec.n_stages)
    rng = np.random.default_rng(seed)
    generator = torch.Generator(device=sampler.device).manual_seed(seed)
    grids = []
    for frames in sampler.lengths.draw(N, rng):
        if frames < MIN_FRAMES:
            continue
        latent = sampler.flow.sample(int(frames), count=1, steps=steps,
                                     device=sampler.device, generator=generator)
        latent = (latent * sampler.std + sampler.mean).transpose(1, 2)
        grids.append(slice_indices(codec, latent)[0])
        stage.update(len(grids), N)
    return grids


def main():
    run = Run("0054 — CHURN TRIAGE", ["real", "generated", "report"])
    try:
        codec = ContinuousCodec(n_stages=32)
        with run.stage("real") as stage:
            real = churn(real_grids(codec, stage), codec.n_stages)
            stage.say(f"real stage-0 {real[0]:.4f}")
        with run.stage("generated") as stage:
            made = churn(generated_grids(codec, stage), codec.n_stages)
            stage.say(f"generated stage-0 {made[0]:.4f}")

        with run.stage("report") as stage:
            gap = made[0] - real[0]
            print(f"\n{'stage':>6s} {'real':>8s} {'generated':>10s} {'gap':>8s}")
            for i in range(min(8, codec.n_stages)):
                print(f"{i:6d} {real[i]:8.4f} {made[i]:10.4f} {made[i]-real[i]:+8.4f}")
            print(f"\nstage-0 gap {gap:+.4f}   (0046's EnCodec incumbent was -0.066; "
                  f"NOT comparable, different codec)")
            payload = {"codec": codec.kind, "n": N,
                       "real": real.tolist(), "generated": made.tolist(),
                       "stage0_real": float(real[0]), "stage0_generated": float(made[0]),
                       "stage0_gap": float(gap),
                       "note": "triage only (0049: 1-for-2 against the ear). The DAC "
                               "reference is measured here; 0.868 is an EnCodec number."}
            (OUT / "churn.json").write_text(json.dumps(payload, indent=2) + "\n")
            stage.say(f"gap {gap:+.4f}")
        run.note(f"stage-0 real {real[0]:.4f} generated {made[0]:.4f} gap {gap:+.4f}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
