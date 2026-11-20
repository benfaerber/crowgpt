"""0099: Architecture & objective shootout on tokens-6s.

Stage 1 — Per-stage (prefix, stage 0..7, EOS) full validation breakdown on
          CrowGPT2, 0097 (60k), 0098 (60k token-budget), and 0096 (43.9M 60k).
Stage 2 — Frame-indexed RoPE + stage embeddings + RMSNorm/SwiGLU (17.34M, 60k).
Stage 3 — Dual-AR Temporal (75 Hz, L6) + Depth (K=8, L2) (17.34M, 60k).
Stage 4 — Winner pushed to 120k steps (cosine to 0.01) + coarse-weighted 60k arm.
Stage 5 — Full offline instrument suite (0067 structure, 0069 dust/pitch,
          0046 stage-0 churn, GPU+CPU latency) + sampling sweep (min_p, split-T,
          repeat_penalty) + diagnostic WAV clips.

Everything reports through `crowgpt.progress.Run` and checkpoints atomically so
interrupted arms resume cleanly.
"""

import argparse
import copy
import gc
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "crowgpt/src"))
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(REPO / "experiments/0086-can-tuned-training-improve-crowgpt2"))

import numpy as np
import soundfile as sf
import torch

from crowgpt.codec import CODEBOOK_SIZE, SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.dualar import DualARConfig, DualARCrowGPT, DualARSampler
from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.sliced import LegalSlices, summarise_stage_sums
from crowgpt.tokens import BoutStore, TokenDataset, Vocabulary
from crowgpt.train import BucketedBatcher, require_device
from lib.dustprobe import DUST_THRESHOLD, bursts_of, pitch_strength
from training import atomic_json, atomic_torch, fixed_panel, pack

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
TOKENS = DATA / "crowgpt/tokens-6s"
BOUTS = DATA / "crowgpt/bouts-6s"
OUTPUT = REPO / "crowgpt/results/shootout-0099"
RESULTS_JSON = HERE / "results.json"

TOKEN_BUDGET = 12300
PEAK_LR = 6e-4
WARMUP = 200
EVAL_EVERY = 2000
CHECKPOINT_EVERY = 10000
PANEL_SIZE = 256
COARSE_WEIGHTS = (1.8, 1.5, 1.25, 1.0, 0.85, 0.7, 0.55, 0.45)

REFERENCES = {
    "CrowGPT2 (30k, 18.7M)": REPO / "crowgpt/results/model-longctx/model.pt",
    "0097 plain (60k, 18.7M)": REPO / "crowgpt/results/control-0097/60k-lr-6e-4/step-60000.pt",
    "0098 budget (60k, 18.7M)": REPO / "crowgpt/results/trimmed-0098/budget-lr-6e-4/step-60000.pt",
    "0096 larger (60k, 43.9M)": REPO / "crowgpt/results/longer-0096/60k-lr-6e-4/step-60000.pt",
}


def cleanup():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def load_model_from_checkpoint(path, device="cuda"):
    """Load either CrowGPT (learned/frame_rope) or DualARCrowGPT from checkpoint."""
    state = torch.load(path, map_location="cpu", weights_only=False)
    manifest = state["manifest"]
    vocabulary = Vocabulary(
        manifest["n_codebooks"],
        manifest["species"],
        manifest.get("call_types", ()),
        manifest.get("channels", ()),
        n_unit_buckets=manifest.get("n_unit_buckets", 0),
    )
    cfg_dict = dict(state["config"])
    if cfg_dict.get("arch") == "dualar":
        cfg = DualARConfig(**{k: v for k, v in cfg_dict.items() if k != "arch"})
        model = DualARCrowGPT(cfg).to(device).eval()
        model.load_state_dict(state["model"])
        return model, vocabulary, state, True
    cfg = Config(**cfg_dict)
    model = CrowGPT(cfg).to(device).eval()
    model.load_state_dict(state["model"])
    return model, vocabulary, state, False


def load_sampler(path, device="cuda", decoder_state="finetuned"):
    state = torch.load(path, map_location="cpu", weights_only=False)
    is_dualar = state["config"].get("arch") == "dualar"
    del state
    if is_dualar:
        return DualARSampler(path, device=device, decoder_state=decoder_state)
    return Sampler(path, device=device, decoder_state=decoder_state)


