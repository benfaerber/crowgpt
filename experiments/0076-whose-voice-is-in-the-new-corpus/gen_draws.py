"""0076 stage 1 (GPU): matched draws from both arms, plus real-bout samples."""
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import soundfile as sf
import torch

from crowgpt.calltype import CORE
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.tokens import BoutStore

OUT = Path(__file__).resolve().parent / "wavs"
DATA = REPO / "data" / "crowgpt"
PER = 20
ARMS = {
    "ct-b32": (HERE / "results" / "model-longctx-ct-b32" / "model.pt", 460),
    "calltype": (HERE / "results" / "model-calltype" / "model.pt", 225),
}
CORPORA = {"real-v1": "bouts-v1", "real-6s": "bouts-6s"}


def write(path, audio):
    peak = float(np.max(np.abs(audio))) or 1.0
    sf.write(path, audio / peak * 0.95, SAMPLE_RATE, format="WAV",
             subtype="PCM_16")


def main():
    run = Run("0076 — DRAWS FOR THE VOICE PROBE", ["draw", "real"])
    with run.stage("draw") as stage:
        done, total = 0, len(ARMS) * len(CORE) * PER
        for arm, (ckpt, frames) in ARMS.items():
            sampler = Sampler(ckpt, decoder_state="finetuned")
            for call_type in CORE:
                folder = OUT / arm / call_type.replace(" ", "-")
                folder.mkdir(parents=True, exist_ok=True)
                for i in range(PER):
                    audio = sampler.audio(
                        "american-crow", call_type=call_type,
                        seed=42_000 + i, temperature=1.1 if arm == "ct-b32" else 1.0,
                        top_k=200, max_frames=frames)
                    write(folder / f"{i:03d}.wav", audio)
                    done += 1
                    stage.update(done, total, extra=f"{arm} {call_type}")
            del sampler
            torch.cuda.empty_cache()

    with run.stage("real") as stage:
        for name, dirname in CORPORA.items():
            store = BoutStore(DATA / dirname)
            rng = random.Random(76)
            positions = [i for i, r in enumerate(store.index)
                         if r["species"] == "american-crow"]
            picks = rng.sample(positions, 40)
            folder = OUT / name
            folder.mkdir(parents=True, exist_ok=True)
            for j, p in enumerate(picks):
                write(folder / f"{j:03d}.wav",
                      normalise(store.audio(store.index[p])))
            stage.update(1, 1, extra=name)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
