"""0101: Recording-quality conditioning + Classifier-Free Guidance on Dual-AR 17M.

0100's Dual-AR 17M @ 240k reached 4.5308 full American Crow val CE (−0.262 below
CrowGPT2), and Ben's labelled audition called it the best model while pointing
out the remaining spread: "some audio clips sound really good like the first one
and others have lower quality."

Why: `tokens-6s` mixes crisp close-mic recordings with distant, hissy archive
mics across ~20,000 recordings, with no recording-quality token. Without one,
every draw rolls the dice across the corpus's quality distribution.

Method (zero re-tokenization, zero BirdNET circularity):
  1. Score every recording in `bouts-6s` purely acoustically (median across up
     to 6 bouts per recording):
       - snr_db: 95th − 20th percentile of the segmenter's dB envelope
       - quiet_flatness: spectral flatness of quiet frames (below floor + 12 dB)
       - burst_pitch: mean autocorrelation pitch strength across detected bursts
     Standardise using ONLY American Crow *train* recordings (zero val/test
     leakage) into a composite score, then bin into 5 equal quantiles:
       q0_noisy, q1_low, q2_mid, q3_clean, q4_crisp
     plus a dedicated null token `q_unknown` (never colliding with q0).
  2. Splice the quality token into the prefix at batch time
     ([species, quality_tier, unit_bucket, duration], prefix_len=4) with
     p_drop = 0.15 CFG dropout -> `q_unknown` during training.
  3. Train Dual-AR 17M (d384, L6 temporal + L2 depth, matched to 0100's 240k
     schedule, ~80 min).
  4. Full 5,033-bout per-stage validation scored BOTH unconditionally
     (`q_unknown`, apples-to-apples vs 0100's 4.5308) AND conditionally (true
     recording tier, measuring the information content of quality conditioning).
  5. Offline instrument sweep across quality tiers (q0_noisy vs q2_mid vs
     q4_crisp) and CFG scales (w = 1.0, 1.3, 1.6, 2.0) on q4_crisp, measuring
     SNR, quiet-frame flatness, pitch strength, dust rate, structure, and
     stage-0 churn + 0015 memorisation check.
  6. Build a labelled diagnostic comparison page at
     `crowgpt/results/quality-0101/compare.html` (Real, CrowGPT2, 0100 17M 240k,
     0101 q4_crisp w=1.0, and 0101 q4_crisp best CFG).
"""

import copy
import gc
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "crowgpt/src"))
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(REPO / "experiments/0086-can-tuned-training-improve-crowgpt2"))
sys.path.insert(0, str(REPO / "experiments/0099-architecture-and-objective-shootout"))

import numpy as np
import soundfile as sf
import torch
from scipy.signal import stft

import run as exp99
from crowgpt.codec import CODEBOOK_SIZE, SAMPLE_RATE, normalise
from crowgpt.demo import ComparePage, MIN_GRADEABLE_SECONDS
from crowgpt.dualar import DualARConfig, DualARCrowGPT, DualARSampler
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.sliced import summarise_stage_sums
from crowgpt.tokens import BoutStore, TokenDataset, Vocabulary
from crowgpt.train import BucketedBatcher, require_device
from lib.dustprobe import DUST_THRESHOLD, bursts_of, pitch_strength
from training import atomic_json, atomic_torch, fixed_panel

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
TOKENS = DATA / "crowgpt/tokens-6s"
BOUTS = DATA / "crowgpt/bouts-6s"
OUTPUT = REPO / "crowgpt/results/quality-0101"
QUALITY_JSON = OUTPUT / "recording_quality.json"
RESULTS_JSON = HERE / "results.json"

TIERS = ("q0_noisy", "q1_low", "q2_mid", "q3_clean", "q4_crisp", "q_unknown")
UNKNOWN = "q_unknown"
CFG_DROPOUT = 0.15