@torch.no_grad()
def evaluate_per_stage(model, vocabulary, dataset, indices, device="cuda",
                       batch_size=8, is_dualar=False, slices=None, on_progress=None):
    """Exact token-weighted cross-entropy overall and per codebook stage."""
    was_training = model.training
    model.eval()
    sums = {"prefix": 0.0, "eos": 0.0, **{f"stage_{s}": 0.0 for s in range(vocabulary.n_codebooks)}}
    counts = {"prefix": 0, "eos": 0, **{f"stage_{s}": 0 for s in range(vocabulary.n_codebooks)}}
    try:
        if not is_dualar and slices is None:
            legal = LegalMask(vocabulary, model.config.block_size + 1, device)
            slices = LegalSlices(legal)
        for start in range(0, len(indices), batch_size):
            x, y = pack(dataset, indices[start : start + batch_size], device)
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
                if is_dualar:
                    b_sums, b_counts = model.per_stage_sums(x, y, vocabulary)
                else:
                    b_sums, b_counts = slices.per_stage_sums(model, x, y, vocabulary)
            for key in sums:
                sums[key] += b_sums[key]
                counts[key] += b_counts[key]
            if on_progress:
                on_progress(min(start + batch_size, len(indices)), len(indices))
    finally:
        model.train(was_training)
    return summarise_stage_sums(sums, counts, vocabulary.n_codebooks)


class FullStageValidator:
    """5,033 canonical American Crow validation bouts, scored per stage."""

    def __init__(self):
        self.dataset = TokenDataset(TOKENS, "val")
        self.indices = [
            i for i, r in enumerate(self.dataset.records)
            if r["species"] == "american-crow" and r.get("canonical", True)
        ]

    def score_checkpoint(self, path, on_progress=None):
        path = Path(path)
        model, vocab, state, is_dualar = load_model_from_checkpoint(path, "cuda")
        batch_size = 16 if is_dualar else 8
        metrics = evaluate_per_stage(
            model, vocab, self.dataset, self.indices, "cuda",
            batch_size=batch_size, is_dualar=is_dualar, on_progress=on_progress,
        )
        row = {
            "path": str(path.relative_to(REPO)),
            "arch": "dualar" if is_dualar else state["config"].get("pos_encoding", "learned"),
            "params": model.n_params(),
            "step": state["step"],
            "overall": round(metrics["overall"], 5),
            "coarse_0_2": round(metrics["coarse_0_2"], 5),
            "fine_5_7": round(metrics["fine_5_7"], 5),
            "per_stage": {k: (round(v, 5) if v is not None else None)
                          for k, v in metrics["per_stage"].items()},
            "total_tokens": metrics["total_tokens"],
            "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
        }
        del model, state
        cleanup()
        return row


