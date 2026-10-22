"""The continuous half of the project: DAC latents instead of codec symbols.

WHY THIS EXISTS. Every generator here so far has predicted a codebook INDEX, and
0052 measured what that costs. DAC's fine stages carry 9.935 bits of 10 as symbol
indices and no capacity extracts them (0035, extender 0/24) — but the same
information carried as continuous vectors tolerates 20% per-channel corruption
INAUDIBLY (0052: 10/25, below chance, against 21/25 at 80%). "Unpredictable as a
symbol" and "unpredictable as a sound" are different claims, and only the first
was ever measured.

So a model working here does not have to be right. It has to be close, and 0052
says how close: at least 20% of each channel's spread, which is an enormous
budget by the standards of a 1024-way softmax that is either right or wrong.

THE CODEBOOK IS THE ONLY THING REMOVED. Each RVQ stage projects the running
residual to 8 dimensions (`in_proj`), snaps it to a codebook entry, projects back
to 1024 (`out_proj`) and subtracts. Dropping the snap leaves a rank-8 linear
cascade whose concatenated 8-vectors are exactly what DAC calls `latents`, and
whose sum is a rank-8N approximation of the encoder's z.

`quantizer.from_latents` LOOKS LIKE THIS AND IS NOT. Its docstring opens "given
the unquantized latents" and it then calls `decode_latents`, a nearest-neighbour
codebook search. Anything routed through it is quantized and would measure the
discrete path under a continuous name.

AND DO NOT REACH FOR `z` INSTEAD. The raw 1024-d encoder output decodes WORSE
than this rank-256 approximation of it — 0.5492 against 0.2588 log-mel (0052) —
because DAC's decoder was trained on quantizer output and raw z is off-manifold
for it. The compact representation is also the better-sounding one, which is not
the way round anyone expects.
"""

import json
from pathlib import Path

import numpy as np
import torch

SAMPLE_RATE = 24000
HOP = 320
STAGE_DIM = 8
DEFAULT_STAGES = 32


class ContinuousCodec:
    """DAC's residual cascade with the codebook lookup taken out."""

    def __init__(self, n_stages=DEFAULT_STAGES, model_type="24khz", device=None):
        import dac

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = dac.DAC.load(dac.utils.download(model_type=model_type))
        self.model = self.model.to(self.device).eval()
        if n_stages > self.model.n_codebooks:
            raise ValueError(
                f"{model_type} has {self.model.n_codebooks} stages, asked for {n_stages}")
        self.quantizers = self.model.quantizer.quantizers[:n_stages]
        self.n_stages = n_stages
        self.kind = f"dac-{model_type}-continuous"

    @property
    def dim(self):
        return self.n_stages * STAGE_DIM

    def frames(self, n_samples):
        return max(1, int(np.ceil(n_samples / HOP)))

    def _batch(self, samples):
        if isinstance(samples, torch.Tensor):
            batch = samples
        else:
            array = np.asarray(samples, dtype=np.float32)
            batch = torch.from_numpy(array if array.ndim == 2 else array[None])
        return batch[:, None].to(self.device)

    @torch.no_grad()
    def encode(self, samples):
        """[B, T] audio -> [B, dim, frames] continuous latent.

        The residual chain is recomputed WITHOUT quantization rather than read off
        `model.encode`, whose `latents` follow the quantized trajectory: each of
        its stages sees a residual that earlier codebook errors have already
        shifted. Mixing the two produces a latent that decodes, and decodes wrong.
        """
        residual = self.model.encoder(self.model.preprocess(self._batch(samples), SAMPLE_RATE))
        parts = []
        for quantizer in self.quantizers:
            projected = quantizer.in_proj(residual)
            parts.append(projected)
            residual = residual - quantizer.out_proj(projected)
        return torch.cat(parts, dim=1)

    @torch.no_grad()
    def to_z(self, latent):
        summed = 0.0
        for i, quantizer in enumerate(self.quantizers):
            summed = summed + quantizer.out_proj(
                latent[:, i * STAGE_DIM : (i + 1) * STAGE_DIM, :])
        return summed

    @torch.no_grad()
    def decode(self, latent):
        """[B, dim, frames] -> [B, samples] float32 on the CPU."""
        if latent.dim() == 2:
            latent = latent[None]
        audio = self.model.decode(self.to_z(latent.to(self.device)))
        return audio.squeeze(1).float().cpu().numpy()

    def roundtrip(self, samples):
        return self.decode(self.encode(samples))


