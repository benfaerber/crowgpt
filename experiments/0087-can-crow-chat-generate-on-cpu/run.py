import sys, time, os
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fieldserver" / "worker"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
import torch
device, threads, names = sys.argv[1], int(sys.argv[2]), sys.argv[3].split(",")
torch.set_num_threads(threads)
from generate_worker import RECIPES
from crowgpt.sample import Sampler
for name in names:
    r = RECIPES[name]
    t = time.monotonic()
    s = Sampler(r.checkpoint, device=device, decoder_state=r.decoder_state)
    print(f"{name} load {device} x{threads}: {time.monotonic()-t:.1f}s", flush=True)
    ct = r.call_types[0] if r.call_types else None
    for seed in (1, 2, 3):
        t = time.monotonic()
        wav = s.audio(r.species, call_type=ct, seed=seed, **r.sampling)
        el = time.monotonic() - t
        n = wav.shape[-1] if hasattr(wav, "shape") else len(wav)
        print(f"  seed {seed}: {el:.1f}s wall, {n} samples", flush=True)
