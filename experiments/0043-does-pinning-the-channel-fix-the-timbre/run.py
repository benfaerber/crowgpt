"""Does pinning the channel fix the timbre?

0042 measured two defects in generated audio, both resolved against a
codec-carrying control: it moves through timbre 17% faster frame to frame than
real audio does, and it carries 23% less timbral variety across clips. And it
measured the scale — in this corpus the microphone moves timbre 6.2x further
than everything inside one microphone does, bird and call type included.

The corpus is 41.7 hours over 12,846 recordings, about 11.7 seconds per acoustic
channel, and `tokens.Vocabulary` conditions on species, call type and duration.
There is no token for the channel. So the hypothesis is that the model has to
average over ~12,800 unlabelled microphones every time it samples, and that the
two defects are what that averaging sounds like: a smeared mean voice belonging
to no particular recording, and a per-frame conditional too broad to hold still.

    ARM D TESTS IT WITHOUT TRAINING ANYTHING. A causal model conditions on
    whatever is in its context whether or not there is a token for it, so
    handing it a real bout's opening second of codec tokens pins the channel by
    example. If the hypothesis is right, the continuation should hold a voice.

BUT THERE IS A SECOND EXPLANATION AND IT MUST BE SEPARATED HERE. Two independent
code audits both landed on `top_k=200` as the largest sampler-side deviation
from the trained distribution, and — this is the part nobody had noticed — it is
not a uniform truncation. Measured per stage on `model-fair-k8`, top-200 of 1024
retains 0.981 of the mass at stage 0 and 0.782 at stage 7. It is a no-op on the
coarse structure and throws away a fifth of the fine residual, renormalising onto
whichever 200 codes the model happens to rank highest.

Structurally that is the same operation as cooling the fine stages, which
`stages.py` pre-registered as the thing that would "make the sampler re-pick the
same arbitrary residual code over and over, which is periodic, and periodic is
what 'robotic' sounds like". 0019 closed per-stage TEMPERATURE on calibration
grounds and checked top-k only against EOS; it never checked top-k against mass.
0015 swept top-k as a global on/off knob at five temperatures, and at T=1.0 —
the shipped setting — turning it off was NOT worse. So this has never been ruled
out, and it predicts the same frame-to-frame defect the channel story does.

Arm C' is that control, and it costs one extra generation pass:

    A  real          held-out bouts, raw
    B  real via codec                        the ceiling, and the check that the
                                             instrument is not reading the codec
    C  unprompted, top_k=200                 the incumbent
    C' unprompted, top_k=None                the truncation confound
    D  prompted continuation, top_k=200      the channel pinned by example

Read it as a 2x2 with one cell missing. If only C' moves, the defect is the
sampler and it is free to fix. If only D moves, it is the missing conditioning
and the fix is a channel token. If both move, they are separate and additive. If
neither moves, both hypotheses are wrong and 0042's defects come from somewhere
else — which is a real answer and the one worth writing down loudest.

HELD-OUT MEANS THE RECORDING, NOT THE BOUT. Bouts from one recording are near
duplicates, so the prompts are drawn from the test split's recordings and no
recording contributes more than one bout. A prompt from a recording the model
trained on would be measuring memorisation, not conditioning.
"""

import collections
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "crowgpt" / "src"))

CHECKPOINT = ROOT / "crowgpt" / "results" / "model-fair-k8" / "model.pt"
TOKEN_DIR = ROOT / "data" / "crowgpt" / "tokens"
BOUTS = ROOT / "data" / "crowgpt" / "bouts"
PER_SPECIES = 12
PROMPT_SECONDS = 1.0
MIN_SOURCE_SECONDS = 2.0
SR = 24000


