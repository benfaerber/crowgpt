"""Which generated calls are good enough to publish?

Ben, for the promo site: he wants crowgpt's own output, not his field recordings
(0054 answered that question and answered the wrong one).

TWO CONSTRAINTS, AND ONLY ONE OF THEM IS SOLVED HERE.

**Blinding.** 0053 is mid-flight: 50 of 120 trials graded, results withheld until
120, and the arms are three channel buckets of `model-channel256`. Curating "the
best generated clips" out of that model and playing them to Ben would leak arm
quality into a running experiment. So this generates from **`model-mono-v2`**,
which is not in the pool, and records no arm or bucket in any filename. 0050 put
mono-v2 and fair-k8 at a dead heat (P = 0.51), so nothing is lost by picking the
one that is not being measured.

That reduces the risk; it does not remove it. Hearing a curated best-of shifts an
absolute bar, and 0038 measured 8.3 points of drift from far less. The pool's
per-trial real anchor is what protects it — every 0053 trial carries its own
reference, so a criterion that moves affects both arms of a comparison equally.
**Ben's call whether to listen now or after trial 120.** The clips sit on disk
either way.

**Licensing, which this cannot solve.** The model is trained on archive
recordings, some of them CC BY-NC-**ND**, and `crowgpt/README.md` already forbids
publishing the derived shards. Generated audio is a different thing from a shard
and the repo has real evidence for that — 0015 swept the sampling temperature and
found n-gram overlap with the training set at **0.0x the held-out base rate at
T = 1.0**, the setting used here, so these clips are not reproducing anybody's
recording. Whether a model's output is a derivative work of ND material is
unsettled, and this file is not the place that gets decided. Flagged, not
answered. Attribution on the page is cheap and worth it regardless.

HOW THE BEST ARE CHOSEN. Two instruments, neither trusted alone:

    birdnet     max corvid confidence. Circular as evidence that the generator is
                good — 0022 found generated output scores ABOVE real audio on it —
                but that is not the question here. The question is which of 300
                clips is most crow-like, and a bird classifier's confidence is a
                fair ranking for that even when its absolute level is inflated.
    churn       stage-0 codebook churn against real audio's 0.868 (0046). The
                defect Ben calls "modem" is a stuck coarse codebook, so a clip far
                from the target on this is one carrying the artefact.

Clips must clear 1.5 s, which is BirdNET's own floor: `birdnetlib` breaks out of
its chunking loop below that and returns zero detections with no error, so a
shorter clip reads as rejection when nothing was analysed. That is stricter than
`MIN_GRADEABLE_SECONDS` and it is the binding one.

NOTHING HERE DECIDES. Ben picks by ear. Every automated instrument in this project
has ordered arms correctly and located nothing.
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

OUT = Path(__file__).resolve().parent
CLIPS = OUT / "candidates"
SHORT_DIR = OUT / "shortlist"

#: Not `model-channel256`, which 0053 is measuring. See the docstring.
MODEL = HERE / "results" / "model-mono-v2"
SPECIES = "american-crow"
SR = 24000

#: Draw a lot and keep a few. Generation is cheap and Ben's ear is not.
DRAWS = 300

#: BirdNET's floor, not the page's. Below this nothing is analysed at all.
MIN_SECONDS = 1.5

#: Real audio's stage-0 churn (0046).
TARGET_CHURN = 0.868

#: How many go in front of Ben.
SHORTLIST = 10

#: A clip whose churn is further than this from real is carrying the modem
#: artefact, however confident BirdNET is about it.
MAX_CHURN_GAP = 0.12

#: Clearing BOTH instruments at once. Rare — 3 of 203 — and the first version's
#: duration-spread rule pushed two of the three out of the shortlist, which is
#: exactly backwards. These get seated first now.
BOTH_BIRDNET, BOTH_GAP = 0.99, 0.02


def churn_stage0(grid):
    """Fraction of adjacent frames whose coarse code changes."""
    if grid.shape[1] < 2:
        return 0.0
    return float((grid[0, 1:] != grid[0, :-1]).mean())


def main():
    from crowgpt.gpu import claim

    claim()

    import torch

    from crowgpt.progress import Run
    from crowgpt.sample import Sampler

    CLIPS.mkdir(parents=True, exist_ok=True)
    SHORT_DIR.mkdir(parents=True, exist_ok=True)

    run = Run("0055 — BEST GENERATED CALLS", ["generate", "birdnet", "pick"])
    made = []
    try:
        with run.stage("generate") as stage:
            sampler = Sampler(MODEL / "model.pt", token_dir=None)
            short = 0
            for seed in range(DRAWS):
                flat = sampler.tokens(SPECIES, seed=seed)
                grid = sampler.codec.unflatten(flat)
                audio = sampler.codec.decode(torch.from_numpy(grid))[0]
                audio = np.asarray(audio, dtype=np.float32)
                seconds = audio.size / SR
                if seconds < MIN_SECONDS:
                    short += 1
                else:
                    made.append({"seed": seed, "seconds": round(seconds, 2),
                                 "churn": round(churn_stage0(grid), 4),
                                 "audio": audio})
                stage.update(seed + 1, DRAWS, extra=f"{len(made)} kept")
            del sampler
            torch.cuda.empty_cache()
            run.note(f"{len(made)} clips over {MIN_SECONDS}s, {short} too short")

        with run.stage("birdnet") as stage:
            stage.update(0, 1)
            from crowgpt.birdnet import BirdNet

            birdnet = BirdNet(sample_rate=SR)
            values, crow_min = birdnet.confidence([m["audio"] for m in made])
            for row, value in zip(made, values):
                row["birdnet"] = None if value is None else round(float(value), 4)
            scored = [m for m in made if m["birdnet"] is not None]
            run.note(f"{len(scored)} of {len(made)} scored, crow floor {crow_min}")
            stage.say(f"{len(scored)} scored")

        with run.stage("pick") as stage:
            stage.update(0, 1)
            for row in made:
                row["churn_gap"] = round(abs(row["churn"] - TARGET_CHURN), 4)

            # BirdNET ranks, churn vetoes. Confidence says "most crow-like" and
            # churn says "not carrying the stuck-codebook artefact"; a clip needs
            # both, and neither is trusted to do the other's job.
            eligible = [r for r in made
                        if r["birdnet"] is not None
                        and r["churn_gap"] <= MAX_CHURN_GAP]
            eligible.sort(key=lambda r: -r["birdnet"])

            # Clips clearing both instruments go in first and unconditionally.
            both = sorted((r for r in eligible
                           if r["birdnet"] >= BOTH_BIRDNET
                           and r["churn_gap"] <= BOTH_GAP),
                          key=lambda r: r["churn_gap"])
            picked = list(both[:SHORTLIST])
            for row in picked:
                row["clears_both"] = True

            # Then spread durations across the rest. The model caps at the 3.0 s
            # bout length, so the range available is 1.5-3.0 and bins are 0.5 s;
            # this is a spread, not a guarantee of ten distinct shapes.
            buckets = {round(r["seconds"] * 2) / 2 for r in picked}
            for row in eligible:
                if len(picked) >= SHORTLIST:
                    break
                bucket = round(row["seconds"] * 2) / 2
                if bucket in buckets or row in picked:
                    continue
                buckets.add(bucket)
                picked.append(row)
            for row in eligible:                       # top up by confidence
                if len(picked) >= SHORTLIST:
                    break
                if row not in picked:
                    picked.append(row)

            import soundfile as sf

            def write(folder, name, audio):
                peak = float(np.max(np.abs(audio))) or 1.0
                sf.write(folder / name, np.clip(audio / peak * 0.95, -1, 1), SR,
                         format="WAV", subtype="PCM_16")

            for row in made:
                write(CLIPS, f"seed{row['seed']:03d}.wav", row["audio"])
            for rank, row in enumerate(picked, 1):
                mark = "both" if row.get("clears_both") else "birdnet"
                row["file"] = f"{rank}-crowgpt-{mark}-{row['seconds']:.1f}s.wav"
                row["rank"] = rank
                write(SHORT_DIR, row["file"], row["audio"])

            for row in made:
                row.pop("audio", None)
            (OUT / "candidates.json").write_text(json.dumps({
                "model": MODEL.name, "species": SPECIES, "draws": DRAWS,
                "min_seconds": MIN_SECONDS, "target_churn": TARGET_CHURN,
                "max_churn_gap": MAX_CHURN_GAP,
                "why_not_channel256": ("0053 is measuring that model blinded; "
                                       "curating its output would leak arm quality"),
                "shortlist": [r["file"] for r in picked],
                "candidates": made}, indent=2))
            stage.say(f"{len(picked)} shortlisted of {len(eligible)} eligible")
    except Exception as error:
        run.note(f"FAILED: {type(error).__name__}: {error}")
        raise

    print(f"\n{len(made)} clips over {MIN_SECONDS}s from {DRAWS} draws")
    print(f"eligible after the churn veto: "
          f"{sum(1 for r in made if r.get('churn_gap', 9) <= MAX_CHURN_GAP)}")
    print(f"\n{'#':>3}{'secs':>6}{'birdnet':>9}{'churn':>7}{'gap':>7}{'both':>6}  file")
    for row in picked:
        print(f"{row['rank']:>3}{row['seconds']:>6.1f}{row['birdnet']:>9.3f}"
              f"{row['churn']:>7.3f}{row['churn_gap']:>+7.3f}"
              f"{'YES' if row.get('clears_both') else '':>6}  {row['file']}")
    print(f"\nshortlist -> {SHORT_DIR}\nall candidates -> {CLIPS}")


if __name__ == "__main__":
    main()
