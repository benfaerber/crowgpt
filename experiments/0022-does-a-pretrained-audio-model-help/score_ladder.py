"""Score every rung of the LoRA ladder on the same axis 0022 used.

Trimmed to 3 s, resampled to 24 kHz, peak normalised — identical treatment to
0022, so these numbers sit on the same scale as `real 65.0%, crowgpt 71.7%,
lora(2000) 35.0%, base 10.8%` rather than beside it.

The shape is the answer. Still climbing at 3,000 steps means more training is
worth buying; flat after 1,000 means it is not, whatever the intuition about
LoRAs says.
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
import soundfile as sf
from scipy.signal import resample_poly

from crowgpt.birdnet import BirdNet
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run

LADDER = REPO / "data" / "sa3-lora" / "ladder" / "ladder.json"
OUT = Path(__file__).resolve().parent / "ladder.json"
CLIP_SECONDS = 3.0


def standardise(audio, sr):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        from math import gcd
        divisor = gcd(int(sr), SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, int(sr) // divisor)
    return normalise(audio[: int(CLIP_SECONDS * SAMPLE_RATE)]).astype(np.float32)


def main():
    rungs = json.loads(LADDER.read_text())
    run = Run("0022 LADDER — DOES THE LORA STILL CLIMB",
              [r["tag"] for r in rungs])
    birdnet = BirdNet(sample_rate=SAMPLE_RATE)
    report = {}
    for rung in rungs:
        with run.stage(rung["tag"]) as stage:
            folder = Path(rung["dir"])
            index = json.loads((folder / "index.json").read_text())
            clips = []
            for row in index["clips"]:
                audio, sr = sf.read(str(folder / row["file"]))
                clips.append(standardise(audio, sr))
            scores, crow_min = birdnet.confidence(clips)
            got = [s for s in scores if s is not None]
            detected = sum(1 for s in got if s >= crow_min)
            report[rung["tag"]] = {
                "model": rung["model"], "step": rung["step"],
                "clips": len(clips), "detected": detected,
                "rate": round(detected / len(clips), 3) if clips else None,
                "mean_confidence": round(float(np.mean(got)), 3) if got else None,
            }
            stage.say(f"{report[rung['tag']]['rate']:.1%}")
        OUT.write_text(json.dumps(report, indent=2) + "\n")

    run.note("BirdNET corvid rate by rung:")
    for model in ("small-sfx-base", "medium-base"):
        row = [(r["step"], r["rate"]) for r in report.values() if r["model"] == model]
        if row:
            run.note(f"  {model}: " + "  ".join(f"{s}:{v:.0%}" for s, v in sorted(row)))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