class LatentWriter:
    """Bouts -> one float16 memmap per split, plus an index and a manifest.

    FLOAT16 IS SAFE HERE AND IT IS WORTH SAYING WHY, because storing a generative
    target at half precision usually is not. 0052 measured the budget: 20% of a
    channel's standard deviation is inaudible. Float16 carries about three decimal
    digits, so its representation error is ~1e-3 relative — roughly two hundred
    times inside the budget. `check_precision` asserts it rather than trusting it.

    THE SPLIT IS BY GROUP, inherited from `BoutStore.split` unchanged, because
    recordists upload one bird on one day under several ids and a bout-level split
    puts near-duplicates on both sides.
    """

    def __init__(self, store, out_dir, codec, species=None):
        self.store = store
        self.out_dir = Path(out_dir)
        self.codec = codec
        self.species = set(species) if species else None

    def _rows(self, indices):
        for i in indices:
            row = self.store.index[i]
            if self.species and row["species"] not in self.species:
                continue
            yield i, row

    def _encode_batch(self, pending):
        longest = max(samples.size for _, _, samples in pending)
        batch = np.zeros((len(pending), longest), dtype=np.float32)
        for k, (_, _, samples) in enumerate(pending):
            batch[k, : samples.size] = samples
        encoded = self.codec.encode(batch).half().cpu().numpy()
        for k, (index, row, samples) in enumerate(pending):
            # Transposed to [frames, dim] — FRAME-MAJOR IS THE ONLY LAYOUT THAT
            # WORKS. Bouts have different lengths, so a file of [dim, frames]
            # blocks cannot be reshaped into one array at all; frame-major makes
            # the split a flat sequence of frames that a bout slices by cursor.
            # It is also the orientation a transformer wants, (batch, time,
            # channel), so nothing transposes on the hot path.
            yield index, row, encoded[k][:, : self.codec.frames(samples.size)].T

    def run(self, splits, batch_size=16, on_progress=None):
        from crowgpt.codec import normalise

        self.out_dir.mkdir(parents=True, exist_ok=True)
        manifest = {"codec": self.codec.kind, "dim": self.codec.dim,
                    "n_stages": self.codec.n_stages, "sample_rate": SAMPLE_RATE,
                    "hop": HOP, "dtype": "float16", "splits": {}}

        totals = {name: sum(1 for _ in self._rows(idx)) for name, idx in splits.items()}
        done = 0
        overall = sum(totals.values())

        for split, indices in splits.items():
            handle = open(self.out_dir / f"{split}.f16", "wb")
            records, cursor, pending = [], 0, []

            def flush():
                nonlocal cursor, done
                for index, row, latent in self._encode_batch(pending):
                    handle.write(np.ascontiguousarray(latent).tobytes())
                    records.append({
                        "start": cursor, "frames": int(latent.shape[0]),
                        "species": row["species"], "group_key": row["group_key"],
                        "recording_id": row["recording_id"], "bout": int(index),
                        "seconds": round(row["n_samples"] / SAMPLE_RATE, 3),
                    })
                    cursor += int(latent.shape[0])
                    done += 1
                pending.clear()

            for index, row in self._rows(indices):
                pending.append((index, row, normalise(self.store.audio(row))))
                if len(pending) >= batch_size:
                    flush()
                    if on_progress and done % 200 < batch_size:
                        on_progress(split, done, overall)
            if pending:
                flush()
            handle.close()

            (self.out_dir / f"{split}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in records))
            manifest["splits"][split] = {"bouts": len(records), "frames": cursor}
            print(f"   {split}: {len(records)} bouts, {cursor} frames", flush=True)

        manifest["stats"] = self._statistics(manifest)
        (self.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest

    def _statistics(self, manifest):
        """Per-channel mean and std over TRAIN ONLY.

        Over train only because these normalise the model's input, and statistics
        taken over validation are a leak — small here, free to avoid.
        """
        data = LatentDataset(self.out_dir, "train", manifest=manifest)
        stream = data.stream.astype(np.float32)
        return {"mean": stream.mean(axis=0).tolist(), "std": stream.std(axis=0).tolist()}


class LatentDataset:
    """A written split, read back as a memmap."""

    def __init__(self, out_dir, split, manifest=None):
        self.out_dir = Path(out_dir)
        self.manifest = manifest or json.loads((self.out_dir / "manifest.json").read_text())
        self.dim = self.manifest["dim"]
        self.records = [json.loads(line) for line
                        in (self.out_dir / f"{split}.jsonl").read_text().splitlines() if line]
        flat = np.memmap(self.out_dir / f"{split}.f16", dtype=np.float16, mode="r")
        self.stream = flat.reshape(-1, self.dim)

    def __len__(self):
        return len(self.records)

    def latent(self, i):
        """[frames, dim] for one bout."""
        record = self.records[i]
        return self.stream[record["start"] : record["start"] + record["frames"]]

    def statistics(self):
        """Per-channel mean and std as [1, dim], ready to broadcast over time."""
        stats = self.manifest["stats"]
        return (np.asarray(stats["mean"], dtype=np.float32)[None],
                np.asarray(stats["std"], dtype=np.float32)[None])


def check_precision(codec, samples):
    """Relative error introduced by float16 storage, against 0052's 0.20 budget."""
    exact = codec.encode(samples)
    stored = exact.half().float()
    spread = exact.std(dim=(0, 2), keepdim=True).clamp_min(1e-8)
    return float(((stored - exact).abs() / spread).max())
