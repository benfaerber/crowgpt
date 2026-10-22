"""Is the model blurry in the fine residual codebooks, or correctly uncertain?

CrowGPT samples the whole token stream at one temperature, and the history of
that constant is a fight it cannot win. 0.95 was written first. 0015 measured
1.15 and cut training-set overlap from 8.7x the held-out base rate to 1.0x. Then
1.0 beat 1.15 on the better-trained model by 21 points of detection, because at
1.15 bouts come out 29% short and their contour flattens. Every setting was
right about something and wrong about something else.

The suspicion behind this experiment is that the knob is doing two jobs at once.
In a residual codec the first codebook carries the coarse shape — which is
duration, contour, and when the bout stops — while the later stages carry
texture. If the model is well fitted at the coarse end and blurry at the fine
end, then one temperature must either sharpen the texture and wreck the timing,
or fix the timing and leave the texture gritty. Which is exactly the observed
pattern, and "gritty texture" is what a cyborg sounds like.

WHAT WOULD MAKE THIS IDEA DEAD, WRITTEN DOWN BEFORE THE NUMBERS EXIST:

  1. FLAT CALIBRATION. If the temperature minimising held-out loss is the same
     at every stage, a per-stage schedule is a global one in disguise. Stop.

  2. CORRECT UNCERTAINTY, and this is the trap. If a fine stage's cross-entropy
     already equals its own predictive entropy, and both sit at the codec's
     marginal, then the model is not blurry there — the residual is genuinely
     unpredictable given the context, and the model is right to hedge. Cooling a
     correctly-uncertain distribution does not clean it up. It makes the sampler
     re-pick the same arbitrary residual code over and over, which is periodic,
     and periodic is precisely what "robotic" sounds like. This outcome would
     make the output WORSE, and it will feel like confirmation when it arrives,
     because it shows up as high fine-stage entropy.

The null is not invented here. 0014 measured the codec's own per-stage marginal
entropy on gated windows at [6.30, 7.06, 7.34, 7.50, 7.63, 7.73, 7.80, 7.84]
bits of a possible 10. No stage is noise, and the whole spread is 1.5 bits, so a
model whose spread is far wider is failing on its own account.

Two more answers ride along in the same forward pass, both free:

  - PER-SPECIES held-out loss, which settles the `--balance` question without
    training anything. American Crow is 70.6% of the corpus and already at 99%
    of its codec ceiling; if it also has the lowest loss, then rebalancing can
    only move loss off the species being listened to and onto ones that are not.

  - WHERE EOS RANKS at a frame boundary. Sampling keeps the top 200 ids. If EOS
    routinely falls below that, top-k is deleting the chance to stop, and the
    bout-length behaviour blamed on temperature since 0015 is a top-k artefact
    instead. Nobody has ever looked.

CPU by default. This is inference over a few hundred sequences and it must not
be able to OOM a training run sharing the card.

Run:
    cd ../../crowgpt && PYTHONPATH=src .venv/bin/python \
        ../experiments/0019-is-the-model-blurry-in-the-fine-codebooks/run.py
"""

import argparse
import json
import sys
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = REPO / "data" / "crowgpt"
TOKENS = DATA / "tokens"
RESULTS = REPO / "crowgpt" / "results"
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.model import Config, CrowGPT  # noqa: E402
from crowgpt.stages import StageProfile  # noqa: E402
from crowgpt.tokens import TokenDataset, Vocabulary  # noqa: E402


def vocabulary_for(manifest):
    """Tolerate the call-type prefix landing in the vocabulary mid-flight."""
    try:
        return Vocabulary(manifest["n_codebooks"], manifest["species"],
                          manifest.get("call_types", ()))
    except TypeError:
        return Vocabulary(manifest["n_codebooks"], manifest["species"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="model-d384-6k")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batches", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()

    blob = torch.load(RESULTS / args.model / "model.pt", map_location="cpu",
                      weights_only=False)
    config = Config(**blob["config"])
    model = CrowGPT(config)
    model.load_state_dict(blob["model"])
    vocabulary = vocabulary_for(blob["manifest"])

    print(f"{args.model} · {model.n_params()/1e6:.1f}M params · "
          f"{vocabulary.n_codebooks} codebooks · val loss {blob.get('val_loss')}")
    print(f"scoring {args.batches * args.batch_size} held-out sequences on {args.device}\n")

    profile = StageProfile(
        model, vocabulary, TokenDataset(TOKENS, "val"),
        device=args.device, batch_size=args.batch_size, batches=args.batches,
        block_size=config.block_size,
    )
    report = profile.measure()

    print(f"{'stage':>5} {'cross-ent':>10} {'predictive':>11} {'codec':>7} "
          f"{'recovered':>10} {'overconf':>9} {'calib T':>8}")
    for row in report["stages"]:
        print(f"{row['stage']:>5} {row['cross_entropy_bits']:>10.3f} "
              f"{row['predictive_entropy_bits']:>11.3f} {row['marginal_bits']:>7.2f} "
              f"{row['bits_recovered']:>10.3f} {row['overconfidence']:>9.3f} "
              f"{row['calibration_t']:>8.2f}")

    if report["prefix"]:
        print(f"\nprefix and EOS: {report['prefix']['cross_entropy_bits']:.3f} bits, "
              f"calibration T {report['prefix']['calibration_t']:.2f}")

    print("\nheld-out loss by species (bits/token):")
    for slug, bits in sorted(report["species"].items(), key=lambda kv: kv[1]):
        print(f"   {slug:<20} {bits:.3f}")

    if report["eos"]:
        print("\nwhere EOS ranks among legal ids at a frame boundary:")
        for where, row in report["eos"].items():
            label = ("the boundary the bout really ends on" if where == "ending"
                     else "boundaries mid-bout, where it should rank low")
            print(f"   {label:<44} median {row['median_rank']:>5.0f}  "
                  f"inside top-200 {row['inside_top_200']:>6.1%}  (n={row['n']})")

    print(f"\nVERDICT: {report['verdict']}")

    (HERE / "results.json").write_text(json.dumps(
        {"model": args.model, "device": args.device,
         "sequences": args.batches * args.batch_size, **report},
        indent=2,
    ))


if __name__ == "__main__":
    main()
