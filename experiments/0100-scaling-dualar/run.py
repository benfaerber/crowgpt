"""0100: Scaling Dual-AR — longer training (17.3M @ 240k) vs larger capacity (~40M @ 120k).

0099 showed Dual-AR (17.34M) reached 4.5674 full American Crow val CE in 40 min
with a flat train/val gap (+0.1555) and was still improving until LR decayed.
With ~4 h left on the overnight GPU booking, this tests both levers Dual-AR
unlocked:

  1. dualar-17M-240k : same 17.34M (d384, L6+D2), 240k steps (~75 min)
  2. dualar-40M-120k : scaled d512, L8 temporal + L3 depth, H8 (~39M params,
                       matching 0096's capacity class), 120k steps (~55 min)

Then:
  - Full 5,033-bout per-stage validation on both + intermediate snapshots.
  - Offline instrument suite (0067 structure, 0069 dust/pitch, 0046 churn) at
    both default (T=1.1, k=200) and rep=1.05 (T=1.1, k=200, repeat_penalty=1.05)
    plus T=1.15/k=200.
  - 0015-style exact coarse n-gram memorisation check (generated vs held-out
    real bouts against canonical training n-grams) to confirm longer training /
    larger capacity is not copying.
  - Labelled diagnostic HTML comparison page at
    `crowgpt/results/scaling-0100/compare.html` (diagnostic only, never a
    competing sitting page) comparing Real, CrowGPT2, 0099 dualar-120k (rep1.05),
    and 0100's best arm.
"""

import gc
import json
import os
import sys
import time
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

import run as exp99
from crowgpt.codec import CODEBOOK_SIZE, SAMPLE_RATE, normalise
from crowgpt.demo import ComparePage
from crowgpt.dualar import DualARConfig, DualARCrowGPT
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore, TokenDataset
from crowgpt.train import BucketedBatcher, require_device
from training import atomic_json, fixed_panel

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
TOKENS = DATA / "crowgpt/tokens-6s"
BOUTS = DATA / "crowgpt/bouts-6s"
OUTPUT = REPO / "crowgpt/results/scaling-0100"
RESULTS_JSON = HERE / "results.json"


class CustomDualARTrainer(exp99.ArmTrainer):
    """ArmTrainer with configurable Dual-AR width/depth."""

    def __init__(self, out_dir, *, n_embd=384, n_layer=6, depth_layer=2, n_head=4,
                 depth_head=4, steps=120000, learning_rate=6e-4, lr_floor=0.01,
                 seed=0, token_budget=12300, eval_every=4000, checkpoint_every=20000):
        self.out_dir = Path(out_dir)
        self.arch = "dualar"
        self.steps = steps
        self.learning_rate = learning_rate
        self.warmup = 400
        self.lr_floor = lr_floor
        self.stage_weights = None
        self.eval_every = eval_every
        self.checkpoint_every = checkpoint_every
        self.device = require_device()

        torch.manual_seed(seed)
        self.train_set = TokenDataset(TOKENS, "train")
        self.val_set = TokenDataset(TOKENS, "val")
        manifest = self.train_set.manifest
        from crowgpt.tokens import Vocabulary
        self.vocabulary = Vocabulary(
            manifest["n_codebooks"],
            manifest["species"],
            manifest.get("call_types", ()),
            n_unit_buckets=manifest.get("n_unit_buckets", 0),
        )
        longest = max(r["length"] for r in self.train_set.records)
        block_size = int(min(4096, max(256, longest)))
        self.is_dualar = True
        self.config = DualARConfig(
            vocab_size=self.vocabulary.size,
            n_codebooks=manifest["n_codebooks"],
            block_size=block_size,
            n_layer=n_layer,
            depth_layer=depth_layer,
            n_head=n_head,
            depth_head=depth_head,
            n_embd=n_embd,
            dropout=0.0,
            prefix_len=self.vocabulary.prefix_len,
            norm="rmsnorm",
            mlp="swiglu",
        )
        self.model = DualARCrowGPT(self.config).to(self.device)
        self.legal = None
        self.slices = None
        self.train_batcher = BucketedBatcher(
            self.train_set, 8, block_size, self.device, seed=seed,
            vocabulary=self.vocabulary, token_budget=token_budget,
        )
        self.panels = {
            "train": fixed_panel(self.train_set, 256, 87),
            "val": fixed_panel(self.val_set, 256, 86),
        }
        self.signature = {
            "arch": "dualar",
            "config": self.config.as_dict(),
            "steps": steps,
            "learning_rate": learning_rate,
            "lr_floor": lr_floor,
            "warmup": self.warmup,
            "token_budget": token_budget,
            "seed": seed,
        }