def acoustic_bout_metrics(seg, audio):
    """Purely acoustic quality features on one normalised 24 kHz bout (no BirdNET)."""
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    if db.size < 4:
        return None
    snr_db = float(np.percentile(db, 95) - np.percentile(db, 20))
    floor = float(np.percentile(db, seg.floor_pctl))

    # Quiet-frame spectral flatness in 300..8000 Hz (0051's low-hiss predictor).
    freqs, _, z = stft(audio, fs=SAMPLE_RATE, nperseg=512, noverlap=256)
    power = np.abs(z) ** 2
    band = (freqs >= 300.0) & (freqs <= 8000.0)
    power = power[band]
    n_frames = min(power.shape[1], db.size)
    power = power[:, :n_frames]
    quiet = db[:n_frames] <= floor + seg.burst_db
    if quiet.sum() < 4:
        quiet = db[:n_frames] <= np.median(db[:n_frames])
    q_spec = np.maximum(power[:, quiet].mean(axis=1), 1e-12)
    flatness = float(np.exp(np.mean(np.log(q_spec))) / np.mean(q_spec))

    strengths = [pitch_strength(b, SAMPLE_RATE) for b in bursts_of(seg, audio, SAMPLE_RATE)]
    pitch = float(np.mean(strengths)) if strengths else 0.0
    return snr_db, flatness, pitch