class ArmTrainer:
    """Resumable token-budget trainer supporting both Frame-RoPE CrowGPT and Dual-AR."""

    def __init__(
        self,
        out_dir,
        arch,
        steps=60000,
        learning_rate=PEAK_LR,
        lr_floor=0.1,
        stage_weights=None,
        seed=0,
        token_budget=TOKEN_BUDGET,
        eval_every=EVAL_EVERY,
        checkpoint_every=CHECKPOINT_EVERY,
    ):
        self.out_dir = Path(out_dir)
        self.arch = arch
        self.steps = steps
        self.learning_rate = learning_rate
        self.warmup = WARMUP
        self.lr_floor = lr_floor
        self.stage_weights = tuple(stage_weights) if stage_weights is not None else None
        self.eval_every = eval_every
        self.checkpoint_every = checkpoint_every
        self.device = require_device()

        torch.manual_seed(seed)
        self.train_set = TokenDataset(TOKENS, "train")
        self.val_set = TokenDataset(TOKENS, "val")
        manifest = self.train_set.manifest
        self.vocabulary = Vocabulary(
            manifest["n_codebooks"],
            manifest["species"],
            manifest.get("call_types", ()),
            n_unit_buckets=manifest.get("n_unit_buckets", 0),
        )
        longest = max(r["length"] for r in self.train_set.records)
        block_size = int(min(4096, max(256, longest)))

        self.is_dualar = arch == "dualar"
        if self.is_dualar:
            self.config = DualARConfig(
                vocab_size=self.vocabulary.size,
                n_codebooks=manifest["n_codebooks"],
                block_size=block_size,
                n_layer=6,
                depth_layer=2,
                n_head=4,
                depth_head=4,
                n_embd=384,
                dropout=0.0,
                prefix_len=self.vocabulary.prefix_len,
                norm="rmsnorm",
                mlp="swiglu",
            )
            self.model = DualARCrowGPT(self.config).to(self.device)
            self.legal = None
            self.slices = None
        elif arch == "frame_rope":
            self.config = Config(
                vocab_size=self.vocabulary.size,
                n_codebooks=manifest["n_codebooks"],
                block_size=block_size,
                n_layer=8,
                n_head=4,
                n_embd=384,
                dropout=0.0,
                prefix_len=self.vocabulary.prefix_len,
                pos_encoding="frame_rope",
                norm="rmsnorm",
                mlp="swiglu",
            )
            self.model = CrowGPT(self.config).to(self.device)
            self.legal = LegalMask(self.vocabulary, block_size + 1, self.device)
            self.slices = LegalSlices(self.legal)
        else:
            raise ValueError(f"unknown arch {arch!r}")

        self.train_batcher = BucketedBatcher(
            self.train_set, 8, block_size, self.device, seed=seed,
            vocabulary=self.vocabulary, token_budget=token_budget,
        )
        self.panels = {
            "train": fixed_panel(self.train_set, PANEL_SIZE, 87),
            "val": fixed_panel(self.val_set, PANEL_SIZE, 86),
        }
        self.signature = {
            "arch": arch,
            "config": self.config.as_dict(),
            "steps": steps,
            "learning_rate": learning_rate,
            "lr_floor": lr_floor,
            "warmup": self.warmup,
            "token_budget": token_budget,
            "stage_weights": list(self.stage_weights) if self.stage_weights else None,
            "seed": seed,
        }

    def _lr(self, step):
        if step < self.warmup:
            return self.learning_rate * (step + 1) / self.warmup
        progress = (step - self.warmup) / max(1, self.steps - self.warmup)
        return self.lr_floor * self.learning_rate + (1 - self.lr_floor) * self.learning_rate * 0.5 * (
            1 + math.cos(math.pi * min(1.0, progress))
        )

    def _train_loss(self, x, y):
        with torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
            if self.is_dualar:
                return self.model.loss(x, y, self.vocabulary, stage_weights=self.stage_weights)
            return self.slices.loss(self.model, x, y, stage_weights=self.stage_weights)

    @torch.no_grad()
    def evaluate_panels(self):
        bs = 16 if self.is_dualar else 8
        tr = evaluate_per_stage(
            self.model, self.vocabulary, self.train_set, self.panels["train"],
            self.device, batch_size=bs, is_dualar=self.is_dualar, slices=self.slices,
        )
        va = evaluate_per_stage(
            self.model, self.vocabulary, self.val_set, self.panels["val"],
            self.device, batch_size=bs, is_dualar=self.is_dualar, slices=self.slices,
        )
        return tr, va

    def blob(self, step, val):
        return {
            "model": self.model.state_dict(),
            "config": self.config.as_dict(),
            "manifest": dict(self.train_set.manifest),
            "step": step,
            "val_loss": val,
        }

    def _save_resume(self, optimizer, step, best, history):
        state = dict(
            self.blob(step, history[-1]["val"] if history else None),
            optimizer=optimizer.state_dict(),
            best=best,
            history=history,
            signature=self.signature,
            torch_rng=torch.get_rng_state(),
            cuda_rng=torch.cuda.get_rng_state_all() if self.device == "cuda" else [],
            python_rng=random.getstate(),
            numpy_rng=np.random.get_state(),
            batch_rng=copy.deepcopy(self.train_batcher.rng.bit_generator.state),
        )
        atomic_torch(self.out_dir / "resume.pt", state)

    def run(self, on_step=None, on_eval=None):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        optimizer = self.model.optimiser(self.learning_rate, fused=(self.device == "cuda"))
        resume_path = self.out_dir / "resume.pt"
        history, best, start = [], float("inf"), 0

        if resume_path.exists():
            state = torch.load(resume_path, map_location="cpu", weights_only=False)
            if state["signature"] != self.signature:
                raise ValueError(f"Resume signature mismatch in {self.out_dir}")
            self.model.load_state_dict(state["model"])
            optimizer.load_state_dict(state["optimizer"])
            history, best, start = state["history"], state["best"], state["step"]
            torch.set_rng_state(state["torch_rng"])
            if self.device == "cuda":
                torch.cuda.set_rng_state_all(state["cuda_rng"])
            random.setstate(state["python_rng"])
            np.random.set_state(state["numpy_rng"])
            self.train_batcher.rng.bit_generator.state = state["batch_rng"]
            del state
            print(f"[{self.out_dir.name}] resumed from step {start}/{self.steps}", flush=True)
        else:
            atomic_json(self.out_dir / "recipe.json", self.signature)
            print(
                f"[{self.out_dir.name}] {self.arch} · {self.model.n_params():,} params · "
                f"steps {self.steps} · lr {self.learning_rate} -> floor {self.lr_floor} · "
                f"stage_weights={self.stage_weights}",
                flush=True,
            )

        if start >= self.steps:
            return {"best_val": best, "history": history, "step": start, "seconds": 0.0}

        started = time.monotonic()
        real_tokens = 0
        if on_step:
            on_step(start, self.steps, "starting")

        for step in range(start, self.steps):
            lr = self._lr(step)
            for group in optimizer.param_groups:
                group["lr"] = lr
            optimizer.zero_grad(set_to_none=True)
            x, y = self.train_batcher.batch()
            real_tokens += int((y >= 0).sum().item())
            loss = self._train_loss(x, y)
            if not torch.isfinite(loss):
                raise RuntimeError(f"{self.out_dir.name}: nonfinite loss at step {step + 1}")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()

            done = step + 1
            if on_step and done % 25 == 0:
                elapsed = max(time.monotonic() - started, 1e-3)
                tok_s = real_tokens / elapsed
                it_s = (done - start) / elapsed
                on_step(done, self.steps, f"{it_s:.1f} it/s · {tok_s/1e3:.1f}k tok/s")

            if done % self.eval_every == 0 or done == self.steps:
                tr, va = self.evaluate_panels()
                entry = {
                    "step": done,
                    "train": round(tr["overall"], 5),
                    "val": round(va["overall"], 5),
                    "gap": round(va["overall"] - tr["overall"], 5),
                    "val_coarse_0_2": round(va["coarse_0_2"], 5),
                    "val_fine_5_7": round(va["fine_5_7"], 5),
                    "lr": round(lr, 7),
                    "elapsed_s": round(time.monotonic() - started, 1),
                }
                history.append(entry)
                if va["overall"] < best:
                    best = va["overall"]
                    atomic_torch(self.out_dir / "model.pt", self.blob(done, va["overall"]))
                atomic_torch(self.out_dir / "last.pt", self.blob(done, va["overall"]))
                if done % self.checkpoint_every == 0 or done == self.steps:
                    atomic_torch(self.out_dir / f"step-{done:06d}.pt", self.blob(done, va["overall"]))
                atomic_json(self.out_dir / "history.json", {"best_val": best, "history": history})
                self._save_resume(optimizer, done, best, history)
                print(
                    f"  [{self.out_dir.name}] step {done:6d}: val {va['overall']:.4f} "
                    f"(coarse0-2 {va['coarse_0_2']:.4f} · fine5-7 {va['fine_5_7']:.4f} · "
                    f"gap {entry['gap']:+.4f}) {entry['elapsed_s']:.0f}s",
                    flush=True,
                )
                if on_eval:
                    on_eval(done, entry)

        elapsed = time.monotonic() - started
        return {"best_val": best, "history": history, "step": self.steps, "seconds": round(elapsed, 1)}


