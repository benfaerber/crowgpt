"""Post-train smoke: the checkpoint loads and answers each button, no crash.

Not a quality gate — that is run.py's job — just proof the morning starts from
a checkpoint that samples, so a prefix_len-4 wiring failure surfaces tonight
rather than mid-validation.
"""

import sys
import time
from pathlib import Path

REPO = Path("/home/ben/Code/cawtalker")
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import soundfile as sf

from crowgpt.calltype import CORE
from crowgpt.sample import Sampler

HERE = Path(__file__).resolve().parent
MODEL = REPO / "crowgpt" / "results" / "model-longctx-ct" / "model.pt"
OUT = HERE / "smoke"


def main():
    OUT.mkdir(exist_ok=True)
    sampler = Sampler(MODEL, decoder_state="finetuned")
    assert set(CORE) <= set(sampler.vocabulary.call_types), \
        sampler.vocabulary.call_types
    for i, call_type in enumerate(CORE):
        started = time.monotonic()
        audio = sampler.audio("american-crow", call_type=call_type,
                              seed=40_000 + i, temperature=1.1, top_k=200,
                              max_frames=460)
        peak = float(np.max(np.abs(audio))) or 1.0
        name = OUT / f"{call_type.replace(' ', '-')}.wav"
        sf.write(name, audio / peak * 0.95, 24_000, format="WAV",
                 subtype="PCM_16")
        print(f"{call_type}: {len(audio) / 24_000:.1f}s "
              f"in {time.monotonic() - started:.1f}s -> {name.name}")
    print("smoke passes — all four buttons answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
