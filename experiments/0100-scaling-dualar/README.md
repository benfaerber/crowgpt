# 0100 — Scaling Dual-AR: 240k steps vs 40M parameters

**2026-11-20** · GPU ~3 h 07 min · **answer: 17.34M Dual-AR at 240k steps reaches 4.5308 full American Crow val CE (−0.262 below CrowGPT2, −0.137 below 0096's 43.9M flat model) and beats 39.6M Dual-AR at 120k (4.5337) at equal wall-clock time, with zero memorisation (1.0% vs 4.6% held-out 16-frame overlap) and 4.5× faster CPU generation. Diagnostic comparison page built for morning audition; nobody has heard it yet.**

## The question

0099 showed Dual-AR (`17.34M`, `d384 / L6 temporal + L2 depth`) reached `4.5674` at 120k steps in 40 minutes with a flat train/val gap (`+0.1555`) and only plateaued when cosine LR reached `6e-6`. That left two clean scaling directions:

1. **Steps (`dualar-17M-240k`):** Keep the fast, small `17.34M` model (`10.65 ms/frame` on CPU) and double the schedule to **240k steps** (~80 min).
2. **Capacity (`dualar-40M-120k`):** Scale Dual-AR to `39.58M` (`d512, L8 temporal + L3 depth, H8`) for **120k steps** (~74 min), matching `0096`'s capacity class in 1/3 the wall-clock time.

Both are checked on full 5,033-bout per-stage validation, offline acoustic instruments (`0067`/`0069`/`0046`), GPU/CPU latency, and the `0015` exact stage-0 n-gram memorisation test against held-out real bouts.

## Results

### 1. Full American Crow validation CE (5,033 canonical bouts, 7,502,243 tokens)

| Model | Params | Steps | Train time | Overall ↓ | Coarse (0–2) ↓ | Fine (5–7) ↓ | Stage 0 ↓ | EOS ↓ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CrowGPT2 (flat, 30k) | 18.73M | 30k | — | 4.7927 | 3.8812 | 5.5696 | 3.1591 | 0.8976 |
| 0096 larger flat (60k) | 43.86M | 60k | 220 min | 4.6680 | 3.8061 | 5.3990 | 3.1065 | 0.9366 |
| 0099 Dual-AR 17M (120k) | 17.34M | 120k | 40 min | 4.5674 | 3.7573 | 5.2332 | 3.0574 | 0.8805 |
| Dual-AR 17M @ 160k | 17.34M | 160k | 53 min | 4.6188 | 3.7915 | 5.3008 | 3.0824 | 0.9556 |
| Dual-AR 17M @ 200k | 17.34M | 200k | 66 min | 4.5594 | 3.7441 | 5.2283 | 3.0405 | 0.9002 |
| **Dual-AR 17M @ 240k** | **17.34M** | **240k** | **80 min** | **4.5308** | **3.7227** | **5.1918** | **3.0230** | **0.8918** |
| Dual-AR 40M @ 60k | 39.58M | 60k | 37 min | 4.6821 | 3.8564 | 5.3666 | 3.1465 | 1.0067 |
| Dual-AR 40M @ 100k | 39.58M | 100k | 61 min | 4.5576 | 3.7492 | 5.2209 | 3.0474 | 0.9371 |
| **Dual-AR 40M @ 120k** | **39.58M** | **120k** | **74 min** | **4.5337** | **3.7312** | **5.1905** | **3.0330** | **0.8621** |

- **Equal wall-clock winner: `dualar-17M-240k`.** In ~80 minutes it reaches `4.5308` overall and `3.7227` on coarse stages 0–2, edging out `dualar-40M-120k` (`4.5337` / `3.7312`, 74 min) while being **2.3× smaller** (67 MB vs 152 MB) and **2.7× faster on CPU** (`10.65` vs `29.13 ms/frame`).
- **Capacity on Dual-AR does scale at equal steps:** at 120k steps, 40M beats 17M by **−0.034 nats** (`4.5337` vs `4.5674`), and its train/val panel gap stays healthy (`+0.1670`). Pushing 40M to 240k (~2.5 h) would likely cross `4.50`, though the 17M model is far better suited for CPU serving on `field.crowgpt.org`.

### 2. Memorisation check (0015 protocol: exact stage-0 n-grams vs canonical train)

100 bouts per arm (held-out test real vs generated at `T=1.1, k=200, rep=1.05`):

| Arm | 8-frame (~107 ms) | 16-frame (~213 ms) | 32-frame (~427 ms) |
|---|---:|---:|---:|
| **Real held-out (test)** | **36.6%** | **4.6%** | **1.2%** |
| CrowGPT2 (`T=1.1, k=200`) | 38.0% | 2.0% | 0.0% |
| **Dual-AR 17M @ 240k (`rep=1.05`)** | **40.0%** | **1.0%** | **0.0%** |
| **Dual-AR 40M @ 120k (`rep=1.05`)** | **38.0%** | **0.0%** | **0.0%** |

**Zero memorisation.** Even after 240,000 steps (7+ passes), exact 16-frame and 32-frame coarse matches sit strictly below held-out real recordings.

### 3. Offline instruments & sampling sweep (100 draws per arm, finetuned decoder)

| Arm | Units | Single | Med gap (s) | Pitch str. | Dust rate | Stage-0 churn | Keep rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Real 6 s (n=200, from 0099)** | **4.39** | **0.19** | **0.299** | **0.5342** | **0.2753** | **0.8844** | — |
| CrowGPT2 (`T=1.1, k=200`) | 4.23 | 0.18 | 0.277 | 0.5176 | 0.2588 | 0.8892 | 0.781 |
| **17M @ 240k (`T=1.1, k=200`)** | **5.01** | **0.18** | **0.267** | **0.5304** | **0.2558** | **0.8889** | **0.758** |
| 17M @ 240k (`T=1.1, k=200, rep=1.05`) | 5.28 | 0.14 | 0.267 | 0.5492 | 0.2444 | 0.9082 | 0.752 |
| 17M @ 240k (`T=1.15, k=200`) | 4.56 | 0.17 | 0.267 | 0.5384 | 0.2444 | 0.9067 | 0.730 |
| 40M @ 120k (`T=1.1, k=200`) | 4.93 | 0.17 | 0.256 | 0.5278 | 0.2889 | 0.8707 | 0.741 |
| **40M @ 120k (`T=1.1, k=200, rep=1.05`)** | **5.27** | **0.13** | **0.283** | **0.5371** | **0.2584** | **0.8858** | **0.758** |
| 40M @ 120k (`T=1.15, k=200`) | 4.82 | 0.17 | 0.277 | 0.5394 | 0.2198 | 0.9103 | 0.769 |

Notably, `17M @ 240k` lands right on top of real audio at plain `T=1.1, k=200` (`stage0_churn = 0.8889` vs `0.8844`, `pitch = 0.5304` vs `0.5342`, `dust = 0.2558` vs `0.2753`, `single = 0.18` vs `0.19`), without needing `repeat_penalty`. On `40M @ 120k`, `repeat_penalty=1.05` brings churn from `0.8707 → 0.8858`.

### 4. Inference latency

| Model | GPU ms/frame | GPU s/bout | CPU ms/frame | CPU s/bout |
|---|---:|---:|---:|---:|
| CrowGPT2 (flat, 18.7M) | 13.32 | 2.09 | 47.44 | 8.98 |
| **Dual-AR 17.3M** | **6.12** | **0.58** | **10.65** | **1.98** |
| Dual-AR 39.6M | 7.49 | 0.83 | 29.13 | 5.61 |

## Audition & caveats

- **Labelled diagnostic page (not a sitting):** `crowgpt/results/scaling-0100/compare.html` places 8 rows of `Real held-out`, `CrowGPT2`, `0099 Dual-AR 17M 120k (rep=1.05)`, and `0100 Dual-AR 17M 240k (rep=1.05)` side by side. Per `CLAUDE.md`, no listening pool was registered while `capacity-0096` is open.
- **Ben's informal labelled audition (2026-11-20, unblinded):** *"I think 240k is the best one. Some audio clips sound really good like the first one and others have lower quality. I still think its the best."* Recorded as a hypothesis-generating diagnostic note, not a blinded verdict; it directly motivates conditioning on recording quality/SNR so draws stop landing on low-quality archive mics (0101).
- **No release until heard in a blinded sitting.** All weights are local under `crowgpt/results/shootout-0099/` and `crowgpt/results/scaling-0100/`.

## What it changed

- **New leading candidate checkpoint:** `crowgpt/results/scaling-0100/dualar-17M-240k/step-240000.pt` (`17.34M` params, `4.5308` full American Crow val CE, **−0.262 nats below CrowGPT2**, 0% 32-frame overlap, **4.5× faster on CPU**, plain `T=1.1 / k=200` on target).
- **Next human step:** Audition `crowgpt/results/scaling-0100/compare.html` for a quick sanity check, and once `capacity-0096` closes, register a blinded listening pool of `dualar-17M-240k` against CrowGPT2.
- **Next engineering step if Dual-AR wins by ear:** Train Dual-AR on `tokens-6s-ct` (with calibrated call-type labels + classifier-free guidance) to upgrade both CrowGPT2 and Crow Chat (`field.crowgpt.org`) with a 4.5× CPU speedup.