def clip_features(seg, audio, codes=None):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    bursts = seg.bursts(db, fps, np.percentile(db, seg.floor_pctl))
    strengths = [pitch_strength(b, SAMPLE_RATE) for b in bursts_of(seg, audio, SAMPLE_RATE)]
    half = len(strengths) // 2
    stage0_churn = None
    if codes is not None and codes.shape[1] > 1:
        stage0_churn = float(np.mean(codes[0, 1:] != codes[0, :-1]))
    return {
        "seconds": audio.size / SAMPLE_RATE,
        "units": len(bursts),
        "gaps": [(b[0] - a[1]) / fps for a, b in zip(bursts, bursts[1:])],
        "pitch_strength": float(np.mean(strengths)) if strengths else None,
        "crescendo": (
            float(np.mean(strengths[half:]) - np.mean(strengths[:half])) if half else None
        ),
        "stage0_churn": stage0_churn,
    }


def summarise_features(rows):
    gaps = [g for r in rows for g in r["gaps"]]
    strengths = [r["pitch_strength"] for r in rows if r["pitch_strength"] is not None]
    deltas = [r["crescendo"] for r in rows if r["crescendo"] is not None]
    churns = [r["stage0_churn"] for r in rows if r["stage0_churn"] is not None]
    return {
        "n": len(rows),
        "mean_seconds": round(float(np.mean([r["seconds"] for r in rows])), 3),
        "mean_units": round(float(np.mean([r["units"] for r in rows])), 3),
        "single_share": round(float(np.mean([r["units"] <= 1 for r in rows])), 3),
        "gaps_per_clip": round(len(gaps) / max(1, len(rows)), 3),
        "median_gap_s": round(float(np.median(gaps)), 3) if gaps else None,
        "mean_pitch_strength": round(float(np.mean(strengths)), 4) if strengths else None,
        "dust_rate": round(float(np.mean(np.array(strengths) <= DUST_THRESHOLD)), 4) if strengths else None,
        "mean_crescendo": round(float(np.mean(deltas)), 4) if deltas else None,
        "stage0_churn": round(float(np.mean(churns)), 4) if churns else None,
    }