def build_coarse_ngram_index(spans=(8, 16, 32)):
    """Exact stage-0 n-gram sets from canonical American Crow training bouts (0015 protocol)."""
    ds = TokenDataset(TOKENS, "train")
    p = ds.manifest["prefix_len"]
    k = ds.manifest["n_codebooks"]
    index = {n: set() for n in spans}
    for i, r in enumerate(ds.records):
        if r["species"] != "american-crow" or not r.get("canonical", True):
            continue
        seq = ds.sequence(i)[p:-1]
        usable = (seq.size // k) * k
        if usable == 0:
            continue
        s0 = seq[:usable].reshape(-1, k)[:, 0]
        raw = s0.astype(np.uint16).tobytes()
        for n in spans:
            step = 2 * n
            for pos in range(0, len(raw) - step + 1, 2):
                index[n].add(raw[pos : pos + step])
    return index


def ngram_overlap_rate(stage0_seqs, index, spans=(8, 16, 32)):
    """Fraction of bouts containing at least one exact training stage-0 n-gram."""
    hits = {n: 0 for n in spans}
    eligible = {n: 0 for n in spans}
    for s0 in stage0_seqs:
        raw = np.asarray(s0, dtype=np.uint16).tobytes()
        for n in spans:
            if len(s0) < n:
                continue
            eligible[n] += 1
            step = 2 * n
            if any(raw[pos : pos + step] in index[n] for pos in range(0, len(raw) - step + 1, 2)):
                hits[n] += 1
    return {
        f"ngram_{n}": round(hits[n] / max(1, eligible[n]), 4)
        for n in spans
    }


def heldout_stage0_seqs(n=100):
    ds = TokenDataset(TOKENS, "test")
    p = ds.manifest["prefix_len"]
    k = ds.manifest["n_codebooks"]
    rng = np.random.default_rng(100)
    ac = [i for i, r in enumerate(ds.records)
          if r["species"] == "american-crow" and r.get("canonical", True)]
    rng.shuffle(ac)
    out = []
    for i in ac[:n]:
        seq = ds.sequence(i)[p:-1]
        usable = (seq.size // k) * k
        if usable:
            out.append(seq[:usable].reshape(-1, k)[:, 0])
    return out


def generated_stage0_seqs(path, sampling_kwargs, n=100, seed_base=10000):
    sampler = exp99.load_sampler(path, device="cuda", decoder_state="finetuned")
    k = sampler.vocabulary.n_codebooks
    out = []
    for s in range(seed_base, seed_base + n * 5):
        flat = sampler.tokens("american-crow", seed=s, **sampling_kwargs)
        if flat.size < k * 75:
            continue
        out.append(flat.reshape(-1, k)[:, 0])
        if len(out) == n:
            break
    del sampler
    exp99.cleanup()
    return out


def build_diagnostic_compare_page(winner_label, winner_path, best_sampling, out_html):
    """Build a labelled diagnostic page (per CLAUDE.md, never a sitting) for morning audition."""
    store = BoutStore(BOUTS)
    rng = np.random.default_rng(10042)
    test_ac = [i for i in store.split(seed=0)["test"]
               if store.index[i]["species"] == "american-crow"
               and store.index[i]["n_samples"] >= 2 * SAMPLE_RATE]
    rng.shuffle(test_ac)
    reals = [normalise(store.audio(store.index[i])) for i in test_ac[:8]]

    arms_spec = [
        ("CrowGPT2 (30k, T=1.1)", exp99.REFERENCES["CrowGPT2 (30k, 18.7M)"],
         dict(temperature=1.1, top_k=200, max_frames=460)),
        ("0099 Dual-AR 17M 120k (rep=1.05)",
         REPO / "crowgpt/results/shootout-0099/dualar-120k/step-120000.pt",
         dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460)),
        (f"0100 {winner_label} (best sampling)", winner_path, best_sampling),
    ]
    drawn = {}
    for name, ckpt, skw in arms_spec:
        sampler = exp99.load_sampler(ckpt, device="cuda", decoder_state="finetuned")
        clips = []
        for s in range(10100, 10200):
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
        "Experiment": "0099 / 0100 Dual-AR scaling",
        "Winner": winner_label,
        "Sampling": json.dumps(best_sampling),
        "Decoder": "0063 adversarial finetune",
        "Note": "Labelled diagnostic only — not a blinded sitting",
    }
    page = ComparePage(rows, facts)
    page.write(out_html)


