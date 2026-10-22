"""Which cheap signal measure actually separates a generated caw from a real one?

Ben's verdict on the best model is "more like a cyborg, so still a little
robotic but still a crow". Nothing in this project can measure that. BirdNET
detection is at 96% of its codec ceiling so it has almost no room left to move,
and 0014 disqualified it for quality outright: a 2 kHz lowpass, audibly
destroyed, RETAINED MORE detections (0.733) than a 3 kbps codec round-trip
(0.690) while sitting 3.2x further away spectrally. Fréchet distance still
discriminates but is a single opaque scalar that cannot say WHAT is wrong.

So this tries three interpretable measures and asks which, if any, earn a place.

THE ACCEPTANCE TEST IS WRITTEN BEFORE THE NUMBERS. A measure is useful only if
REAL and CODEC agree while GENERATED differs from both. A measure that separates
real from codec is describing the tokenizer, and 0014 and 0017 already
established the tokenizer is not the lever — 0017's words were "The codec is not
the lever. What remains for audio quality is the model or the objective." A
measure that separates nothing at all gets deleted rather than reported.

THE MEASURES:

  stitch_db   Periodicity in the spectral flux at the codec's own frame rate.
              EnCodec emits one frame per 320 samples, which at 24 kHz is
              exactly 75 Hz. Tokens that do not belong next to each other
              produce a decoder discontinuity locked to that grid, and real
              audio has no reason to prefer any frame phase — so this is the one
              measure here whose null is known by construction rather than
              estimated. Real audio should score ~0 dB with nobody calibrating.

  rise_ms     Median 10%->90% attack time. metrics.py already keeps a 5.3 ms
              analysis scale because onset smearing is the first thing a codec
              loses; a model that hedges its opening tokens gives a mushy attack
              and a mushy attack does not read as a bird.

  jitter      Median frame-to-frame relative change in f0 inside voiced runs,
              with HNR and voiced fraction alongside. A pitch track that steps
              rather than glides is a large part of what "robotic" means.

EVERY ARM IS RAW AUDIO AND NOTHING IS PLACED IN AMBIENCE, WHICH IS THE WHOLE
REASON THIS SCRIPT EXISTS IN THIS SHAPE. The first version of this experiment
scored the clips the listening test plays — a bout dropped into three seconds of
real background — and got a result that looked clean and was not. A generated
clip is codec output only where the bout is, and untouched ambience everywhere
else, while a round-tripped clip is codec output for the full three seconds. So
the codec arm carried several times more codec than the arm it was the control
for, and duly scored 13.4 dB of frame-stitch against generated audio's 7.0. That
is not the tokenizer being worse than the model, it is two arms being different
lengths of codec. Raw bouts, equal treatment, no ambience.

Run:
    cd ../../crowgpt && PYTHONPATH=src .venv/bin/python \
        ../experiments/0020-what-does-cyber-crow-actually-measure/run.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = REPO / "data" / "crowgpt"
TOKENS = DATA / "tokens"
BOUTS = DATA / "bouts"
RESULTS = REPO / "crowgpt" / "results"
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.codec import SAMPLE_RATE, normalise  # noqa: E402
from crowgpt.metrics import bootstrap_ci, paired_difference  # noqa: E402
from crowgpt.timbre import TimbrePanel  # noqa: E402
from crowgpt.tokens import BoutStore, TokenDataset  # noqa: E402


def held_out_bouts(species, wanted, seed=0):
    """Real bouts from groups the model never saw, longest first for stability."""
    store = BoutStore(BOUTS)
    held = {row["group_key"] for row in TokenDataset(TOKENS, "test").records}
    pool = [row for row in store.index
            if row["group_key"] in held and row["species"] in species]
    if not pool:
        raise SystemExit(f"no held-out bouts for {species}")
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(pool), size=min(wanted, len(pool)), replace=False)
    return [normalise(store.audio(pool[i])) for i in picks]


def summarise(columns):
    out = {}
    for name, values in columns.items():
        usable = values[np.isfinite(values)]
        if usable.size < 2:
            out[name] = {"n": int(usable.size)}
            continue
        low, high = bootstrap_ci(usable, statistic=np.median)
        out[name] = {
            "n": int(usable.size),
            "median": round(float(np.median(usable)), 4),
            "ci": [round(low, 4), round(high, 4)],
        }
    return out


def verdict(real, codec, generated, name):
    """The pre-registered rule: real ~ codec, and generated apart from both."""
    if any(name not in arm or "median" not in arm[name] for arm in (real, codec, generated)):
        return "no data"
    tokenizer = abs(real[name]["median"] - codec[name]["median"])
    model = abs(generated[name]["median"] - codec[name]["median"])
    overlaps = not (generated[name]["ci"][0] > codec[name]["ci"][1]
                    or generated[name]["ci"][1] < codec[name]["ci"][0])

    if overlaps:
        return "NO SEPARATION at this n — generated sits inside the codec interval"
    if tokenizer > model:
        return "MEASURES THE TOKENIZER — real-vs-codec exceeds codec-vs-generated"
    return "KEEP — separates generated from both references"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="model-d384-6k")
    parser.add_argument("--species", default="american-crow")
    parser.add_argument("-n", type=int, default=40)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    from crowgpt.sample import Sampler

    species = [s.strip() for s in args.species.split(",")]
    sampler = Sampler(RESULTS / args.model / "model.pt", token_dir=TOKENS, device=args.device)

    print(f"{args.n} bouts per arm · {', '.join(species)} · {args.model}")
    real = held_out_bouts(species, args.n)
    print(f"   {len(real)} held-out real bouts", flush=True)

    through = [np.asarray(sampler.codec.roundtrip(bout)[0][: bout.size], dtype=np.float32)
               for bout in real]
    print("   codec round-trip done", flush=True)

    made = []
    for index in range(args.n):
        audio = sampler.audio(species[index % len(species)], seed=9000 + index)
        if audio.size:
            made.append(np.asarray(audio, dtype=np.float32))
        if (index + 1) % 10 == 0:
            print(f"   generated {index + 1}/{args.n}", flush=True)

    panel = TimbrePanel()
    arms = {
        "A real": panel.across(real, SAMPLE_RATE),
        "B codec": panel.across(through, SAMPLE_RATE),
        "C generated": panel.across(made, SAMPLE_RATE),
    }
    summaries = {name: summarise(columns) for name, columns in arms.items()}

    names = sorted(arms["A real"])
    print(f"\n{'measure':<18} {'A real':>22} {'B codec':>22} {'C generated':>22}")
    for name in names:
        cells = []
        for arm in ("A real", "B codec", "C generated"):
            row = summaries[arm].get(name, {})
            cells.append(f"{row['median']:.3f} [{row['ci'][0]:.2f},{row['ci'][1]:.2f}]"
                         if "median" in row else "—")
        print(f"{name:<18} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22}")

    print("\npaired, each real bout against its own codec round-trip"
          " — the tokenizer alone:")
    paired = {}
    for name in names:
        a, b = arms["A real"].get(name), arms["B codec"].get(name)
        if a is None or b is None or a.shape != b.shape:
            continue
        keep = np.isfinite(a) & np.isfinite(b)
        if keep.sum() < 5:
            continue
        paired[name] = paired_difference(a[keep], b[keep])
        mark = "moves" if paired[name]["significant"] else "steady"
        print(f"   {name:<16} {paired[name]['mean_difference']:+.4f} "
              f"[{paired[name]['ci'][0]:+.4f},{paired[name]['ci'][1]:+.4f}]  {mark}")

    print("\nVERDICTS")
    verdicts = {}
    for name in names:
        verdicts[name] = verdict(summaries["A real"], summaries["B codec"],
                                 summaries["C generated"], name)
        print(f"   {name:<16} {verdicts[name]}")

    (HERE / "results.json").write_text(json.dumps({
        "model": args.model, "species": species,
        "n": {"real": len(real), "codec": len(through), "generated": len(made)},
        "arms": summaries, "codec_paired": paired, "verdicts": verdicts,
    }, indent=2))


if __name__ == "__main__":
    main()