def compute_recording_quality(stage, per_recording=6):
    """Score every recording in bouts-6s and assign q0..q4 using AC-train quantiles."""
    if QUALITY_JSON.exists():
        data = json.loads(QUALITY_JSON.read_text())
        stage.update(1, 1, extra=f"cached {len(data['mapping'])} recordings")
        return data

    store = BoutStore(BOUTS)
    train_ds = TokenDataset(TOKENS, "train")
    ac_train_rids = {
        r["recording_id"] for r in train_ds.records
        if r["species"] == "american-crow" and r.get("canonical", True)
    }

    by_rid = defaultdict(list)
    for row in store.index:
        rid = row["recording_id"]
        if len(by_rid[rid]) < per_recording:
            by_rid[rid].append(row)

    seg = Segmenter()
    raw = {}
    rids = sorted(by_rid)
    for idx, rid in enumerate(rids, 1):
        vals = []
        for row in by_rid[rid]:
            audio = normalise(store.audio(row))
            m = acoustic_bout_metrics(seg, audio)
            if m is not None:
                vals.append(m)
        if vals:
            arr = np.asarray(vals, dtype=np.float64)
            raw[rid] = {
                "snr_db": float(np.median(arr[:, 0])),
                "quiet_flatness": float(np.median(arr[:, 1])),
                "pitch_strength": float(np.median(arr[:, 2])),
            }
        if idx % 250 == 0 or idx == len(rids):
            stage.update(idx, len(rids), extra=f"{idx}/{len(rids)} recordings")

    # Fit standardisation & quantile edges ONLY on American Crow train recordings.
    fit_rids = [rid for rid in rids if rid in ac_train_rids and rid in raw]
    snr_v = np.array([raw[r]["snr_db"] for r in fit_rids])
    flt_v = np.array([math.log(max(raw[r]["quiet_flatness"], 1e-6)) for r in fit_rids])
    pit_v = np.array([raw[r]["pitch_strength"] for r in fit_rids])

    stats = {
        "snr_mean": float(snr_v.mean()), "snr_std": float(snr_v.std() + 1e-8),
        "logflt_mean": float(flt_v.mean()), "logflt_std": float(flt_v.std() + 1e-8),
        "pit_mean": float(pit_v.mean()), "pit_std": float(pit_v.std() + 1e-8),
    }

    def score_of(entry):
        z_snr = np.clip((entry["snr_db"] - stats["snr_mean"]) / stats["snr_std"], -3.0, 3.0)
        z_flt = np.clip(
            (math.log(max(entry["quiet_flatness"], 1e-6)) - stats["logflt_mean"]) / stats["logflt_std"],
            -3.0, 3.0,
        )
        z_pit = np.clip((entry["pitch_strength"] - stats["pit_mean"]) / stats["pit_std"], -3.0, 3.0)
        # High SNR + low quiet-frame flatness + high burst pitch strength = crisp recording.
        return float((z_snr - z_flt + z_pit) / 3.0)

    train_scores = np.array([score_of(raw[r]) for r in fit_rids])
    edges = [float(np.quantile(train_scores, q)) for q in (0.2, 0.4, 0.6, 0.8)]
    tier_names = TIERS[:5]

    mapping = {}
    tier_stats = defaultdict(lambda: {"n": 0, "snr": [], "flat": [], "pitch": []})
    for rid, entry in raw.items():
        sc = score_of(entry)
        tier = tier_names[int(np.searchsorted(edges, sc))]
        mapping[rid] = tier
        if rid in ac_train_rids:
            ts = tier_stats[tier]
            ts["n"] += 1
            ts["snr"].append(entry["snr_db"])
            ts["flat"].append(entry["quiet_flatness"])
            ts["pitch"].append(entry["pitch_strength"])

    summary = {
        t: {
            "ac_train_recordings": tier_stats[t]["n"],
            "median_snr_db": round(float(np.median(tier_stats[t]["snr"])), 2),
            "median_quiet_flatness": round(float(np.median(tier_stats[t]["flat"])), 4),
            "median_pitch_strength": round(float(np.median(tier_stats[t]["pitch"])), 4),
        }
        for t in tier_names
    }
    data = {
        "tiers": list(TIERS),
        "unknown": UNKNOWN,
        "edges": edges,
        "stats": stats,
        "ac_train_summary": summary,
        "mapping": mapping,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    atomic_json(QUALITY_JSON, data)
    return data


class QualityAdapter:
    """Drop-in `channels` object for Batcher with optional CFG dropout."""

    def __init__(self, mapping, dropout=0.0, seed=0):
        self.names = list(TIERS)
        self.mapping = mapping
        self.dropout = dropout
        self.rng = np.random.default_rng(seed)

    def assign(self, recording_id):
        if self.dropout > 0.0 and self.rng.random() < self.dropout:
            return UNKNOWN
        return self.mapping.get(recording_id, UNKNOWN)


def splice_quality_sequence(stored, tier, vocabulary, old_unit_base):
    """Splice quality token at position 1 and remap unit token to new unit_base.

    `tokens-6s` on disk was written with channels=() so its unit tokens sit at
    `old_unit_base = duration_base + n_buckets`. Adding channels shifts
    `vocabulary.unit_base` up by `len(channels)`, so slot 1 of `stored` (the
    unit bucket) must be shifted to match before inserting the channel token.
    """
    out = np.empty(stored.size + 1, dtype=stored.dtype)
    out[0] = stored[0]
    out[1] = vocabulary.channel_token(tier)
    out[2] = stored[1] - old_unit_base + vocabulary.unit_base
    out[3:] = stored[2:]
    return out


class QualityBucketedBatcher(BucketedBatcher):
    """BucketedBatcher that remaps disk unit tokens when splicing quality channels."""

    def __init__(self, *args, old_unit_base, **kwargs):
        super().__init__(*args, **kwargs)
        self.old_unit_base = old_unit_base

    def sequence(self, i):
        stored = self.dataset.sequence(i)
        tier = self.channels.assign(self.dataset.records[i]["recording_id"])
        return splice_quality_sequence(stored, tier, self.vocabulary, self.old_unit_base)


def pack_with_quality(dataset, indices, vocabulary, mapping, device, force_tier=None):
    """Pack sequences with spliced quality token at position 1 (after species)."""
    old_unit_base = dataset.manifest["duration_base"] + dataset.manifest["n_buckets"]
    seqs = []
    for i in indices:
        stored = dataset.sequence(int(i))
        tier = force_tier if force_tier is not None else mapping.get(
            dataset.records[int(i)]["recording_id"], UNKNOWN
        )
        seqs.append(splice_quality_sequence(stored, tier, vocabulary, old_unit_base))
    n = max(map(len, seqs)) - 1
    x = np.zeros((len(seqs), n), dtype=np.int64)
    y = np.full((len(seqs), n), -1, dtype=np.int64)
    for j, s in enumerate(seqs):
        x[j, : len(s) - 1] = s[:-1]
        y[j, : len(s) - 1] = s[1:]
    return torch.from_numpy(x).to(device), torch.from_numpy(y).to(device)


@torch.no_grad()
def eval_quality_per_stage(model, vocabulary, dataset, indices, mapping, device="cuda",
                           batch_size=16, force_tier=None, on_progress=None):
    """Exact unweighted NLL/token on codec + prefix + EOS; also reports codec-only NLL
    so conditional vs unconditioned models compare cleanly even with prefix_len=4 vs 3."""
    was_training = model.training
    model.eval()
    sums = {"prefix": 0.0, "eos": 0.0, **{f"stage_{s}": 0.0 for s in range(vocabulary.n_codebooks)}}
    counts = {"prefix": 0, "eos": 0, **{f"stage_{s}": 0 for s in range(vocabulary.n_codebooks)}}
    try:
        for start in range(0, len(indices), batch_size):
            x, y = pack_with_quality(
                dataset, indices[start : start + batch_size], vocabulary, mapping, device,
                force_tier=force_tier,
            )
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
                b_sums, b_counts = model.per_stage_sums(x, y, vocabulary)
            for key in sums:
                sums[key] += b_sums[key]
                counts[key] += b_counts[key]
            if on_progress:
                on_progress(min(start + batch_size, len(indices)), len(indices))
    finally:
        model.train(was_training)
    out = summarise_stage_sums(sums, counts, vocabulary.n_codebooks)
    codec_loss = sum(sums[f"stage_{s}"] for s in range(vocabulary.n_codebooks)) + sums["eos"]
    codec_n = sum(counts[f"stage_{s}"] for s in range(vocabulary.n_codebooks)) + counts["eos"]
    out["codec_plus_eos"] = codec_loss / max(1, codec_n)
    return out


class QualityDualARTrainer:
    """Resumable Dual-AR trainer with spliced quality tier + CFG dropout."""

    def __init__(self, out_dir, mapping, steps=240000, learning_rate=6e-4, lr_floor=0.01,
                 cfg_dropout=CFG_DROPOUT, seed=0, token_budget=12300,
                 eval_every=4000, checkpoint_every=40000):
        self.out_dir = Path(out_dir)
        self.mapping = mapping
        self.steps = steps
        self.learning_rate = learning_rate
        self.warmup = 400
        self.lr_floor = lr_floor
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
            channels=TIERS,
            n_unit_buckets=manifest.get("n_unit_buckets", 0),
        )
        longest = max(r["length"] for r in self.train_set.records) + 1
        block_size = int(min(4096, max(256, longest)))
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
        self.channels = QualityAdapter(mapping, dropout=cfg_dropout, seed=seed + 101)
        old_unit_base = manifest["duration_base"] + manifest["n_buckets"]
        self.train_batcher = QualityBucketedBatcher(
            self.train_set, 8, block_size, self.device, seed=seed,
            vocabulary=self.vocabulary, channels=self.channels, token_budget=token_budget,
            old_unit_base=old_unit_base,
        )
        self.panels = {
            "train": fixed_panel(self.train_set, 256, 87),
            "val": fixed_panel(self.val_set, 256, 86),
        }
        self.signature = {
            "arch": "dualar-quality-cfg",
            "config": self.config.as_dict(),
            "steps": steps,
            "learning_rate": learning_rate,
            "lr_floor": lr_floor,
            "cfg_dropout": cfg_dropout,
            "tiers": list(TIERS),
            "token_budget": token_budget,
            "seed": seed,
        }

    def _lr(self, step):
        if step < self.warmup:
            return self.learning_rate * (step + 1) / self.warmup
        progress = (step - self.warmup) / max(1, self.steps - self.warmup)
        return self.lr_floor * self.learning_rate + (1 - self.lr_floor) * self.learning_rate * 0.5 * (
            1 + math.cos(math.pi * min(1.0, progress))
        )

    def blob(self, step, val):
        manifest = dict(self.train_set.manifest)
        manifest["channels"] = list(TIERS)
        manifest["vocab_size"] = self.vocabulary.size
        manifest["prefix_len"] = self.vocabulary.prefix_len
        return {
            "model": self.model.state_dict(),
            "config": self.config.as_dict(),
            "manifest": manifest,
            "step": step,
            "val_loss": val,
        }

    def _save_resume(self, optimizer, step, best, history):
        state = dict(
            self.blob(step, history[-1]["val_cond"] if history else None),
            optimizer=optimizer.state_dict(),
            best=best,
            history=history,
            signature=self.signature,
            torch_rng=torch.get_rng_state(),
            cuda_rng=torch.cuda.get_rng_state_all(),
            python_rng=random.getstate(),
            numpy_rng=np.random.get_state(),
            batch_rng=copy.deepcopy(self.train_batcher.rng.bit_generator.state),
            chan_rng=copy.deepcopy(self.channels.rng.bit_generator.state),
        )
        atomic_torch(self.out_dir / "resume.pt", state)

    def run(self, on_step=None, on_eval=None):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        optimizer = self.model.optimiser(self.learning_rate, fused=True)
        resume_path = self.out_dir / "resume.pt"
        history, best, start = [], float("inf"), 0

        if resume_path.exists():
            state = torch.load(resume_path, map_location="cpu", weights_only=False)
            if state["signature"] != self.signature:
                raise ValueError("Resume signature mismatch")
            self.model.load_state_dict(state["model"])
            optimizer.load_state_dict(state["optimizer"])
            history, best, start = state["history"], state["best"], state["step"]
            torch.set_rng_state(state["torch_rng"])
            torch.cuda.set_rng_state_all(state["cuda_rng"])
            random.setstate(state["python_rng"])
            np.random.set_state(state["numpy_rng"])
            self.train_batcher.rng.bit_generator.state = state["batch_rng"]
            self.channels.rng.bit_generator.state = state["chan_rng"]
            del state
        else:
            atomic_json(self.out_dir / "recipe.json", self.signature)
            print(
                f"[dualar-quality-240k] {self.model.n_params():,} params · "
                f"prefix_len={self.vocabulary.prefix_len} · cfg_drop={self.channels.dropout}",
                flush=True,
            )

        if start >= self.steps:
            return {"best_val": best, "history": history, "step": start, "seconds": 0.0}

        started = time.monotonic()
        real_tokens = 0
        for step in range(start, self.steps):
            lr = self._lr(step)
            for group in optimizer.param_groups:
                group["lr"] = lr
            optimizer.zero_grad(set_to_none=True)
            x, y = self.train_batcher.batch()
            real_tokens += int((y >= 0).sum().item())
            with torch.autocast(self.device, dtype=torch.bfloat16):
                loss = self.model.loss(x, y, self.vocabulary)
            if not torch.isfinite(loss):
                raise RuntimeError(f"Nonfinite loss at step {step + 1}")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()

            done = step + 1
            if on_step and done % 25 == 0:
                elapsed = max(time.monotonic() - started, 1e-3)
                on_step(done, self.steps, f"{(done - start)/elapsed:.1f} it/s · {real_tokens/elapsed/1e3:.1f}k tok/s")

            if done % self.eval_every == 0 or done == self.steps:
                tr_c = eval_quality_per_stage(
                    self.model, self.vocabulary, self.train_set, self.panels["train"],
                    self.mapping, self.device,
                )
                va_c = eval_quality_per_stage(
                    self.model, self.vocabulary, self.val_set, self.panels["val"],
                    self.mapping, self.device,
                )
                va_u = eval_quality_per_stage(
                    self.model, self.vocabulary, self.val_set, self.panels["val"],
                    self.mapping, self.device, force_tier=UNKNOWN,
                )
                entry = {
                    "step": done,
                    "train_cond": round(tr_c["codec_plus_eos"], 5),
                    "val_cond": round(va_c["codec_plus_eos"], 5),
                    "val_uncond": round(va_u["codec_plus_eos"], 5),
                    "cond_gain": round(va_u["codec_plus_eos"] - va_c["codec_plus_eos"], 5),
                    "val_coarse_0_2": round(va_c["coarse_0_2"], 5),
                    "gap": round(va_c["codec_plus_eos"] - tr_c["codec_plus_eos"], 5),
                    "lr": round(lr, 7),
                    "elapsed_s": round(time.monotonic() - started, 1),
                }
                history.append(entry)
                if va_c["codec_plus_eos"] < best:
                    best = va_c["codec_plus_eos"]
                    atomic_torch(self.out_dir / "model.pt", self.blob(done, best))
                atomic_torch(self.out_dir / "last.pt", self.blob(done, va_c["codec_plus_eos"]))
                if done % self.checkpoint_every == 0 or done == self.steps:
                    atomic_torch(self.out_dir / f"step-{done:06d}.pt", self.blob(done, va_c["codec_plus_eos"]))
                atomic_json(self.out_dir / "history.json", {"best_val": best, "history": history})
                self._save_resume(optimizer, done, best, history)
                print(
                    f"  [0101] step {done:6d}: cond {entry['val_cond']:.4f} · "
                    f"uncond {entry['val_uncond']:.4f} (Δ {entry['cond_gain']:+.4f}) · "
                    f"coarse {entry['val_coarse_0_2']:.4f} · gap {entry['gap']:+.4f} · "
                    f"{entry['elapsed_s']:.0f}s",
                    flush=True,
                )
                if on_eval:
                    on_eval(done, entry)

        return {"best_val": best, "history": history, "step": self.steps,
                "seconds": round(time.monotonic() - started, 1)}