def draw_instrument_set(sampler, count, seed_base, sampling_kwargs, stage, label,
                        save_dir=None, save_n=0):
    seg = Segmenter()
    rows = []
    attempts = 0
    if save_dir and save_n:
        Path(save_dir).mkdir(parents=True, exist_ok=True)
    for seed in range(seed_base, seed_base + count * 10):
        attempts += 1
        flat = sampler.tokens("american-crow", seed=seed, **sampling_kwargs)
        if flat.size == 0:
            continue
        codes = sampler.codec.unflatten(flat)
        audio = np.asarray(sampler.codec.decode(torch.from_numpy(codes))[0], dtype=np.float32)
        if not np.isfinite(audio).all():
            raise ValueError(f"Nonfinite audio seed {seed}")
        if audio.size / SAMPLE_RATE < MIN_GRADEABLE_SECONDS:
            continue
        normed = normalise(audio)
        row = clip_features(seg, normed, codes=codes) | {"seed": seed}
        if save_dir and len(rows) < save_n:
            fname = f"{label}-{len(rows):02d}.wav"
            sf.write(Path(save_dir) / fname, normed, SAMPLE_RATE, subtype="PCM_16")
            row["file"] = fname
        rows.append(row)
        stage.update(len(rows), count, extra=f"{label} ({attempts} tries)")
        if len(rows) == count:
            return {
                "summary": summarise_features(rows) | {"keep_rate": round(count / attempts, 3)},
                "attempts": attempts,
            }
    raise RuntimeError(f"{label}: only {len(rows)} gradeable clips in {attempts} tries")


def benchmark_latency(path, n_gpu=8, n_cpu=3):
    """Measure end-to-end token generation speed on GPU and CPU (seconds per bout & ms/frame)."""
    out = {}
    for dev, n in [("cuda", n_gpu), ("cpu", n_cpu)]:
        sampler = load_sampler(path, device=dev, decoder_state="finetuned")
        # Warmup 1 draw.
        sampler.tokens("american-crow", seed=1, temperature=1.1, top_k=200, max_frames=225)
        if dev == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        total_frames = 0
        for s in range(n):
            flat = sampler.tokens("american-crow", seed=500 + s, temperature=1.1,
                                  top_k=200, max_frames=225)
            total_frames += flat.size // sampler.vocabulary.n_codebooks
        if dev == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - t0
        out[dev] = {
            "bouts": n,
            "total_frames": int(total_frames),
            "sec_per_bout": round(elapsed / n, 3),
            "ms_per_frame": round(1000.0 * elapsed / max(1, total_frames), 2),
        }
        del sampler
        cleanup()
    return out


def real_reference_summary(n=200):
    """Real 6 s test bouts summary (same protocol as 0086, plus EnCodec stage-0 churn)."""
    from crowgpt.codec import Codec

    store = BoutStore(BOUTS)
    candidates = list(store.split(seed=0)["test"])
    np.random.default_rng(9900).shuffle(candidates)
    chosen, seen = [], set()
    for i in candidates:
        r = store.index[i]
        if r["species"] != "american-crow" or r["n_samples"] < SAMPLE_RATE:
            continue
        if r["group_key"] in seen:
            continue
        seen.add(r["group_key"])
        chosen.append(i)
        if len(chosen) == n:
            break
    seg = Segmenter()
    codec = Codec(bandwidth=6.0, device="cuda")
    rows = []
    for i in chosen:
        audio = normalise(store.audio(store.index[i]))
        codes = codec.encode(audio)[0].numpy()
        rows.append(clip_features(seg, audio, codes=codes))
    del codec
    cleanup()
    return summarise_features(rows)


