"""What would the EnCodec decoder finetune cost, measured on this machine?

TODO.txt holds the decision entry: freeze EnCodec's encoder and quantizer,
retrain ONLY the decoder on the extracted corpus with the adversarial +
multi-scale spectral losses it was originally trained with. Tokens stay
bit-identical, so model-fair-k8 keeps working untouched. The entry says it
"needs a costing not a build" — this is the costing's measured half.

Three measurements, none needing more than minutes of GPU:

  1. Where the parameters are. Encoder / quantizer / decoder split of
     facebook/encodec_24khz, plus a representative MS-STFT discriminator at
     the shape the EnCodec paper uses (5 STFT scales, 32-filter conv stacks).
     The frozen share is the share that costs forward-only.

  2. What a step costs, timed. Batch of 1 s excerpts at 24 kHz — the paper's
     own excerpt length — through:
       recipe A: frozen encode -> decoder forward -> multi-scale spectral
                 loss -> backward (decoder only)
       recipe B: A plus the adversarial half — generator adversarial +
                 feature-matching losses through the decoder, then a
                 discriminator update on (real, fake.detach())
     Timed after warmup, with CUDA synchronised, peak VRAM recorded.

  3. How big an epoch is. Corpus seconds from the bout store index — the
     whole extracted corpus and american-crow alone — turned into steps per
     pass at the benchmarked batch size.

The discriminator here is a timing stand-in built to the paper's shape, not
training code. If the finetune is built, vendor audiocraft's (MIT) or write
one against these numbers; either way the per-step cost is what this measures.

The README does the arithmetic and carries the recommendation.
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import torch
import torch.nn as nn
import torch.nn.functional as F

from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent

SR = 24000
EXCERPT_SECONDS = 1.0
BATCH_SIZES = (16, 32, 64)
STFT_SCALES = (2048, 1024, 512, 256, 128)
WARMUP, TIMED = 5, 20


def spectral_loss(x, y):
    """Multi-scale STFT: L1 on magnitude and on log-magnitude, summed over
    scales. The shape of EnCodec's reconstruction loss, minus the balancer."""
    total = x.new_zeros(())
    for n_fft in STFT_SCALES:
        window = torch.hann_window(n_fft, device=x.device)
        gx = torch.stft(x, n_fft, n_fft // 4, window=window, return_complex=True).abs()
        gy = torch.stft(y, n_fft, n_fft // 4, window=window, return_complex=True).abs()
        total = total + F.l1_loss(gx, gy) + F.l1_loss(
            (gx + 1e-5).log(), (gy + 1e-5).log()
        )
    return total


class StftDiscriminator(nn.Module):
    """One scale of the paper's MS-STFT discriminator: complex STFT as two
    channels through a 32-filter conv stack. Timing stand-in, honest shape."""

    def __init__(self, n_fft):
        super().__init__()
        self.n_fft = n_fft
        self.convs = nn.ModuleList([
            nn.Conv2d(2, 32, (3, 9), padding=(1, 4)),
            nn.Conv2d(32, 32, (3, 9), stride=(1, 2), dilation=(1, 1), padding=(1, 4)),
            nn.Conv2d(32, 32, (3, 9), stride=(1, 2), dilation=(2, 1), padding=(2, 4)),
            nn.Conv2d(32, 32, (3, 9), stride=(1, 2), dilation=(4, 1), padding=(4, 4)),
            nn.Conv2d(32, 32, (3, 3), padding=(1, 1)),
        ])
        self.head = nn.Conv2d(32, 1, (3, 3), padding=(1, 1))

    def forward(self, audio):
        window = torch.hann_window(self.n_fft, device=audio.device)
        spec = torch.stft(audio, self.n_fft, self.n_fft // 4, window=window,
                          return_complex=True)
        x = torch.stack([spec.real, spec.imag], dim=1)
        features = []
        for conv in self.convs:
            x = F.leaky_relu(conv(x), 0.2)
            features.append(x)
        return self.head(x), features


class MsStftDiscriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.scales = nn.ModuleList(StftDiscriminator(n) for n in STFT_SCALES)

    def forward(self, audio):
        return [scale(audio) for scale in self.scales]


def timed(fn):
    for _ in range(WARMUP):
        fn()
    torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(TIMED):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - start) / TIMED


def count(module):
    return sum(p.numel() for p in module.parameters())


def main():
    from transformers import EncodecModel

    results = {"gpu": torch.cuda.get_device_name(0)}

    model = EncodecModel.from_pretrained("facebook/encodec_24khz").to("cuda")
    results["params"] = {
        "encoder": count(model.encoder),
        "quantizer": count(model.quantizer),
        "decoder": count(model.decoder),
        "total": count(model),
    }
    discriminator = MsStftDiscriminator().to("cuda")
    results["params"]["discriminator"] = count(discriminator)

    store = BoutStore(DATA / "bouts")
    seconds = {}
    for row in store.index:
        seconds[row["species"]] = seconds.get(row["species"], 0) + row["n_samples"] / SR
    results["corpus"] = {
        "total_hours": round(sum(seconds.values()) / 3600, 1),
        "american_crow_hours": round(seconds.get("american-crow", 0) / 3600, 1),
        "bouts": len(store.index),
        "species": len(seconds),
    }

    for p in model.encoder.parameters():
        p.requires_grad_(False)
    for p in model.quantizer.parameters():
        p.requires_grad_(False)
    # cudnn refuses LSTM backward in eval mode, and from_pretrained returns
    # eval. Train mode on the decoder only — the frozen half stays as served.
    model.decoder.train()
    dec_opt = torch.optim.Adam(model.decoder.parameters(), lr=1e-4)
    disc_opt = torch.optim.Adam(discriminator.parameters(), lr=1e-4)

    n_samples = int(SR * EXCERPT_SECONDS)
    results["steps"] = {}
    for batch in BATCH_SIZES:
        audio = torch.randn(batch, 1, n_samples, device="cuda") * 0.1

        def encode():
            with torch.no_grad():
                encoded = model.encode(audio, bandwidth=6.0)
                embeddings = model.quantizer.decode(
                    encoded.audio_codes[0].transpose(0, 1)
                )
            return embeddings

        embeddings = encode()

        def step_spectral():
            dec_opt.zero_grad(set_to_none=True)
            fake = model.decoder(encode())
            width = min(fake.shape[-1], audio.shape[-1])
            loss = spectral_loss(fake[:, 0, :width], audio[:, 0, :width])
            loss.backward()
            dec_opt.step()

        def step_adversarial():
            dec_opt.zero_grad(set_to_none=True)
            fake = model.decoder(encode())
            width = min(fake.shape[-1], audio.shape[-1])
            fake, real = fake[:, 0, :width], audio[:, 0, :width]
            loss = spectral_loss(fake, real)
            fake_out = discriminator(fake)
            real_out = discriminator(real)
            for (score, fake_feats), (_, real_feats) in zip(fake_out, real_out):
                loss = loss + F.relu(1 - score).mean()
                for ff, rf in zip(fake_feats, real_feats):
                    loss = loss + F.l1_loss(ff, rf.detach())
            loss.backward()
            dec_opt.step()

            disc_opt.zero_grad(set_to_none=True)
            d_loss = fake.new_zeros(())
            with torch.no_grad():
                detached = model.decoder(encode())[:, 0, :width]
            for (fake_score, _), (real_score, _) in zip(
                discriminator(detached), discriminator(real)
            ):
                d_loss = d_loss + F.relu(1 + fake_score).mean() + F.relu(1 - real_score).mean()
            d_loss.backward()
            disc_opt.step()

        try:
            torch.cuda.reset_peak_memory_stats()
            spec_s = timed(step_spectral)
            spec_vram = torch.cuda.max_memory_allocated() / 2**30
            torch.cuda.reset_peak_memory_stats()
            adv_s = timed(step_adversarial)
            adv_vram = torch.cuda.max_memory_allocated() / 2**30
        except torch.cuda.OutOfMemoryError:
            results["steps"][str(batch)] = "OOM"
            torch.cuda.empty_cache()
            continue

        results["steps"][str(batch)] = {
            "spectral_ms": round(spec_s * 1000, 1),
            "spectral_vram_gb": round(spec_vram, 2),
            "adversarial_ms": round(adv_s * 1000, 1),
            "adversarial_vram_gb": round(adv_vram, 2),
            "examples_per_hour_adversarial": int(batch / adv_s * 3600),
        }
        print(f"batch {batch}: spectral {spec_s * 1000:.0f} ms · "
              f"adversarial {adv_s * 1000:.0f} ms · {adv_vram:.1f} GB peak")

    corpus_s = results["corpus"]["total_hours"] * 3600
    arithmetic = {}
    for batch, row in results["steps"].items():
        if row == "OOM":
            continue
        steps_per_pass = corpus_s / int(batch)
        arithmetic[batch] = {
            "steps_per_corpus_pass": int(steps_per_pass),
            "hours_per_pass_spectral": round(steps_per_pass * row["spectral_ms"] / 3.6e6, 2),
            "hours_per_pass_adversarial": round(
                steps_per_pass * row["adversarial_ms"] / 3.6e6, 2),
        }
    results["per_corpus_pass"] = arithmetic

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