def _instrument():
    """0042's measurement, imported rather than reimplemented.

    Two copies of an instrument drift, and the whole point of this experiment is
    that its numbers are comparable with 0042's.
    """
    path = ROOT / "experiments" / "0042-does-the-generator-hold-one-voice" / "run.py"
    spec = importlib.util.spec_from_file_location("m0042", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def held_out_recordings():
    """Recording ids in the generator's test split."""
    out = collections.defaultdict(set)
    with open(TOKEN_DIR / "test.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            out[row["species"]].add(row["recording_id"])
    return out


def sources(rng):
    """One held-out bout per recording, PER_SPECIES of each species."""
    held = held_out_recordings()
    by_species = collections.defaultdict(list)
    with open(BOUTS / "index.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            if row["recording_id"] in held.get(row["species"], ()) \
                    and row["dur_sec"] >= MIN_SOURCE_SECONDS:
                by_species[row["species"]].append(row)

    chosen = []
    for species, rows in sorted(by_species.items()):
        seen, pool = set(), []
        for i in rng.permutation(len(rows)):
            row = rows[i]
            if row["recording_id"] in seen:
                continue
            seen.add(row["recording_id"])
            pool.append(row)
            if len(pool) == PER_SPECIES:
                break
        chosen.extend(pool)
    return chosen


def audio_of(row, shards):
    shard = shards[row["species"]]
    start = row["sample_offset"]
    return shard[start:start + row["n_samples"]].astype(np.float64) / 32768.0


def main():
    from crowgpt import gpu

    gpu.claim()
    import torch

    from crowgpt.codec import FRAME_RATE
    from crowgpt.progress import Run
    from crowgpt.sample import Sampler

    m = _instrument()
    rng = np.random.default_rng(0)
    run = Run("0043 — DOES PINNING THE CHANNEL FIX THE TIMBRE",
              ["choose", "real", "generate", "measure"])

    with run.stage("choose") as stage:
        rows = sources(rng)
        shards = {s: np.memmap(BOUTS / f"{s}.i16", dtype=np.int16, mode="r")
                  for s in {r["species"] for r in rows}}
        stage.say(f"{len(rows)} held-out bouts, one per recording, "
                   f"{len(set(r['recording_id'] for r in rows))} recordings")

    sampler = Sampler(str(CHECKPOINT), token_dir=str(TOKEN_DIR))
    width = sampler.vocabulary.n_codebooks
    prompt_frames = int(FRAME_RATE * PROMPT_SECONDS)

    vectors = collections.defaultdict(list)
    prompts = []

    with run.stage("real") as stage:
        stage.update(0, len(rows))
        for i, row in enumerate(rows):
            y = audio_of(row, shards)
            codes = np.asarray(sampler.codec.encode(y.astype(np.float32)))[0]
            if codes.shape[1] <= prompt_frames + 8:
                continue
            back = sampler.codec.decode(torch.from_numpy(codes))[0].astype(np.float64)
            for arm, clip in (("A_real", y), ("B_codec", back)):
                v = m.timbre(clip)
                if v is not None:
                    vectors[arm].append(v)
            prompts.append((row, codes))
            stage.update(i + 1, len(rows))
        stage.say(f"{len(prompts)} usable sources")

    arms = [("C_topk200", dict(top_k=200)),
            ("C_notopk", dict(top_k=None)),
            ("D_prompted", dict(top_k=200))]

    with run.stage("generate") as stage:
        total = len(prompts) * len(arms)
        stage.update(0, total)
        step = 0
        for name, kwargs in arms:
            for seed, (row, codes) in enumerate(prompts):
                if name == "D_prompted":
                    flat = sampler.continue_from(
                        row["species"], codes[:, :prompt_frames], seed=seed,
                        seconds=row["dur_sec"], **kwargs)
                else:
                    flat = sampler.tokens(row["species"], seed=seed, **kwargs)
                step += 1
                stage.update(step, total, extra=name)
                if flat.size < width * 8:
                    continue
                clip = sampler.codec.decode(
                    torch.from_numpy(sampler.codec.unflatten(flat)))[0].astype(np.float64)
                v = m.timbre(clip)
                if v is not None:
                    vectors[name].append(v)
        stage.say(f"{sum(len(vectors[a]) for a, _ in arms)} gradeable clips")

    with run.stage("measure") as stage:
        order = ["A_real", "B_codec", "C_topk200", "C_notopk", "D_prompted"]
        stats, centroids = {}, {}
        for arm in order:
            jump, within = m.per_clip(vectors[arm])
            centroids[arm] = np.vstack([m.unit(v.mean(0)) for v in vectors[arm]])
            stats[arm] = {"n": len(vectors[arm]),
                          "frame_to_frame": float(jump.mean()),
                          "within_clip": float(within.mean()),
                          "between_clip": m.spread(centroids[arm]),
                          "_jump": jump, "_within": within}
            s = stats[arm]
            print(f"{arm:14s} n={s['n']:3d}  frame-to-frame {s['frame_to_frame']:.4f}  "
                  f"within-clip {s['within_clip']:.4f}  "
                  f"between-clip {s['between_clip']:.4f}")

        # Every generated arm is judged against B, never against raw: 0024 showed
        # the round-trip is itself audibly scratchy, so a difference from A could
        # always be the tokenizer.
        pairs = [("B_codec", "A_real"), ("C_topk200", "B_codec"),
                 ("C_notopk", "B_codec"), ("D_prompted", "B_codec"),
                 ("C_notopk", "C_topk200"), ("D_prompted", "C_topk200")]
        comparisons = {}
        print()
        for a, b in pairs:
            row = {}
            for key, label in (("_jump", "frame_to_frame"), ("_within", "within_clip")):
                lo, hi = m.boot_mean_diff(stats[a][key], stats[b][key], rng)
                row[label] = {"diff": float(stats[a][key].mean() - stats[b][key].mean()),
                              "ci": [float(lo), float(hi)],
                              "resolved": bool(lo > 0 or hi < 0)}
            lo, hi = m.boot_spread_diff(centroids[a], centroids[b], rng)
            row["between_clip"] = {
                "diff": stats[a]["between_clip"] - stats[b]["between_clip"],
                "ci": [float(lo), float(hi)], "resolved": bool(lo > 0 or hi < 0)}
            comparisons[f"{a} - {b}"] = row
            for label, r in row.items():
                mark = "RESOLVED" if r["resolved"] else ""
                print(f"{a:12s} - {b:12s} {label:15s} {r['diff']:+.4f} "
                      f"95% CI [{r['ci'][0]:+.4f}, {r['ci'][1]:+.4f}] {mark}")

        (HERE / "results.json").write_text(json.dumps({
            "checkpoint": str(CHECKPOINT.relative_to(ROOT)),
            "prompt_seconds": PROMPT_SECONDS,
            "sources": len(prompts),
            "arms": {a: {k: v for k, v in s.items() if not k.startswith("_")}
                     for a, s in stats.items()},
            "comparisons": comparisons,
        }, indent=2))
        stage.say("wrote results.json")

    for arm in ("C_topk200", "C_notopk", "D_prompted"):
        c = comparisons[f"{arm} - B_codec"]
        run.note(f"{arm}: frame-to-frame {c['frame_to_frame']['diff']:+.4f}"
                 f"{' RESOLVED' if c['frame_to_frame']['resolved'] else ''} · "
                 f"between-clip {c['between_clip']['diff']:+.4f}"
                 f"{' RESOLVED' if c['between_clip']['resolved'] else ''}")


if __name__ == "__main__":
    main()
