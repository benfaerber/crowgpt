"""Is CrowGPT's overlap with its training set memorisation, or mode-seeking?

The judge measured generated bouts sharing an exact token n-gram with the
training set 37.5% of the time over ~213 ms, against 4.3% for held-out real
audio. Read as memorisation that is damning. But there is a confound, and it is
not small: sampling at temperature 0.95 with top-k 200 draws from the model's
high-probability region, and the most probable patterns are the most COMMON
training patterns. A model that had memorised nothing would still overlap more
than natural audio does, simply by playing it safe.

The two come apart under temperature. Mode-seeking is a property of sampling and
should melt as temperature rises; memorisation is a property of the weights and
should not. So this sweeps temperature and top-k and watches both the overlap
and whether BirdNET still hears a crow — because the fix implied by each answer
is different, and one of them is "sample hotter", which is free.

Run:
    cd ../../crowgpt && PYTHONPATH=src .venv/bin/python ../experiments/0015-is-it-copying-or-playing-it-safe/run.py
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = REPO / "data" / "crowgpt"
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.corpus import Corpus  # noqa: E402
from crowgpt.judge import Ambience, BirdNetJudge, NgramIndex  # noqa: E402
from crowgpt.sample import Sampler  # noqa: E402
from crowgpt.tokens import TokenDataset  # noqa: E402

TEMPERATURES = (0.7, 0.85, 1.0, 1.15, 1.3)
TOP_K = (200, 0)
PER_SPECIES = 4
FRAMES = 16  # ~213 ms, the span the judge reported


def main():
    sampler = Sampler(REPO / "crowgpt" / "results" / "model" / "model.pt", token_dir=DATA / "tokens")
    train = TokenDataset(DATA / "tokens", "train")
    test = TokenDataset(DATA / "tokens", "test")
    judge = BirdNetJudge()
    ambience = Ambience([r for recs in Corpus().recordings().values() for r in recs[:3]])

    index = NgramIndex(sampler.vocabulary.n_codebooks, stages=1)
    canonical = [train.sequence(i)[2:-1] for i in range(len(train)) if train.records[i]["canonical"]]
    index.build(canonical)
    baseline = index.hit_rate([test.sequence(i)[2:-1] for i in range(len(test))])[f"{FRAMES}_frames"]
    print(f"held-out real base rate at {FRAMES} frames: {baseline:.3f}\n", flush=True)

    rows = []
    for temperature in TEMPERATURES:
        for top_k in TOP_K:
            tokens, detections, durations = [], [], []
            for s, slug in enumerate(sampler.species):
                for i in range(PER_SPECIES):
                    seed = s * 100 + i
                    flat = sampler.tokens(slug, temperature=temperature,
                                          top_k=top_k or None, seed=seed)
                    tokens.append(flat)
                    if flat.size == 0:
                        detections.append(0.0)
                        durations.append(0.0)
                        continue
                    codes = sampler.codec.unflatten(flat)
                    audio = sampler.codec.decode(__import__("torch").from_numpy(codes))[0]
                    durations.append(audio.size / 24000)
                    detections.append(judge.confidence(ambience.place(audio))[0])

            overlap = index.hit_rate(tokens)[f"{FRAMES}_frames"]
            scores = np.array(detections)
            row = {
                "temperature": temperature,
                "top_k": top_k or None,
                "ngram_overlap": overlap,
                "overlap_over_baseline": round(overlap / baseline, 1) if baseline else None,
                "detected_rate": round(float((scores >= judge.crow_min).mean()), 3),
                "mean_conf": round(float(scores.mean()), 3),
                "mean_dur_sec": round(float(np.mean(durations)), 2),
            }
            rows.append(row)
            print(f"  T={temperature:<5} top_k={str(top_k or 'off'):<4} "
                  f"overlap={overlap:.3f} ({row['overlap_over_baseline']}x base)  "
                  f"detected={row['detected_rate']:.2f}  conf={row['mean_conf']:.3f}  "
                  f"dur={row['mean_dur_sec']:.2f}s", flush=True)

    results = {
        "frames": FRAMES,
        "per_species": PER_SPECIES,
        "held_out_real_base_rate": baseline,
        "sweep": rows,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {HERE / 'results.json'}")


if __name__ == "__main__":
    main()
