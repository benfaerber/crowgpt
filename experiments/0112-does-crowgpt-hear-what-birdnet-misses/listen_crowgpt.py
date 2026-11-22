"""0112 step 2: CrowGPT Dual-AR 17M hidden states, mean-pooled per span, every temporal block.

    crowgpt/.venv/bin/python experiments/0112-does-crowgpt-hear-what-birdnet-misses/listen_crowgpt.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import librosa
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sets  # noqa: E402

sys.path.insert(0, str(sets.REPO / "crowgpt" / "src"))
from crowgpt.codec import CODEBOOK_SIZE, FRAME_RATE, HOP, SAMPLE_RATE, Codec, normalise  # noqa: E402
from crowgpt.dualar import DualARConfig, DualARCrowGPT  # noqa: E402
from crowgpt.progress import Run  # noqa: E402
from crowgpt.tokens import Vocabulary  # noqa: E402
from crowgpt.model import rope_cos_sin  # noqa: E402

CHECKPOINT = sets.REPO / "crowgpt" / "results" / "scaling-0100" / "dualar-17M-240k" / "step-240000.pt"
OUT = sets.CACHE / "crowgpt.npz"
LEAD_S = 0.25
FADE_S = 0.010
BATCH = 48


class CrowGPTListener:
    """Audio span in, one mean hidden vector per temporal block out."""

    def __init__(self, device: str = "cuda"):
        blob = torch.load(CHECKPOINT, map_location=device, weights_only=False)
        manifest = blob["manifest"]
        config = DualARConfig(**{k: v for k, v in blob["config"].items() if k != "arch"})
        self.model = DualARCrowGPT(config).to(device).eval()
        self.model.load_state_dict(blob["model"])
        self.vocabulary = Vocabulary(manifest["n_codebooks"], manifest["species"], manifest.get("call_types", ()),
                                     manifest.get("channels", ()), n_unit_buckets=manifest.get("n_unit_buckets", 0))
        self.codec = Codec(bandwidth=manifest["bandwidth"], device=device)
        self.device = device
        self.species = self.vocabulary.species_token("american-crow")
        self.unit = self._unit_argmax()

    @torch.no_grad()
    def _unit_argmax(self) -> int:
        start, end = self.vocabulary.prefix_slots()[1]
        h = self.model.temporal_hidden(self.model.token_embedding(torch.tensor([[self.species]], device=self.device)))
        return start + int((h[0, -1] @ self.model.head.weight[start:end].T).argmax())

    @torch.no_grad()
    def _blocks(self, x: torch.Tensor) -> list[torch.Tensor]:
        positions = torch.arange(x.size(1), device=x.device)
        cos_sin = rope_cos_sin(positions, self.model.config.n_embd // self.model.config.n_head,
                               x.device, x.dtype, base=self.model.config.rope_base)
        outputs = []
        for block in self.model.temporal_blocks:
            x = block(x, cache=None, rope_pos=cos_sin)
            outputs.append(x)
        return outputs

    @torch.no_grad()
    def embed(self, waveforms: list[np.ndarray], lead_samples: list[int], span_seconds: list[float]) -> np.ndarray:
        """Each waveform is lead + span at 24 kHz. Returns [N, n_layer, n_embd] float16."""
        longest = max(len(w) for w in waveforms)
        batch = np.zeros((len(waveforms), longest), dtype=np.float32)
        for i, w in enumerate(waveforms):
            batch[i, :len(w)] = w
        codes = self.codec.encode(batch).to(self.device)
        offsets = torch.arange(codes.size(1), device=self.device)[None, :, None] * CODEBOOK_SIZE
        frames = (codes + offsets).permute(0, 2, 1)
        prefix = torch.tensor([[self.species, self.unit, self.vocabulary.duration_token(s)] for s in span_seconds],
                              device=self.device)
        x = torch.cat([self.model.token_embedding(prefix), self.model.embed_frames(frames)], dim=1)
        outputs = self._blocks(x)
        p = prefix.size(1)
        pooled = np.zeros((len(waveforms), len(outputs), self.model.config.n_embd), dtype=np.float16)
        for i, (w, lead) in enumerate(zip(waveforms, lead_samples)):
            first = p + lead // HOP
            last = p + max(lead // HOP + 1, int(np.ceil(len(w) / HOP)))
            for layer, h in enumerate(outputs):
                pooled[i, layer] = h[i, first:last].float().mean(0).cpu().numpy()
        return pooled


class SpanAudio:
    """Cuts spans out of one file loaded once, in CrowGPT's input convention."""

    def __init__(self, path: str):
        self.samples, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)

    def window(self, start: float, end: float) -> tuple[np.ndarray, int]:
        lo, hi = int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)
        lead = int(LEAD_S * SAMPLE_RATE)
        body = self.samples[lo:hi]
        before = self.samples[max(0, lo - lead):lo]
        before = np.concatenate([np.zeros(lead - len(before), dtype=np.float32), before])
        peak = float(np.max(np.abs(body))) if body.size else 0.0
        scale = 0.89 / peak if peak > 0 else 1.0
        return np.concatenate([before, body]).astype(np.float32) * scale, lead

    def isolated(self, onset: float, offset: float) -> tuple[np.ndarray, int]:
        body = self.samples[int(onset * SAMPLE_RATE):int(offset * SAMPLE_RATE)].astype(np.float32).copy()
        fade = min(int(FADE_S * SAMPLE_RATE), len(body) // 2)
        if fade:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            body[:fade] *= ramp
            body[-fade:] *= ramp[::-1]
        lead = int(LEAD_S * SAMPLE_RATE)
        return np.concatenate([np.zeros(lead, dtype=np.float32), normalise(body)]), lead


def main():
    spans = sets.SpanCatalogue().all()
    done = {}
    if OUT.exists():
        saved = np.load(OUT)
        done = dict(zip(saved["ids"].tolist(), saved["layers"]))
    todo = [s for s in spans if s.span_id not in done]
    by_file = defaultdict(list)
    for s in todo:
        by_file[s.path].append(s)
    run = Run("0112 CrowGPT hidden states", ["embed"])
    listener = CrowGPTListener()
    finished = 0
    with run.stage("embed") as stage:
        stage.update(0, len(todo))
        for path, group in by_file.items():
            try:
                audio = SpanAudio(path)
            except Exception as error:  # noqa: BLE001
                print(f"skip {path}: {error}")
                finished += len(group)
                continue
            for i in range(0, len(group), BATCH):
                chunk = group[i:i + BATCH]
                cut = [audio.isolated(s.start, s.end) if s.isolated else audio.window(s.start, s.end) for s in chunk]
                keep = [(s, c) for s, c in zip(chunk, cut) if len(c[0]) > c[1] + HOP]
                if keep:
                    layers = listener.embed([c[0] for _, c in keep], [c[1] for _, c in keep],
                                            [s.end - s.start for s, _ in keep])
                    for (s, _), row in zip(keep, layers):
                        done[s.span_id] = row
                finished += len(chunk)
            stage.update(finished, len(todo), extra=f"{len(done)} spans")
            if len(done) % 2000 < BATCH:
                np.savez(OUT, ids=np.array(list(done)), layers=np.stack(list(done.values())))
    np.savez(OUT, ids=np.array(list(done)), layers=np.stack(list(done.values())))
    run.note(f"{len(done)} spans embedded at {FRAME_RATE} Hz, unit token {listener.unit}")


if __name__ == "__main__":
    main()