def preflight():
    """Fast 25-step speed & VRAM check on both architectures before committing the night."""
    print("=== Preflight: Frame-RoPE vs Dual-AR (25 steps each) ===", flush=True)
    for arch in ("frame_rope", "dualar"):
        torch.cuda.reset_peak_memory_stats()
        trainer = ArmTrainer(OUTPUT / f"_preflight_{arch}", arch, steps=25, eval_every=25, checkpoint_every=25)
        t0 = time.monotonic()
        real_toks = 0
        opt = trainer.model.optimiser(PEAK_LR, fused=True)
        for _ in range(25):
            opt.zero_grad(set_to_none=True)
            x, y = trainer.train_batcher.batch()
            real_toks += int((y >= 0).sum().item())
            loss = trainer._train_loss(x, y)
            if not torch.isfinite(loss):
                raise RuntimeError(f"Nonfinite preflight loss for {arch}")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainer.model.parameters(), 1.0)
            opt.step()
        torch.cuda.synchronize()
        dt = time.monotonic() - t0
        peak = torch.cuda.max_memory_allocated() / 2**30
        print(
            f"  {arch:11s} | {trainer.model.n_params():,} params | "
            f"{25/dt:.1f} it/s | {real_toks/dt/1e3:.1f}k tok/s | "
            f"peak {peak:.2f} GiB | est 60k = {60000/(25/dt)/60:.1f} min",
            flush=True,
        )
        del trainer, opt
        cleanup()


