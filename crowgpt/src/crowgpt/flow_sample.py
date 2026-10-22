"""Generating audio from the flow model.

LENGTH COMES FROM THE CORPUS, NEVER FROM A HYPERPARAMETER. `tokens.py` settled
this for the autoregressive model — the duration bucket is sampled from the
empirical per-species distribution so bout lengths are something the data decides.
The same rule holds here for a stronger reason: this model has no EOS and no way
to stop, so its length is chosen by the caller, and choosing it by hand would put
an invented prior exactly where 0025 and 0026 were trying to measure one.

AND THE 1.0-SECOND FLOOR IS NOT OPTIONAL. 0044 found every listening page in the
series had filtered real arms at 1.0 s and generated arms not at all — 18-20% of
generated clips were sub-second, the shortest 0.08 s — so every real-vs-generated
gap in six experiments is an upper bound. Sampling lengths from the empirical
distribution reproduces that bias unless the same floor is applied here, at the
source, which is what `Lengths` does.
"""

import json
from pathlib import Path

import numpy as np
import torch

from crowgpt.continuous import HOP, SAMPLE_RATE, ContinuousCodec
from crowgpt.flow import Config, FlowDiT, RectifiedFlow

MIN_SECONDS = 1.0


class Lengths:
    """The empirical bout-length distribution, floored at a gradeable duration."""

    def __init__(self, latent_dir, split="train", min_seconds=MIN_SECONDS):
        records = [json.loads(line) for line
                   in (Path(latent_dir) / f"{split}.jsonl").read_text().splitlines() if line]
        floor = int(np.ceil(min_seconds * SAMPLE_RATE / HOP))
        self.frames = np.array([r["frames"] for r in records if r["frames"] >= floor])
        if not self.frames.size:
            raise ValueError(f"no bouts at or above {min_seconds}s in {split}")

    def draw(self, count, rng):
        return rng.choice(self.frames, size=count).tolist()


class FlowSampler:
    def __init__(self, checkpoint_dir, latent_dir, device=None, n_stages=32):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        blob = torch.load(Path(checkpoint_dir) / "model.pt", map_location=self.device)
        self.config = Config(**blob["config"])
        self.model = FlowDiT(self.config).to(self.device).eval()
        self.model.load_state_dict(blob["model"])
        self.flow = RectifiedFlow(self.model)
        stats = blob["stats"]
        self.mean = torch.tensor(stats["mean"], device=self.device)
        self.std = torch.tensor(stats["std"], device=self.device)
        self.codec = ContinuousCodec(n_stages=n_stages, device=self.device)
        self.lengths = Lengths(latent_dir)

    def generate(self, count=8, steps=32, seed=0, max_batch=8):
        """Returns a list of float32 waveforms, lengths drawn from the corpus."""
        rng = np.random.default_rng(seed)
        generator = torch.Generator(device=self.device).manual_seed(int(seed))
        wanted = self.lengths.draw(count, rng)

        clips = []
        # Grouped by length because a batch has one sequence length, and padding
        # a flow batch would denoise the padding too — it is not masked at
        # sampling time and there is nothing sensible for it to become.
        for frames in sorted(set(wanted)):
            remaining = sum(1 for f in wanted if f == frames)
            while remaining:
                size = min(remaining, max_batch)
                latent = self.flow.sample(int(frames), count=size, steps=steps,
                                          device=self.device, generator=generator)
                latent = latent * self.std + self.mean
                audio = self.codec.decode(latent.transpose(1, 2))
                clips.extend(np.asarray(a, dtype=np.float32) for a in audio)
                remaining -= size
        return clips


def write_clips(clips, out_dir, prefix="flow", sample_rate=SAMPLE_RATE):
    import soundfile as sf

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, clip in enumerate(clips):
        peak = float(np.abs(clip).max())
        # Peak-normalised, because DAC's decoder returns whatever level it likes
        # and 0022 recorded Stable Audio arriving at peak 0.05-0.19 against the
        # corpus's 0.89 — a level difference is audible and is not the model.
        if peak > 0:
            clip = clip / peak * 0.89
        path = out_dir / f"{prefix}-{i:02d}.wav"
        sf.write(path, clip, sample_rate)
        paths.append(path)
    return paths
