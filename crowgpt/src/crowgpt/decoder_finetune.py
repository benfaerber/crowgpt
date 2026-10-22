"""Finetune EnCodec's decoder on the corpus. Tokens stay bit-identical.

The decision and its evidence: 0057 ("codec makes it scratchy") heard the K=8
round-trip of REAL audio grade down to D+ with no model involved, and 0036
measured EnCodec cutting the 800-4000 Hz corvid band by 0.67 dB inside call
regions — it was trained on speech and music. 0058 priced the fix: freeze the
encoder and quantizer, retrain only the decoder (7.4M of 14.9M params) on the
extracted corpus, 1.48 GPU-hours per corpus pass at the adversarial recipe's
batch-16 ceiling. Because the encoder never moves, every existing token
memmap, checkpoint and sampler keeps working untouched; only what the tokens
SOUND like changes.

Two arms, run separately:

    spectral      multi-scale STFT loss only. Nine times cheaper. The control:
                  if adversarial training collapses or artifacts, this is the
                  floor it must beat; expected to over-smooth on its own.
    adversarial   spectral + MS-STFT discriminator (hinge) + feature matching,
                  the shape of EnCodec's own training. What the paper used the
                  adversarial half FOR is exactly the defect: texture.

THE GATE IS NOT THE TRAINING LOSS. 0058's costing found the originally planned
gate (0028's multi-res STFT instrument) is the same loss family this training
optimises, and over-smoothing LOWERS it while making a worse crow. So the
spectral distance is logged but does not vote. What votes, in order: AST-FAD
against raw on val bouts (an embedder the training never sees), the segmenter
unit-count delta (does decoding preserve burst structure), and a labelled
listen on TEST bouts the finetune never touched. Baselines for the frozen
decoder are measured at step 0 by the same code on the same clips.

Splits: trains on the train split only. Eval during training reads val. The
test split is never read here — it is the final listen's, and stays clean.

Progress: reports through crowgpt.progress.Run into the shared progress
directory (one JSON per run, listed by /api/training), updated every
UPDATE_EVERY steps, far inside the dashboard's 600 s stale window. Counting
is across the whole arm, not per pass. Checkpoints land in
results/decoder-finetune/<arm>/: latest.pt every eval, best.pt when val FAD
improves, history.json the metric trail.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.metrics import frechet_distance, multi_res_stft_distance
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore

MODEL_ID = "facebook/encodec_24khz"
BANDWIDTH = 6.0            # K=8, the operating point every model lives at
CROP_SECONDS = 1.0         # the paper's own excerpt length
BATCH = 16                 # 0058: the adversarial recipe's VRAM ceiling here
STFT_SCALES = (2048, 1024, 512, 256, 128)
LR_DECODER = 1e-4
LR_DISCRIMINATOR = 1e-4
BETAS = (0.5, 0.9)         # GAN-audio convention; EnCodec used the same
ADV_WEIGHT = 3.0
FEATURE_WEIGHT = 3.0
GRAD_CLIP = 1.0
UPDATE_EVERY = 25          # progress writes; ~9 s adversarial, well under 600 s
EVAL_EVERY = 5000          # steps between val evals + checkpoints
EVAL_BOUTS = 64            # val bouts, one per recording
SEED = 0


class SpectralLoss(nn.Module):
    """L1 on STFT magnitude and log-magnitude, summed over scales."""

    def __init__(self, scales=STFT_SCALES):
        super().__init__()
        self.scales = scales

    def forward(self, fake, real):
        total = fake.new_zeros(())
        for n_fft in self.scales:
            window = torch.hann_window(n_fft, device=fake.device)
            gf = torch.stft(fake, n_fft, n_fft // 4, window=window,
                            return_complex=True).abs()
            gr = torch.stft(real, n_fft, n_fft // 4, window=window,
                            return_complex=True).abs()
            total = total + F.l1_loss(gf, gr) + F.l1_loss(
                (gf + 1e-5).log(), (gr + 1e-5).log())
        return total / len(self.scales)


class ScaleDiscriminator(nn.Module):
    """One STFT scale: complex spectrum as two channels through a conv stack."""

    def __init__(self, n_fft):
        super().__init__()
        self.n_fft = n_fft
        self.convs = nn.ModuleList([
            nn.Conv2d(2, 32, (3, 9), padding=(1, 4)),
            nn.Conv2d(32, 32, (3, 9), stride=(1, 2), padding=(1, 4)),
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
    def __init__(self, scales=STFT_SCALES):
        super().__init__()
        self.scales = nn.ModuleList(ScaleDiscriminator(n) for n in scales)

    def forward(self, audio):
        return [scale(audio) for scale in self.scales]


class CropSampler:
    """Random 1 s crops from train-split bouts, normalised per bout.

    Bouts are weighted by their length so every SECOND of corpus is equally
    likely — uniform-per-bout would overweight short bouts. Normalisation is
    per bout before cropping, matching what TokenWriter fed the encoder, so
    the decoder trains on the level distribution the tokens were made at.
    """

    def __init__(self, store, seed=SEED, crop_seconds=CROP_SECONDS):
        self.store = store
        self.n_crop = int(crop_seconds * SAMPLE_RATE)
        splits = store.split(seed=SEED)
        self.rows = [i for i in splits["train"]
                     if store.index[i]["n_samples"] >= self.n_crop]
        lengths = np.array([store.index[i]["n_samples"] for i in self.rows],
                           dtype=np.float64)
        self.weights = lengths / lengths.sum()
        self.rng = np.random.default_rng(seed)
        self.corpus_seconds = float(lengths.sum() / SAMPLE_RATE)

    def batch(self, size=BATCH):
        chosen = self.rng.choice(len(self.rows), size=size, p=self.weights)
        crops = np.empty((size, self.n_crop), dtype=np.float32)
        for n, pick in enumerate(chosen):
            row = self.store.index[self.rows[pick]]
            audio = normalise(self.store.audio(row))
            start = self.rng.integers(0, audio.size - self.n_crop + 1)
            crops[n] = audio[start : start + self.n_crop]
        return torch.from_numpy(crops)


class Evaluator:
    """Val-split metrics for a decoder, and the frozen baseline to beat.

    STFT distance is the training loss's own family and is LOGGED ONLY. The
    voting metrics are AST-FAD (matched n against raw, per 0028's bias note)
    and the segmenter unit delta between decoded and raw.
    """

    def __init__(self, store, model, device):
        splits = store.split(seed=SEED)
        seen, self.rows = set(), []
        for i in splits["val"]:
            recording = store.index[i]["recording_id"]
            if recording in seen or store.index[i]["n_samples"] < SAMPLE_RATE:
                continue
            seen.add(recording)
            self.rows.append(store.index[i])
            if len(self.rows) >= EVAL_BOUTS:
                break
        self.raw = [normalise(store.audio(row)) for row in self.rows]
        self.device = device
        self.segmenter = Segmenter()
        self.codes = []
        with torch.no_grad():
            for clip in self.raw:
                batch = torch.from_numpy(clip)[None, None].to(device)
                encoded = model.encode(batch, bandwidth=BANDWIDTH)
                self.codes.append(encoded.audio_codes[0])
        self._embedder = None
        self._raw_emb = None

    def _units(self, audio):
        db, fps = self.segmenter.envelope(audio, SAMPLE_RATE)
        floor = np.percentile(db, self.segmenter.floor_pctl)
        return len(self.segmenter.bursts(db, fps, floor))

    def measure(self, model):
        was_training = model.decoder.training
        model.decoder.eval()
        decoded = []
        with torch.no_grad():
            for codes, raw in zip(self.codes, self.raw):
                # decode wants [n_chunks, B, K, T] — codec.py's first trap
                out = model.decode(codes.unsqueeze(0).to(self.device),
                                   [None]).audio_values
                decoded.append(out[0, 0].cpu().numpy()[: raw.size])
        if was_training:
            model.decoder.train()

        stft = float(np.mean([
            multi_res_stft_distance(r, d) for r, d in zip(self.raw, decoded)
        ]))
        unit_delta = float(np.mean([
            self._units(d) - self._units(r) for r, d in zip(self.raw, decoded)
        ]))

        if self._embedder is None:
            from crowgpt.embed import AstEmbedder
            self._embedder = AstEmbedder()
            self._raw_emb = self._embedder.embed(self.raw, SAMPLE_RATE)
        dec_emb = self._embedder.embed(decoded, SAMPLE_RATE)
        half = len(self._raw_emb) // 2
        fad = float(frechet_distance(self._raw_emb[:half], dec_emb[half:]))
        return {"ast_fad": round(fad, 3),
                "stft_logged": round(stft, 4),
                "unit_delta": round(unit_delta, 3)}


class DecoderFinetune:
    """One arm of the finetune, checkpointable, reporting through Run."""

    def __init__(self, arm, out_dir, device="cuda"):
        if arm not in ("spectral", "adversarial"):
            raise ValueError(f"unknown arm {arm!r}")
        from transformers import EncodecModel

        self.arm = arm
        self.device = device
        self.out = Path(out_dir) / arm
        self.out.mkdir(parents=True, exist_ok=True)

        self.model = EncodecModel.from_pretrained(MODEL_ID).to(device)
        for p in self.model.encoder.parameters():
            p.requires_grad_(False)
        for p in self.model.quantizer.parameters():
            p.requires_grad_(False)
        # cudnn refuses LSTM backward in eval mode; frozen halves stay eval.
        self.model.decoder.train()

        self.spectral = SpectralLoss().to(device)
        self.dec_opt = torch.optim.Adam(self.model.decoder.parameters(),
                                        lr=LR_DECODER, betas=BETAS)
        if arm == "adversarial":
            self.disc = MsStftDiscriminator().to(device)
            self.disc_opt = torch.optim.Adam(self.disc.parameters(),
                                             lr=LR_DISCRIMINATOR, betas=BETAS)
        self.step = 0
        self.history = []
        self.best_fad = float("inf")

    def _encode_embeddings(self, audio):
        with torch.no_grad():
            encoded = self.model.encode(audio, bandwidth=BANDWIDTH)
            return self.model.quantizer.decode(
                encoded.audio_codes[0].transpose(0, 1))

    def train_step(self, crops):
        audio = crops[:, None, :].to(self.device)
        embeddings = self._encode_embeddings(audio)

        self.dec_opt.zero_grad(set_to_none=True)
        fake = self.model.decoder(embeddings)
        width = min(fake.shape[-1], audio.shape[-1])
        fake, real = fake[:, 0, :width], audio[:, 0, :width]
        losses = {"spec": self.spectral(fake, real)}

        if self.arm == "adversarial":
            fake_out = self.disc(fake)
            real_out = self.disc(real)
            adv = fake.new_zeros(())
            feat = fake.new_zeros(())
            for (score, fake_feats), (_, real_feats) in zip(fake_out, real_out):
                adv = adv + F.relu(1 - score).mean()
                for ff, rf in zip(fake_feats, real_feats):
                    feat = feat + F.l1_loss(ff, rf.detach())
            losses["adv"] = adv / len(fake_out)
            losses["feat"] = feat / sum(len(f) for _, f in fake_out)
            total = (losses["spec"] + ADV_WEIGHT * losses["adv"]
                     + FEATURE_WEIGHT * losses["feat"])
        else:
            total = losses["spec"]

        total.backward()
        nn.utils.clip_grad_norm_(self.model.decoder.parameters(), GRAD_CLIP)
        self.dec_opt.step()

        if self.arm == "adversarial":
            self.disc_opt.zero_grad(set_to_none=True)
            detached = fake.detach()
            d_loss = fake.new_zeros(())
            for (fake_score, _), (real_score, _) in zip(
                self.disc(detached), self.disc(real)
            ):
                d_loss = (d_loss + F.relu(1 + fake_score).mean()
                          + F.relu(1 - real_score).mean())
            d_loss = d_loss / len(self.disc.scales)
            d_loss.backward()
            self.disc_opt.step()
            losses["disc"] = d_loss

        self.step += 1
        return {k: float(v.detach()) for k, v in losses.items()}

    def checkpoint(self, metrics):
        state = {"arm": self.arm, "step": self.step,
                 "decoder": self.model.decoder.state_dict(),
                 "dec_opt": self.dec_opt.state_dict()}
        if self.arm == "adversarial":
            state["disc"] = self.disc.state_dict()
            state["disc_opt"] = self.disc_opt.state_dict()
        torch.save(state, self.out / "latest.pt")
        if metrics["ast_fad"] < self.best_fad:
            self.best_fad = metrics["ast_fad"]
            torch.save(state, self.out / "best.pt")
        self.history.append({"step": self.step, **metrics})
        (self.out / "history.json").write_text(json.dumps(self.history, indent=2))

    def resume(self):
        latest = self.out / "latest.pt"
        if not latest.exists():
            return False
        state = torch.load(latest, map_location=self.device, weights_only=True)
        self.model.decoder.load_state_dict(state["decoder"])
        self.dec_opt.load_state_dict(state["dec_opt"])
        if self.arm == "adversarial" and "disc" in state:
            self.disc.load_state_dict(state["disc"])
            self.disc_opt.load_state_dict(state["disc_opt"])
        self.step = state["step"]
        history_file = self.out / "history.json"
        if history_file.exists():
            self.history = json.loads(history_file.read_text())
            self.best_fad = min((h["ast_fad"] for h in self.history),
                                default=float("inf"))
        return True


def train(arm, passes, data_dir, out_dir, smoke_steps=None):
    from crowgpt.train import require_device

    device = require_device()
    store = BoutStore(Path(data_dir) / "bouts")
    sampler = CropSampler(store)
    job = DecoderFinetune(arm, out_dir, device=device)
    resumed = job.resume()

    total_steps = smoke_steps or int(
        passes * sampler.corpus_seconds / (BATCH * CROP_SECONDS))
    eval_every = min(EVAL_EVERY, max(50, total_steps // 2)) if smoke_steps \
        else EVAL_EVERY

    run = Run(f"DECODER FINETUNE — {arm.upper()} ARM", ["baseline", "train"])
    try:
        with run.stage("baseline") as stage:
            stage.update(0, 1)
            evaluator = Evaluator(store, job.model, device)
            if resumed:
                run.note(f"resumed at step {job.step}, best FAD {job.best_fad}")
                baseline = job.history[0] if job.history else None
            else:
                baseline = {"step": 0, **evaluator.measure(job.model)}
                job.history.append(baseline)
            if baseline:
                run.note(f"frozen decoder on val: FAD {baseline['ast_fad']} · "
                         f"unit Δ {baseline['unit_delta']} · "
                         f"stft {baseline['stft_logged']} (logged, no vote)")
            stage.update(1, 1)

        with run.stage("train") as stage:
            recent = []
            started = time.time()
            start_step = job.step
            while job.step < total_steps:
                losses = job.train_step(sampler.batch())
                recent.append(losses)
                if job.step % UPDATE_EVERY == 0 or job.step == total_steps:
                    mean = {k: float(np.mean([r[k] for r in recent]))
                            for k in recent[0]}
                    recent = []
                    rate = (job.step - start_step) / max(time.time() - started, 1)
                    corpus_passes = job.step * BATCH * CROP_SECONDS / sampler.corpus_seconds
                    stage.update(job.step, total_steps, extra=(
                        f"pass {corpus_passes:.1f} · "
                        + " ".join(f"{k} {v:.3f}" for k, v in mean.items())
                        + f" · {rate:.1f} it/s"))
                if job.step % eval_every == 0 or job.step == total_steps:
                    metrics = evaluator.measure(job.model)
                    job.checkpoint(metrics)
                    run.note(f"step {job.step}: FAD {metrics['ast_fad']} "
                             f"(best {job.best_fad}) · unit Δ {metrics['unit_delta']} "
                             f"· stft {metrics['stft_logged']}")
        run.note(f"done: {job.step} steps, best val FAD {job.best_fad} "
                 f"(frozen baseline {job.history[0]['ast_fad']})")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    return job


def main():
    from crowgpt.gpu import claim

    claim()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", required=True, choices=("spectral", "adversarial"))
    parser.add_argument("--passes", type=float, default=20.0,
                        help="corpus passes to train for")
    parser.add_argument("--smoke", type=int, default=None,
                        help="cap total steps for a smoke run")
    parser.add_argument("--data", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[3]
    data = Path(args.data) if args.data else \
        Path(__import__("os").environ.get("DATA_DIR") or repo / "data") / "crowgpt"
    out = Path(args.out) if args.out else \
        Path(__file__).resolve().parents[2] / "results" / "decoder-finetune"
    train(args.arm, args.passes, data, out, smoke_steps=args.smoke)


if __name__ == "__main__":
    main()