def save_results(state):
    atomic_json(RESULTS_JSON, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--steps-60k", type=int, default=60000)
    parser.add_argument("--steps-120k", type=int, default=120000)
    parser.add_argument("--instrument-n", type=int, default=100)
    args = parser.parse_args()

    if require_device() != "cuda":
        raise RuntimeError("0099 requires CUDA")

    if args.preflight:
        preflight()
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(RESULTS_JSON.read_text()) if RESULTS_JSON.exists() else {
        "references": {},
        "arms": {},
        "full_validation": {},
        "instruments": {},
        "latency": {},
    }

    run = Run(
        "0099 architecture & objective shootout",
        [
            "baseline per-stage val",
            "frame-rope 60k",
            "dualar 60k",
            "60k full validation",
            "winner 120k",
            "coarse-weighted 60k",
            "final full validation",
            "instruments & sampling",
        ],
    )
    validator = FullStageValidator()

    # --- Stage 1: Baseline per-stage breakdown on references ---
    with run.stage("baseline per-stage val") as stage:
        ref_items = list(REFERENCES.items())
        for idx, (label, path) in enumerate(ref_items):
            if label in state["references"]:
                stage.update((idx + 1) * len(validator.indices),
                             len(ref_items) * len(validator.indices), extra=f"cached {label}")
                continue
            row = validator.score_checkpoint(
                path,
                on_progress=lambda d, t, i=idx, lb=label: stage.update(
                    i * len(validator.indices) + d, len(ref_items) * len(validator.indices), extra=lb
                ),
            )
            state["references"][label] = row
            save_results(state)
            run.note(
                f"{label}: overall {row['overall']:.4f} · coarse0-2 {row['coarse_0_2']:.4f} · "
                f"fine5-7 {row['fine_5_7']:.4f}"
            )
            print(f"[ref] {label}: overall={row['overall']:.4f} coarse={row['coarse_0_2']:.4f} "
                  f"fine={row['fine_5_7']:.4f}", flush=True)

    # --- Stage 2: Frame-RoPE + SwiGLU (60k) ---
    with run.stage("frame-rope 60k") as stage:
        tr = ArmTrainer(
            OUTPUT / "frame-rope-60k", "frame_rope",
            steps=args.steps_60k, learning_rate=PEAK_LR, lr_floor=0.1, seed=0,
        )
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"frame-rope step {s}: panel val {e['val']:.4f} (coarse {e['val_coarse_0_2']:.4f})"
            ),
        )
        state["arms"]["frame-rope-60k"] = res
        save_results(state)
        del tr
        cleanup()

    # --- Stage 3: Dual-AR Temporal+Depth (60k) ---
    with run.stage("dualar 60k") as stage:
        tr = ArmTrainer(
            OUTPUT / "dualar-60k", "dualar",
            steps=args.steps_60k, learning_rate=PEAK_LR, lr_floor=0.1, seed=0,
        )
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"dualar step {s}: panel val {e['val']:.4f} (coarse {e['val_coarse_0_2']:.4f})"
            ),
        )
        state["arms"]["dualar-60k"] = res
        save_results(state)
        del tr
        cleanup()

    # --- Stage 4: Full 5,033-bout validation of both 60k arms ---
    with run.stage("60k full validation") as stage:
        to_score = [
            ("frame-rope-60k", OUTPUT / "frame-rope-60k" / f"step-{args.steps_60k:06d}.pt"),
            ("dualar-60k", OUTPUT / "dualar-60k" / f"step-{args.steps_60k:06d}.pt"),
        ]
        for idx, (label, path) in enumerate(to_score):
            if label in state["full_validation"]:
                continue
            row = validator.score_checkpoint(
                path,
                on_progress=lambda d, t, i=idx, lb=label: stage.update(
                    i * len(validator.indices) + d, len(to_score) * len(validator.indices), extra=lb
                ),
            )
            state["full_validation"][label] = row
            save_results(state)
            run.note(
                f"FULL VAL {label}: overall {row['overall']:.4f} · coarse0-2 {row['coarse_0_2']:.4f} · "
                f"fine5-7 {row['fine_5_7']:.4f}"
            )
            print(f"[full val] {label}: overall={row['overall']:.4f} "
                  f"coarse={row['coarse_0_2']:.4f} fine={row['fine_5_7']:.4f}", flush=True)

        fr_val = state["full_validation"]["frame-rope-60k"]["overall"]
        da_val = state["full_validation"]["dualar-60k"]["overall"]
        winner_arch = "dualar" if da_val < fr_val else "frame_rope"
        state["winner_60k"] = {
            "arch": winner_arch,
            "frame_rope_overall": fr_val,
            "dualar_overall": da_val,
            "frame_rope_coarse": state["full_validation"]["frame-rope-60k"]["coarse_0_2"],
            "dualar_coarse": state["full_validation"]["dualar-60k"]["coarse_0_2"],
        }
        save_results(state)
        run.note(f"60k shootout winner: {winner_arch} (frame_rope={fr_val:.4f}, dualar={da_val:.4f})")

    winner_arch = state["winner_60k"]["arch"]

    # --- Stage 5: Push winner to 120k steps (cosine floor 0.01) ---
    with run.stage("winner 120k") as stage:
        tr = ArmTrainer(
            OUTPUT / f"{winner_arch}-120k", winner_arch,
            steps=args.steps_120k, learning_rate=PEAK_LR, lr_floor=0.01, seed=0,
        )
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"{winner_arch}-120k step {s}: panel val {e['val']:.4f} (coarse {e['val_coarse_0_2']:.4f})"
            ),
        )
        state["arms"][f"{winner_arch}-120k"] = res
        save_results(state)
        del tr
        cleanup()

    # --- Stage 6: Coarse-weighted 60k arm on winner architecture ---
    with run.stage("coarse-weighted 60k") as stage:
        tr = ArmTrainer(
            OUTPUT / f"{winner_arch}-coarse-60k", winner_arch,
            steps=args.steps_60k, learning_rate=PEAK_LR, lr_floor=0.05,
            stage_weights=COARSE_WEIGHTS, seed=0,
        )
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"{winner_arch}-coarse step {s}: panel val {e['val']:.4f} (coarse {e['val_coarse_0_2']:.4f})"
            ),
        )
        state["arms"][f"{winner_arch}-coarse-60k"] = res
        save_results(state)
        del tr
        cleanup()

    # --- Stage 7: Full validation of 120k + coarse-weighted checkpoints ---
    with run.stage("final full validation") as stage:
        final_paths = [
            (f"{winner_arch}-120k-step80k", OUTPUT / f"{winner_arch}-120k" / "step-080000.pt"),
            (f"{winner_arch}-120k-step100k", OUTPUT / f"{winner_arch}-120k" / "step-100000.pt"),
            (f"{winner_arch}-120k", OUTPUT / f"{winner_arch}-120k" / f"step-{args.steps_120k:06d}.pt"),
            (f"{winner_arch}-coarse-60k", OUTPUT / f"{winner_arch}-coarse-60k" / f"step-{args.steps_60k:06d}.pt"),
        ]
        final_paths = [(lb, p) for lb, p in final_paths if p.exists()]
        for idx, (label, path) in enumerate(final_paths):
            if label in state["full_validation"]:
                continue
            row = validator.score_checkpoint(
                path,
                on_progress=lambda d, t, i=idx, lb=label: stage.update(
                    i * len(validator.indices) + d, len(final_paths) * len(validator.indices), extra=lb
                ),
            )
            state["full_validation"][label] = row
            save_results(state)
            run.note(
                f"FULL VAL {label}: overall {row['overall']:.4f} · coarse0-2 {row['coarse_0_2']:.4f} · "
                f"fine5-7 {row['fine_5_7']:.4f}"
            )
            print(f"[full val] {label}: overall={row['overall']:.4f} "
                  f"coarse={row['coarse_0_2']:.4f} fine={row['fine_5_7']:.4f}", flush=True)

    # --- Stage 8: Full offline instrument suite + sampling sweep + latency ---
    with run.stage("instruments & sampling") as stage:
        if "real" not in state["instruments"]:
            state["instruments"]["real"] = real_reference_summary(200)
            save_results(state)

        clip_dir = OUTPUT / "clips"
        winner_120k_path = OUTPUT / f"{winner_arch}-120k" / f"step-{args.steps_120k:06d}.pt"
        coarse_60k_path = OUTPUT / f"{winner_arch}-coarse-60k" / f"step-{args.steps_60k:06d}.pt"
        frame_rope_path = OUTPUT / "frame-rope-60k" / f"step-{args.steps_60k:06d}.pt"
        dualar_path = OUTPUT / "dualar-60k" / f"step-{args.steps_60k:06d}.pt"

        default_s = dict(temperature=1.1, top_k=200, max_frames=460)
        sweep_specs = [
            ("crowgpt2_default", REFERENCES["CrowGPT2 (30k, 18.7M)"], default_s, 12),
            ("0097_60k_default", REFERENCES["0097 plain (60k, 18.7M)"], default_s, 12),
            ("frame_rope_60k_default", frame_rope_path, default_s, 12),
            ("dualar_60k_default", dualar_path, default_s, 12),
            (f"{winner_arch}_120k_default", winner_120k_path, default_s, 12),
            (f"{winner_arch}_120k_minp03", winner_120k_path,
             dict(temperature=1.05, top_k=0, min_p=0.03, max_frames=460), 12),
            (f"{winner_arch}_120k_splitT", winner_120k_path,
             dict(temperature=1.0, top_k=0, min_p=0.03,
                  stage_temperatures=(1.1, 1.1, 1.05, 1.0, 0.95, 0.95, 0.9, 0.9),
                  max_frames=460), 12),
            (f"{winner_arch}_120k_rep105", winner_120k_path,
             dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460), 12),
            (f"{winner_arch}_coarse_60k_default", coarse_60k_path, default_s, 12),
        ]

        for label, ckpt, skwargs, save_n in sweep_specs:
            if label in state["instruments"]:
                continue
            sampler = load_sampler(ckpt, device="cuda", decoder_state="finetuned")
            res = draw_instrument_set(
                sampler, args.instrument_n, 99000, skwargs, stage, label,
                save_dir=clip_dir / label, save_n=save_n,
            )
            state["instruments"][label] = res["summary"]
            save_results(state)
            run.note(
                f"instrument {label}: units={res['summary']['mean_units']} "
                f"dust={res['summary']['dust_rate']} pitch={res['summary']['mean_pitch_strength']} "
                f"churn={res['summary']['stage0_churn']}"
            )
            del sampler
            cleanup()

        # Latency comparison: CrowGPT2 vs Frame-RoPE vs Dual-AR on GPU and CPU.
        lat_specs = [
            ("crowgpt2", REFERENCES["CrowGPT2 (30k, 18.7M)"]),
            ("frame_rope", frame_rope_path),
            ("dualar", dualar_path),
        ]
        for label, ckpt in lat_specs:
            if label in state["latency"]:
                continue
            state["latency"][label] = benchmark_latency(ckpt)
            save_results(state)
            run.note(
                f"latency {label}: GPU {state['latency'][label]['cuda']['ms_per_frame']} ms/f · "
                f"CPU {state['latency'][label]['cpu']['ms_per_frame']} ms/f"
            )

    run.note("0099 complete. All checkpoints, metrics, and diagnostic WAVs saved.")
    print("=== 0099 COMPLETE ===", flush=True)


if __name__ == "__main__":
    main()
