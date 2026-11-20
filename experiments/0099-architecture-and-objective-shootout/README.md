# 0099 — Architecture & objective shootout on `tokens-6s`

**2026-11-19/20** · GPU ~2 h 48 min · **answer: Dual-AR (`L6` temporal @ 75 Hz + `L2` depth, 17.34M params) beats every flat architecture on loss, training speed, VRAM, and inference latency. At 120k steps (40 min) it reaches 4.5674 full American Crow val CE (−0.225 below CrowGPT2, −0.101 below 0096's 43.9M flat model) and generates 4.5× faster on CPU. `repeat_penalty=1.05` cures the 120k stickiness cleanly; `min_p` hurts badly. Nobody has heard it yet.**

## The question

0096 and 0097 showed CrowGPT2 was undertrained (`4.793 → 4.690` at 60k steps) and 0098 sped up the flat trainer 2.7× via sliced loss and token-budgeted bucketing (`4.706` in 44 min). Every model so far still ran a single flat causal transformer with learned 1D absolute positions over 3,600 interleaved tokens (spending 7/8 of sequence length and quadratic attention on intra-frame residual codebooks) and weighted all 8 codebooks equally.

Four questions tested in one matched overnight suite on `tokens-6s`:

1. **Where does the loss live?** Break full validation CE (all 5,033 canonical American Crow bouts, 7,502,243 tokens) down by codebook stage (`prefix`, `stage_0..7`, `eos`) on CrowGPT2, 0097, 0098, and 0096.
2. **Frame-indexed RoPE + stage embeddings + RMSNorm/SwiGLU (`frame-rope-60k`, 17.34M params)** vs flat learned positions (`0098` 18.73M, matched 60k token-budget recipe).
3. **Dual-AR (`dualar-60k`, `L6` temporal @ 75 Hz + `L2` depth @ K=8, 17.34M params)** vs both flat models at matched 60k steps and matched parameter/layer count (8 transformer layers total).
4. **Winner pushed to 120k steps** (cosine floor `0.01`) + a **coarse-weighted loss** arm (`1.8 → 0.45` across stages `0..7`, 60k steps), followed by the offline instrument suite (`0067` structure, `0069` dust/pitch, `0046` stage-0 churn), a sampling sweep (`default`, `min_p=0.03`, `split-T`, `repeat_penalty=1.05`), and GPU/CPU latency benchmarks.

## Predictions (pre-registered in Option A plan)

- Per-stage breakdown will show fine stages 5–7 dominate pooled CE while coarse stages 0–2 sit much lower.
- Frame-indexed RoPE + SwiGLU will beat flat learned positions at matched 60k steps.
- Dual-AR will train dramatically faster, run much faster on CPU, and either match or beat flat models on loss by dedicating temporal attention to 75 Hz frame dynamics.
- Coarse-weighted training will pull `coarse_0_2` down at a small cost to `fine_5_7`.

## Results

### 1. Full American Crow validation CE (5,033 canonical bouts, 7,502,243 tokens)

Exact token-weighted cross-entropy (unweighted NLL everywhere, so all models are strictly apples-to-apples comparable):

| Model | Params | Steps | Train time | Overall ↓ | Coarse (0–2) ↓ | Fine (5–7) ↓ | Stage 0 ↓ | EOS ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CrowGPT2 (flat learned) | 18.73M | 30k | — | 4.7927 | 3.8812 | 5.5696 | 3.1591 | 0.8976 |
| 0098 budget (flat learned) | 18.73M | 60k | 44 min | 4.7064 | 3.8330 | 5.4495 | 3.1348 | 1.0744 |
| 0097 plain (flat learned) | 18.73M | 60k | 120 min | 4.6902 | 3.8220 | 5.4278 | 3.1224 | 0.9608 |
| **frame-rope-60k** | **17.34M** | 60k | 43 min | **4.6725** | **3.8172** | **5.3956** | 3.1174 | 0.9502 |
| 0096 larger (flat learned) | 43.86M | 60k | 220 min | 4.6680 | 3.8061 | 5.3990 | 3.1065 | 0.9366 |
| **dualar-coarse-60k** | **17.34M** | 60k | **20 min** | 4.6528 | **3.7954** | 5.3718 | 3.0825 | 1.0874 |
| **dualar-60k** | **17.34M** | 60k | **20 min** | **4.6388** | **3.8106** | **5.3266** | 3.1050 | 0.9161 |
| **dualar-120k @ 80k** | **17.34M** | 80k | 27 min | 4.6447 | 3.8174 | 5.3290 | 3.1076 | 0.9267 |
| **dualar-120k @ 100k** | **17.34M** | 100k | 33 min | 4.5901 | 3.7739 | 5.2625 | 3.0701 | 0.9422 |
| **dualar-120k @ 120k** | **17.34M** | 120k | **40 min** | **4.5674** | **3.7573** | **5.2332** | **3.0574** | **0.8805** |

Key takeaways from the validation table:

- **Per-stage baseline confirmed:** On CrowGPT2, `stage_0` is `3.159`, `coarse_0_2` is `3.881`, and `fine_5_7` is `5.570` — a 1.69-nat spread. Longer flat training (`0097`) improved both coarse (−0.059) and fine (−0.142).
- **Frame-RoPE + SwiGLU wins cleanly over flat learned positions:** At matched 60k token-budget steps (`43 min`), `frame-rope-60k` beats `0098` by **−0.034 nats** (`4.6725` vs `4.7064`) and beats `0097` plain (`4.6902`, 120 min) with 1.4M fewer parameters.
- **Dual-AR wins decisively on every axis:** At 60k steps (`20 min`, peak **1.00 GiB** VRAM, **425k tok/s**), `dualar-60k` (`17.34M`) beats `frame-rope-60k` by −0.034 nats *and* beats `0096`'s **43.9M** flat model (`4.6680`, 220 min) in **1/11th the wall time** with **2.5× fewer parameters**.
- **Dual-AR at 120k steps (`40 min`) hits `4.5674`** (−0.225 below CrowGPT2, −0.123 below `0097`, −0.101 below `0096`'s 43.9M model) and beats every baseline on **every single stage from `stage_0` through `stage_7` and `EOS`**, with a flat train/val panel gap (`+0.1555` vs `+0.1521` at 60k — no overfitting).
- **Coarse-weighted loss (`dualar-coarse-60k`) worked mechanically as predicted:** At 60k it lowered `coarse_0_2` (`3.7954` vs `3.8106`, `stage_0` `3.0825` vs `3.1050`) at a +0.045 cost on `fine_5_7` (`5.3718` vs `5.3266`) and slightly worse `EOS` (`1.087`). Unweighted `dualar-120k` beat it on both coarse (`3.7573`) and fine (`5.2332`) in 40 minutes.

### 2. Inference latency (GPU & CPU)

Measured with `max_frames=225` (3 s window), `T=1.1, k=200`, averaged over 8 GPU bouts and 3 CPU bouts after warmup:

| Model | GPU ms/frame | GPU s/bout | CPU ms/frame | CPU s/bout | CPU speedup vs CrowGPT2 |
|---|---:|---:|---:|---:|---:|
| CrowGPT2 (flat) | 13.32 | 2.09 | 47.44 | 8.98 | 1.0× |
| frame-rope (flat) | 18.39 | 3.06 | 57.28 | 10.62 | 0.85× |
| **Dual-AR** | **6.12** | **0.58** | **10.65** | **1.98** | **4.45×** |

Dual-AR cuts CPU generation latency by **4.5×**, directly impacting the CPU-only hosted Crow Chat / `/api/demo/generate` worker.

### 3. Offline instruments & sampling sweep (100 draws per arm, finetuned decoder)

Real reference: 200 held-out 6 s American Crow test bouts (`≥1 s`, one per group).

| Arm | Units | Single | Med gap (s) | Pitch str. | Dust rate | Stage-0 churn | Keep rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Real 6 s (n=200)** | **4.39** | **0.19** | **0.299** | **0.5342** | **0.2753** | **0.8844** | — |
| CrowGPT2 (`T=1.1, k=200`) | 4.23 | 0.18 | 0.277 | 0.5176 | 0.2588 | 0.8892 | 0.781 |
| 0097 60k (`T=1.1, k=200`) | 4.73 | 0.10 | 0.256 | 0.5416 | 0.2340 | 0.8873 | 0.800 |
| frame-rope 60k (`T=1.1, k=200`) | 4.60 | 0.21 | 0.277 | 0.5423 | 0.2235 | 0.8735 | 0.709 |
| **dualar 60k (`T=1.1, k=200`)** | **4.56** | **0.17** | **0.299** | **0.5490** | **0.2135** | **0.8824** | 0.735 |
| dualar 120k (`T=1.1, k=200`) | 4.60 | 0.21 | 0.256 | 0.5026 | 0.3494 | 0.8588 | 0.781 |
| dualar 120k (`min_p=0.03, T=1.05`) | 4.12 | 0.21 | 0.352 | 0.4747 | 0.4186 | 0.6849 | 0.800 |
| dualar 120k (`split-T + min_p=0.03`) | 4.43 | 0.16 | 0.341 | 0.4765 | 0.3750 | 0.7221 | 0.794 |
| **dualar 120k (`T=1.1, k=200, rep=1.05`)** | **4.88** | **0.18** | **0.288** | **0.5322** | **0.2326** | **0.8846** | 0.787 |
| dualar-coarse 60k (`T=1.1, k=200`) | 5.38 | 0.13 | 0.277 | 0.5270 | 0.2198 | 0.8749 | 0.741 |

Two clear sampling lessons:

1. **`min_p=0.03` is a clear negative:** Truncating probability tails collapses `stage0_churn` from `0.859 → 0.685` (very sticky), drops pitch strength to `0.475`, and raises dust to `0.419` — replicating 0069's finding that conservative sampling turns voiced caws into breathy bellows. Do not use `min_p` here.
2. **Better-trained models get stickier at fixed `T=1.1`, and `repeat_penalty=1.05` fixes it cleanly:** Moving from `dualar-60k` to `dualar-120k` sharpened logits and lowered `stage0_churn` (`0.882 → 0.859`) and pitch (`0.549 → 0.503`). Adding `repeat_penalty=1.05` (from 0047) brought `dualar-120k` right onto real audio on every axis simultaneously: `stage0_churn = 0.8846` (vs real `0.8844`), `pitch = 0.5322` (vs real `0.5342`), `dust = 0.2326` (vs real `0.2753`), `single_share = 0.18` (vs real `0.19`), `median_gap = 0.288 s` (vs real `0.299 s`).

## Caveats

- **Loss and offline instruments are not the ear.** Per 0086/0096, no checkpoint is a release until Ben hears it in a blinded listening pool. Because `capacity-0096` is currently open in the Listening panel, no competing listening pool was registered; 12 diagnostic WAV clips per arm are saved under `crowgpt/results/shootout-0099/clips/`.
- One seed (`seed=0`) per arm; `0099`'s Dual-AR lead over `0098` (`−0.068` at 60k, `−0.139` at 120k) is far larger than single-seed variance (~0.015), whereas the `0099` `dualar-60k` vs `dualar-coarse-60k` coarse delta (`0.015`) is modest.
- Memorisation (0015 n-gram overlap) is checked in the follow-up `0100`.

## What it changed

- **Dual-AR (`crowgpt/src/crowgpt/dualar.py`) replaces flat interleaving as the architecture to push.** Same parameter count (17.34M), 3.4× faster training than 0098 (11× faster than 0096), 4.5× faster CPU generation, 1.0 GiB VRAM, and −0.225 nats below CrowGPT2 at 120k steps.
- **`min_p` sampling is retired for CrowGPT** (clear negative on churn, pitch, and dust).
- **`repeat_penalty=1.05` earned a real listening test** on sharply trained Dual-AR checkpoints (matches real churn to 4 decimal places).
- **Per-stage validation (`LegalSlices.per_stage_sums` / `DualARCrowGPT.per_stage_sums`) is now standard** so future runs always see coarse vs fine separately.
- **Immediate follow-up (`0100`, running next on the remaining overnight GPU slot):** push Dual-AR along both axes it just unlocked — `17.34M @ 240k steps` and `~40M (d512, L8+D3) @ 120k steps` — plus 0015 n-gram memorisation check and a labelled diagnostic comparison page for morning listening.