def draw_quality_instruments(sampler, count, seed_base, sampling_kwargs, stage, label,
                             save_dir=None, save_n=12):
    """Measure standard instruments PLUS SNR & quiet-frame flatness (the quality axes)."""
    seg = Segmenter()
    rows, snrs, flats = [], [], []
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
        row = exp99.clip_features(seg, normed, codes=codes) | {"seed": seed}
        qm = acoustic_bout_metrics(seg, normed)
        if qm is not None:
            snrs.append(qm[0])
            flats.append(qm[1])
        if save_dir and len(rows) < save_n:
            sf.write(Path(save_dir) / f"{label}-{len(rows):02d}.wav", normed, SAMPLE_RATE, subtype="PCM_16")
        rows.append(row)
        stage.update(len(rows), count, extra=f"{label} ({attempts} tries)")
        if len(rows) == count:
            summary = exp99.summarise_features(rows) | {
                "keep_rate": round(count / attempts, 3),
                "median_snr_db": round(float(np.median(snrs)), 2) if snrs else None,
                "median_quiet_flatness": round(float(np.median(flats)), 4) if flats else None,
                "p25_pitch_strength": round(
                    float(np.percentile([r["pitch_strength"] for r in rows if r["pitch_strength"] is not None], 25)), 4
                ),
            }
            return summary
    raise RuntimeError(f"{label}: only {len(rows)} gradeable clips in {attempts} tries")


