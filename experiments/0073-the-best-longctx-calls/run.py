"""0073: 0055's audition, re-run for the standing best generator.

model-longctx at T1.1/k200 (the post-dust-sitting default) through the
finetuned decoder. BirdNET ranks; churn and the dust probe veto; units
spread the shortlist across bout shapes. Nothing here decides — the
shortlist goes to the gallery and Ben's ear picks for the site.
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"))

OUT = Path(__file__).resolve().parent
CLIPS = OUT / "candidates"
SHORT_DIR = OUT / "shortlist"

MODEL = HERE / "results" / "model-longctx"
SPECIES = "american-crow"
SR = 24000
TEMPERATURE, TOP_K, MAX_FRAMES = 1.1, 200, 460
SEED_START = 30000

DRAWS = 300
#: BirdNET's floor, not the page's — below this nothing is analysed at all.
MIN_SECONDS = 1.5
TARGET_CHURN = 0.868
MAX_CHURN_GAP = 0.12
SHORTLIST = 12
BOTH_BIRDNET, BOTH_GAP = 0.99, 0.02


def churn_stage0(grid):
    if grid.shape[1] < 2:
        return 0.0
    return float((grid[0, 1:] != grid[0, :-1]).mean())


def main():
    from crowgpt.gpu import claim

    claim()

    import torch

    from lib.dustprobe import DUST_THRESHOLD, clip_features
    from crowgpt.codec import normalise
    from crowgpt.progress import Run
    from crowgpt.sample import Sampler
    from crowgpt.segment import Segmenter

    CLIPS.mkdir(parents=True, exist_ok=True)
    SHORT_DIR.mkdir(parents=True, exist_ok=True)

    run = Run("0073 — BEST LONGCTX CALLS", ["generate", "birdnet", "pick"])
    seg, made = Segmenter(), []
    try:
        with run.stage("generate") as stage:
            sampler = Sampler(MODEL / "model.pt", token_dir=None,
                              decoder_state="finetuned")
            short = 0
            for n in range(DRAWS):
                seed = SEED_START + n
                flat = sampler.tokens(SPECIES, seed=seed,
                                      temperature=TEMPERATURE, top_k=TOP_K,
                                      max_frames=MAX_FRAMES)
                grid = sampler.codec.unflatten(flat)
                audio = np.asarray(sampler.codec.decode(
                    torch.from_numpy(grid))[0], dtype=np.float32)
                seconds = audio.size / SR
                if seconds < MIN_SECONDS:
                    short += 1
                else:
                    features = clip_features(seg, normalise(audio), SR) or {}
                    made.append({
                        "seed": seed, "seconds": round(seconds, 2),
                        "churn": round(churn_stage0(grid), 4),
                        "pitch_strength": round(
                            features.get("pitch_strength", 0.0), 4),
                        "units": features.get("n_bursts", 0),
                        "audio": audio,
                    })
                stage.update(n + 1, DRAWS, extra=f"{len(made)} kept")
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
            run.note(f"{sum(1 for m in made if m['birdnet'] is not None)} "
                     f"scored, crow floor {crow_min}")
            stage.update(1, 1)

        with run.stage("pick") as stage:
            stage.update(0, 1)
            for row in made:
                row["churn_gap"] = round(abs(row["churn"] - TARGET_CHURN), 4)
                row["dusty"] = row["pitch_strength"] <= DUST_THRESHOLD

            # BirdNET ranks; churn and the dust probe veto. Each instrument
            # does one job: confidence says "most crow-like", churn says "no
            # stuck codebook", pitch strength says "a voice, not a bellows".
            eligible = [r for r in made
                        if r["birdnet"] is not None
                        and r["churn_gap"] <= MAX_CHURN_GAP
                        and not r["dusty"]]
            eligible.sort(key=lambda r: -r["birdnet"])
            run.note(f"{len(eligible)} eligible after vetoes "
                     f"({sum(1 for r in made if r['dusty'])} dusty vetoed)")

            both = sorted((r for r in eligible
                           if r["birdnet"] >= BOTH_BIRDNET
                           and r["churn_gap"] <= BOTH_GAP),
                          key=lambda r: r["churn_gap"])
            picked = list(both[:SHORTLIST])
            for row in picked:
                row["clears_both"] = True

            # Spread across bout shapes rather than durations: the 6 s window
            # makes units the axis a visitor would notice, and a shortlist of
            # twelve one-caw blips would misrepresent what the model learned.
            unit_bins = {r["units"] for r in picked}
            for row in eligible:
                if len(picked) >= SHORTLIST:
                    break
                if row in picked or row["units"] in unit_bins:
                    continue
                unit_bins.add(row["units"])
                picked.append(row)
            for row in eligible:
                if len(picked) >= SHORTLIST:
                    break
                if row not in picked:
                    picked.append(row)

            import soundfile as sf

            def write(folder, name, audio):
                peak = float(np.max(np.abs(audio))) or 1.0
                sf.write(folder / name, np.clip(audio / peak * 0.95, -1, 1),
                         SR, format="WAV", subtype="PCM_16")

            for row in made:
                write(CLIPS, f"seed{row['seed']:05d}.wav", row["audio"])
            for rank, row in enumerate(picked, 1):
                mark = "both" if row.get("clears_both") else "birdnet"
                row["file"] = f"{rank}-crowgpt-{mark}-{row['seconds']:.1f}s.wav"
                row["rank"] = rank
                write(SHORT_DIR, row["file"], row["audio"])

            for row in made:
                row.pop("audio", None)
            (OUT / "candidates.json").write_text(json.dumps({
                "model": MODEL.name, "species": SPECIES, "draws": DRAWS,
                "sampling": {"temperature": TEMPERATURE, "top_k": TOP_K,
                             "max_frames": MAX_FRAMES,
                             "decoder": "finetuned (0063)"},
                "min_seconds": MIN_SECONDS, "target_churn": TARGET_CHURN,
                "max_churn_gap": MAX_CHURN_GAP,
                "dust_threshold": DUST_THRESHOLD,
                "shortlist": [r["file"] for r in picked],
                "candidates": made,
            }, indent=2))
            run.note(f"shortlist of {len(picked)} written")
            stage.update(1, 1)
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps({"eligible": len(eligible), "picked": len(picked)}))


if __name__ == "__main__":
    main()