def save_results(state):
    atomic_json(RESULTS_JSON, state)


def main():
    if require_device() != "cuda":
        raise RuntimeError("0100 requires CUDA")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(RESULTS_JSON.read_text()) if RESULTS_JSON.exists() else {
        "arms": {},
        "full_validation": {},
        "instruments": {},
        "memorisation": {},
        "latency": {},
    }

    run = Run(
        "0100 scaling Dual-AR",
        [
            "dualar-17M-240k",
            "dualar-40M-120k",
            "full validation",
            "instruments & sampling",
            "memorisation & compare page",
        ],
    )
    validator = exp99.FullStageValidator()

    # --- Arm 1: 17.34M Dual-AR @ 240k steps ---
    with run.stage("dualar-17M-240k") as stage:
        tr = CustomDualARTrainer(
            OUTPUT / "dualar-17M-240k",
            n_embd=384, n_layer=6, depth_layer=2, n_head=4, depth_head=4,
            steps=240000, learning_rate=6e-4, lr_floor=0.01, seed=0,
            eval_every=4000, checkpoint_every=40000,
        )
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"17M-240k step {s}: panel val {e['val']:.4f} (coarse {e['val_coarse_0_2']:.4f} · gap {e['gap']:+.4f})"
            ),
        )
        state["arms"]["dualar-17M-240k"] = res
        save_results(state)
        del tr
        exp99.cleanup()

    # --- Arm 2: ~40M Dual-AR (d512, L8 temporal + L3 depth, H8) @ 120k steps ---
    with run.stage("dualar-40M-120k") as stage:
        tr = CustomDualARTrainer(
            OUTPUT / "dualar-40M-120k",
            n_embd=512, n_layer=8, depth_layer=3, n_head=8, depth_head=8,
            steps=120000, learning_rate=6e-4, lr_floor=0.01, seed=0,
            eval_every=4000, checkpoint_every=20000,
        )
        res = tr.run(
            on_step=lambda d, t, extra: stage.update(d, t, extra=extra),
            on_eval=lambda s, e: run.note(
                f"40M-120k step {s}: panel val {e['val']:.4f} (coarse {e['val_coarse_0_2']:.4f} · gap {e['gap']:+.4f})"
            ),
        )
        state["arms"]["dualar-40M-120k"] = res
        save_results(state)
        del tr
        exp99.cleanup()

    # --- Stage 3: Full 5,033-bout per-stage validation ---
    with run.stage("full validation") as stage:
        ckpts = [
            ("dualar-17M-step160k", OUTPUT / "dualar-17M-240k/step-160000.pt"),
            ("dualar-17M-step200k", OUTPUT / "dualar-17M-240k/step-200000.pt"),
            ("dualar-17M-240k", OUTPUT / "dualar-17M-240k/step-240000.pt"),
            ("dualar-40M-step60k", OUTPUT / "dualar-40M-120k/step-060000.pt"),
            ("dualar-40M-step100k", OUTPUT / "dualar-40M-120k/step-100000.pt"),
            ("dualar-40M-120k", OUTPUT / "dualar-40M-120k/step-120000.pt"),
        ]
        ckpts = [(lb, p) for lb, p in ckpts if p.exists()]
        for idx, (label, path) in enumerate(ckpts):
            if label in state["full_validation"]:
                continue
            row = validator.score_checkpoint(
                path,
                on_progress=lambda d, t, i=idx, lb=label: stage.update(
                    i * len(validator.indices) + d, len(ckpts) * len(validator.indices), extra=lb
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

    # Pick overall best checkpoint between 17M-240k and 40M-120k
    v17 = state["full_validation"]["dualar-17M-240k"]["overall"]
    v40 = state["full_validation"]["dualar-40M-120k"]["overall"]
    best_label = "dualar-40M-120k" if v40 < v17 else "dualar-17M-240k"
    best_path = OUTPUT / best_label / f"step-{120000 if best_label == 'dualar-40M-120k' else 240000:06d}.pt"
    state["winner"] = {"label": best_label, "overall": min(v17, v40), "v17": v17, "v40": v40}
    save_results(state)

    # --- Stage 4: Instruments & sampling sweep + CPU/GPU latency ---
    with run.stage("instruments & sampling") as stage:
        p17 = OUTPUT / "dualar-17M-240k/step-240000.pt"
        p40 = OUTPUT / "dualar-40M-120k/step-120000.pt"
        specs = [
            ("17M_240k_T110", p17, dict(temperature=1.1, top_k=200, max_frames=460), 12),
            ("17M_240k_T110_rep105", p17, dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460), 12),
            ("17M_240k_T115", p17, dict(temperature=1.15, top_k=200, max_frames=460), 12),
            ("40M_120k_T110", p40, dict(temperature=1.1, top_k=200, max_frames=460), 12),
            ("40M_120k_T110_rep105", p40, dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460), 12),
            ("40M_120k_T115", p40, dict(temperature=1.15, top_k=200, max_frames=460), 12),
        ]
        for label, ckpt, skw, save_n in specs:
            if label in state["instruments"]:
                continue
            sampler = exp99.load_sampler(ckpt, device="cuda", decoder_state="finetuned")
            res = exp99.draw_instrument_set(
                sampler, 100, 100000, skw, stage, label,
                save_dir=OUTPUT / "clips" / label, save_n=save_n,
            )
            state["instruments"][label] = res["summary"]
            save_results(state)
            run.note(
                f"instrument {label}: units={res['summary']['mean_units']} "
                f"dust={res['summary']['dust_rate']} pitch={res['summary']['mean_pitch_strength']} "
                f"churn={res['summary']['stage0_churn']}"
            )
            del sampler
            exp99.cleanup()

        if "dualar_40M" not in state["latency"]:
            state["latency"]["dualar_40M"] = exp99.benchmark_latency(p40)
            save_results(state)
            run.note(
                f"latency 40M: GPU {state['latency']['dualar_40M']['cuda']['ms_per_frame']} ms/f · "
                f"CPU {state['latency']['dualar_40M']['cpu']['ms_per_frame']} ms/f"
            )

    # --- Stage 5: 0015 memorisation check + morning diagnostic HTML page ---
    with run.stage("memorisation & compare page") as stage:
        stage.update(0, 5, extra="building train stage-0 n-gram index")
        ngram_idx = build_coarse_ngram_index()
        mem = state.get("memorisation", {})
        if "real_heldout" not in mem:
            mem["real_heldout"] = ngram_overlap_rate(heldout_stage0_seqs(100), ngram_idx)
        stage.update(1, 5, extra="crowgpt2 n-grams")
        if "crowgpt2" not in mem:
            mem["crowgpt2"] = ngram_overlap_rate(
                generated_stage0_seqs(exp99.REFERENCES["CrowGPT2 (30k, 18.7M)"],
                                      dict(temperature=1.1, top_k=200, max_frames=460)),
                ngram_idx,
            )
        stage.update(2, 5, extra="17M-240k n-grams")
        if "17M_240k_rep105" not in mem:
            mem["17M_240k_rep105"] = ngram_overlap_rate(
                generated_stage0_seqs(OUTPUT / "dualar-17M-240k/step-240000.pt",
                                      dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460)),
                ngram_idx,
            )
        stage.update(3, 5, extra="40M-120k n-grams")
        if "40M_120k_rep105" not in mem:
            mem["40M_120k_rep105"] = ngram_overlap_rate(
                generated_stage0_seqs(OUTPUT / "dualar-40M-120k/step-120000.pt",
                                      dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460)),
                ngram_idx,
            )
        state["memorisation"] = mem
        save_results(state)
        run.note(f"memorisation (16-frame stage-0): { {k: v['ngram_16'] for k, v in mem.items()} }")

        stage.update(4, 5, extra="writing diagnostic compare.html")
        build_diagnostic_compare_page(
            best_label,
            best_path,
            dict(temperature=1.1, top_k=200, repeat_penalty=1.05, max_frames=460),
            OUTPUT / "compare.html",
        )
        stage.update(5, 5, extra="done")

    run.note("0100 complete.")
    print("=== 0100 COMPLETE ===", flush=True)


if __name__ == "__main__":
    main()