def build_compare_page(ckpt_path, best_cfg_label, best_cfg_kwargs, out_html):
    """Labelled diagnostic comparison page: Real, CrowGPT2, 0100 17M 240k, 0101 q4 w=1.0, 0101 q4 CFG."""
    store = BoutStore(BOUTS)
    rng = np.random.default_rng(10142)
    test_ac = [i for i in store.split(seed=0)["test"]
               if store.index[i]["species"] == "american-crow"
               and store.index[i]["n_samples"] >= 2 * SAMPLE_RATE]
    rng.shuffle(test_ac)
    reals = [normalise(store.audio(store.index[i])) for i in test_ac[:8]]

    arms_spec = [
        ("CrowGPT2 (30k)", exp99.REFERENCES["CrowGPT2 (30k, 18.7M)"],
         dict(temperature=1.1, top_k=200, max_frames=460)),
        ("0100 Dual-AR 240k (uncond)",
         REPO / "crowgpt/results/scaling-0100/dualar-17M-240k/step-240000.pt",
         dict(temperature=1.1, top_k=200, max_frames=460)),
        ("0101 Dual-AR q4_crisp (w=1.0)", ckpt_path,
         dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp", guidance_scale=1.0)),
        (f"0101 Dual-AR q4_crisp ({best_cfg_label})", ckpt_path, best_cfg_kwargs),
    ]
    drawn = {}
    for name, ckpt, skw in arms_spec:
        sampler = exp99.load_sampler(ckpt, device="cuda", decoder_state="finetuned")
        clips = []
        for s in range(10100, 10250):
            audio = np.asarray(sampler.audio("american-crow", seed=s, **skw), dtype=np.float32)
            if audio.size >= 2 * SAMPLE_RATE:
                clips.append(normalise(audio))
            if len(clips) == 8:
                break
        drawn[name] = clips
        del sampler
        exp99.cleanup()

    rows = []
    for idx in range(8):
        entries = [("Real (held-out)", "test split", reals[idx], None)]
        for name, _, _ in arms_spec:
            entries.append((name, "finetuned decoder", drawn[name][idx], None))
        rows.append({"species": f"american-crow #{idx + 1}", "arms": entries})

    facts = {
        "Experiment": "0101 Recording-quality conditioning + CFG on Dual-AR 17M",
        "Tiers": "q0_noisy .. q4_crisp + q_unknown (15% CFG dropout)",
        "Best CFG arm": best_cfg_label,
        "Decoder": "0063 adversarial finetune",
        "Note": "Labelled diagnostic only — not a blinded sitting",
    }
    ComparePage(rows, facts).write(out_html)


def save_results(state):
    atomic_json(RESULTS_JSON, state)


def main():
    if require_device() != "cuda":
        raise RuntimeError("0101 requires CUDA")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(RESULTS_JSON.read_text()) if RESULTS_JSON.exists() else {
        "quality_tiers": {},
        "training": {},
        "full_validation": {},
        "instruments": {},
        "memorisation": {},
    }

    run = Run(
        "0101 quality-conditioned Dual-AR + CFG",
        [
            "score recording quality",
            "train dualar-quality 240k",
            "full validation",
            "tier & CFG sweep",
            "memorisation & compare page",
        ],
    )

    with run.stage("score recording quality") as stage:
        qdata = compute_recording_quality(stage)
        state["quality_tiers"] = {
            "edges": qdata["edges"],
            "ac_train_summary": qdata["ac_train_summary"],
            "n_recordings": len(qdata["mapping"]),
        }
        save_results(state)
        run.note(f"scored {len(qdata['mapping'])} recordings: {json.dumps(qdata['ac_train_summary'])}")
        print("[0101] quality tiers:", json.dumps(qdata["ac_train_summary"], indent=2), flush=True)

    mapping = qdata["mapping"]

    with run.stage("train dualar-quality 240k") as stage:
        tr = QualityDualARTrainer(OUTPUT / "dualar-quality-240k", mapping, steps=240000)
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"step {s}: cond {e['val_cond']:.4f} · uncond {e['val_uncond']:.4f} · "
                f"Δ {e['cond_gain']:+.4f}"
            ),
        )
        state["training"] = res
        save_results(state)
        del tr
        exp99.cleanup()

    ckpt_path = OUTPUT / "dualar-quality-240k/step-240000.pt"

    with run.stage("full validation") as stage:
        val_ds = TokenDataset(TOKENS, "val")
        ac_val = [i for i, r in enumerate(val_ds.records)
                  if r["species"] == "american-crow" and r.get("canonical", True)]
        model, vocab, _, _ = exp99.load_model_from_checkpoint(ckpt_path, "cuda")
        for idx, (mode, forced) in enumerate([("conditional_true_tier", None), ("unconditional_q_unknown", UNKNOWN)]):
            if mode in state["full_validation"]:
                continue
            m = eval_quality_per_stage(
                model, vocab, val_ds, ac_val, mapping, "cuda", batch_size=16,
                force_tier=forced,
                on_progress=lambda d, t, i=idx, lb=mode: stage.update(
                    i * len(ac_val) + d, 2 * len(ac_val), extra=lb
                ),
            )
            state["full_validation"][mode] = {
                "overall": round(m["overall"], 5),
                "codec_plus_eos": round(m["codec_plus_eos"], 5),
                "coarse_0_2": round(m["coarse_0_2"], 5),
                "fine_5_7": round(m["fine_5_7"], 5),
                "per_stage": {k: (round(v, 5) if v is not None else None)
                              for k, v in m["per_stage"].items()},
            }
            save_results(state)
            run.note(
                f"FULL VAL {mode}: codec+eos {m['codec_plus_eos']:.4f} · "
                f"coarse {m['coarse_0_2']:.4f} · fine {m['fine_5_7']:.4f}"
            )
            print(f"[full val] {mode}: codec+eos={m['codec_plus_eos']:.4f} "
                  f"coarse={m['coarse_0_2']:.4f} fine={m['fine_5_7']:.4f}", flush=True)
        del model
        exp99.cleanup()

    with run.stage("tier & CFG sweep") as stage:
        # Reference: unconditioned 0100 Dual-AR 17M 240k with the same SNR/flatness metrics.
        p0100 = REPO / "crowgpt/results/scaling-0100/dualar-17M-240k/step-240000.pt"
        if "0100_uncond_240k" not in state["instruments"]:
            s0 = exp99.load_sampler(p0100, device="cuda", decoder_state="finetuned")
            state["instruments"]["0100_uncond_240k"] = draw_quality_instruments(
                s0, 100, 101000, dict(temperature=1.1, top_k=200, max_frames=460),
                stage, "0100_uncond_240k", save_dir=OUTPUT / "clips/0100_uncond_240k",
            )
            save_results(state)
            del s0
            exp99.cleanup()

        sampler = DualARSampler(ckpt_path, device="cuda", decoder_state="finetuned")
        sweep = [
            ("q0_noisy_w10", dict(temperature=1.1, top_k=200, max_frames=460, channel="q0_noisy", guidance_scale=1.0)),
            ("q2_mid_w10", dict(temperature=1.1, top_k=200, max_frames=460, channel="q2_mid", guidance_scale=1.0)),
            ("q4_crisp_w10", dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp", guidance_scale=1.0)),
            ("q4_crisp_cfg13", dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp",
                                    guidance_scale=1.3, uncond_channel=UNKNOWN)),
            ("q4_crisp_cfg16", dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp",
                                    guidance_scale=1.6, uncond_channel=UNKNOWN)),
            ("q4_crisp_cfg20", dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp",
                                    guidance_scale=2.0, uncond_channel=UNKNOWN)),
            ("q4_crisp_cfg16_rep105", dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp",
                                           guidance_scale=1.6, uncond_channel=UNKNOWN, repeat_penalty=1.05)),
        ]
        for label, skw in sweep:
            if label in state["instruments"]:
                continue
            summary = draw_quality_instruments(
                sampler, 100, 101000, skw, stage, label, save_dir=OUTPUT / "clips" / label,
            )
            state["instruments"][label] = summary
            save_results(state)
            run.note(
                f"{label}: snr={summary['median_snr_db']} dB · flat={summary['median_quiet_flatness']} · "
                f"pitch={summary['mean_pitch_strength']} (p25={summary['p25_pitch_strength']}) · "
                f"dust={summary['dust_rate']} · churn={summary['stage0_churn']}"
            )
            print(f"[inst] {label}: {summary}", flush=True)
        del sampler
        exp99.cleanup()

    # Pick best CFG arm: highest pitch_strength among those keeping stage0_churn >= 0.855.
    cfg_candidates = ["q4_crisp_cfg13", "q4_crisp_cfg16", "q4_crisp_cfg20", "q4_crisp_cfg16_rep105"]
    feasible = [k for k in cfg_candidates if (state["instruments"][k]["stage0_churn"] or 0) >= 0.855]
    pool = feasible or cfg_candidates
    best_cfg_label = max(pool, key=lambda k: state["instruments"][k]["mean_pitch_strength"] or 0.0)
    best_cfg_kwargs = dict(sweep)[best_cfg_label]
    state["best_cfg"] = {"label": best_cfg_label, "summary": state["instruments"][best_cfg_label]}
    save_results(state)

    with run.stage("memorisation & compare page") as stage:
        import importlib.util
        spec = importlib.util.spec_from_file_location("exp100", REPO / "experiments/0100-scaling-dualar/run.py")
        exp100 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exp100)

        stage.update(0, 3, extra="building train stage-0 n-gram index")
        ngram_idx = exp100.build_coarse_ngram_index()
        stage.update(1, 3, extra="scoring q4_crisp w=1.0 & best CFG")
        state["memorisation"]["q4_crisp_w10"] = exp100.ngram_overlap_rate(
            exp100.generated_stage0_seqs(
                ckpt_path, dict(temperature=1.1, top_k=200, max_frames=460, channel="q4_crisp", guidance_scale=1.0),
            ),
            ngram_idx,
        )
        state["memorisation"][best_cfg_label] = exp100.ngram_overlap_rate(
            exp100.generated_stage0_seqs(ckpt_path, best_cfg_kwargs),
            ngram_idx,
        )
        save_results(state)
        run.note(f"memorisation: {state['memorisation']}")

        stage.update(2, 3, extra="writing compare.html")
        build_compare_page(ckpt_path, best_cfg_label, best_cfg_kwargs, OUTPUT / "compare.html")
        stage.update(3, 3, extra="done")

    run.note("0101 complete.")
    print("=== 0101 COMPLETE ===", flush=True)


if __name__ == "__main__":
    main()
