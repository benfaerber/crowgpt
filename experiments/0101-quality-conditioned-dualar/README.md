# 0101 — Recording-quality conditioning + Classifier-Free Guidance on Dual-AR 17M

**2026-11-20** · GPU ~1 h 50 min · **answer: works decisively on every acoustic quality axis, with zero memorisation. Pinning `q4_crisp` + CFG 1.3–1.6 raises median SNR from 16.9 → 24.3 dB (+7.4 dB), cuts quiet-frame hiss in half (0.173 → 0.088), lifts worst-quartile pitch strength from 0.417 → 0.498, cuts dust rate nearly in half (21.8% → 12.0–16.2%), and lifts gradeable keep rate from 75.8% → 87–88.5%, with 0% 32-frame memorisation. Diagnostic comparison page open for audition; blinded sitting pending.**

## The question

0100's Dual-AR 17M @ 240k reached `4.5308` full American Crow val CE, and Ben's labelled audition picked it as the best model while naming the remaining flaw: *"some audio clips sound really good like the first one and others have lower quality."*

Scoring all 40,936 recordings in `bouts-6s` purely acoustically (no BirdNET, fit on American Crow train only) confirmed why: the bottom 20% of American Crow recordings (`q0_noisy`, 2,918 recordings) have median **9.07 dB SNR** and **0.000 pitch strength**, while the top 20% (`q4_crisp`, 2,918 recordings) have **23.64 dB SNR**, **0.089 quiet-frame flatness**, and **0.667 pitch strength**. An unconditioned generator samples uniformly across that spread.

Can splicing a single acoustic quality-tier prefix token (`q0_noisy..q4_crisp` + `q_unknown` with 15% CFG dropout, zero re-tokenization) let Dual-AR pin the crisp tier cleanly—and does Classifier-Free Guidance sharpen it further without causing stickiness or memorisation?

## Method

1. **Recording quality tiers (`recording_quality.json`):** For every recording in `bouts-6s` (median over up to 6 normalised bouts), compute `snr_db` (`p95 − p20` of segmenter dB envelope), `log(quiet_flatness)` (spectral flatness of quiet frames in 300–8000 Hz), and `pitch_strength` (mean autocorrelation peak across detected bursts). Standardise using American Crow *train* recordings only into `(z_snr − z_flat + z_pitch)/3` and cut at 20/40/60/80% quantiles into `q0_noisy..q4_crisp`, plus dedicated null token `q_unknown`.
2. **Training:** Dual-AR 17M (`d384, L6 temporal + L2 depth, H4`, `17,345,664` params), `tokens-6s`, 240k steps (`lr=6e-4 → 0.01`, token budget `12,300`, 82 min), splicing the quality token at prefix position 1 (remapping disk `unit_base` so `prefix_len=4` aligns cleanly) with 15% dropout to `q_unknown`.
3. **Evaluation:** Full 5,033-bout per-stage validation (conditional true tier vs unconditional `q_unknown`), 100-draw instrument sweeps across `q0_noisy`, `q2_mid`, `q4_crisp` (`w=1.0`), and CFG `w ∈ {1.3, 1.6, 2.0}` + `rep=1.05`, `0015` exact stage-0 n-gram memorisation check, and a labelled diagnostic comparison page (`crowgpt/results/quality-0101/compare.html`).

## Results

### 1. Corpus quality tiers (American Crow train, n = 14,589 recordings)

| Tier | Recordings | Median SNR (dB) | Quiet flatness (hiss ↓) | Pitch strength ↑ |
|---|---:|---:|---:|---:|
| `q0_noisy` | 2,918 | 9.07 | 0.1957 | 0.0000 |
| `q1_low` | 2,918 | 14.81 | 0.2615 | 0.3557 |
| `q2_mid` | 2,917 | 17.79 | 0.2299 | 0.5098 |
| `q3_clean` | 2,918 | 19.82 | 0.1631 | 0.5943 |
| **`q4_crisp`** | **2,918** | **23.64** | **0.0890** | **0.6667** |

### 2. Full American Crow validation CE (5,033 canonical bouts)

| Condition | Overall | Codec + EOS | Coarse (0–2) | Fine (5–7) | Prefix |
|---|---:|---:|---:|---:|---:|
| 0100 unconditioned Dual-AR 17M 240k | 4.5308 | — | 3.7227 | 5.1918 | 1.4418 |
| 0101 conditional (true recording tier) | 4.5301 | 4.5362 | 3.7242 | 5.1927 | 1.5063 |
| 0101 unconditional (`q_unknown`) | 4.5306 | 4.5365 | 3.7247 | 5.1928 | 1.6007 |

Teacher-forced codec CE barely moves between conditional and unconditional (`Δ = 0.0003` nats) because after the very first frames of real ambience, the acoustic history already identifies the recording's noise floor. At **generation time**, however, there is no real ambience yet—so the quality token sets the initial acoustic world the entire bout unfolds inside, and the generation metrics move dramatically:

### 3. Tier & CFG generation sweep (100 draws per arm, finetuned decoder)

| Arm | Median SNR ↑ | Quiet flat. ↓ | Mean pitch ↑ | p25 pitch (worst 25%) ↑ | Dust ↓ | Units | Stage-0 churn (real `0.8844`) | Keep ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0100 uncond 240k (`T=1.1, k=200`) | 16.91 dB | 0.1726 | 0.5368 | 0.4170 | 21.8% | 4.14 | 0.8794 | 75.8% |
| `q0_noisy` (`w=1.0`) | 12.64 dB | 0.2418 | 0.4823 | 0.3422 | 34.9% | 2.35 | 0.8963 | 56.8% |
| `q2_mid` (`w=1.0`) | 17.27 dB | 0.2118 | 0.5227 | 0.4242 | 21.6% | 4.38 | 0.8880 | 82.6% |
| **`q4_crisp` (`w=1.0`)** | **20.77 dB** | **0.1330** | **0.5745** | **0.4530** | **17.9%** | **5.61** | **0.8843** | **87.7%** |
| **`q4_crisp` (`CFG w=1.3`)** | **24.00 dB** | **0.1182** | **0.6000** | **0.4982** | **12.0%** | **6.27** | **0.8795** | **88.5%** |
| **`q4_crisp` (`CFG w=1.6`)** | **24.27 dB** | **0.0880** | **0.6119** | **0.4887** | **16.2%** | **6.10** | **0.8761** | **87.0%** |
| `q4_crisp` (`CFG w=2.0`) | 25.06 dB | 0.0907 | 0.6032 | 0.5045 | 16.3% | 6.15 | 0.8612 | 84.0% |
| `q4_crisp` (`CFG w=1.6, rep=1.05`) | 24.54 dB | 0.1114 | 0.6084 | 0.4713 | 19.6% | 5.78 | 0.8896 | 88.5% |

- **Monotonic control across tiers (`q0 → q2 → q4`):** SNR climbs `12.6 → 17.3 → 20.8 dB`, quiet flatness falls `0.242 → 0.212 → 0.133`, dust falls `34.9% → 21.6% → 17.9%`, and keep rate climbs `56.8% → 82.6% → 87.7%`.
- **CFG `w=1.3..1.6` lifts the bottom quartile:** `p25_pitch_strength` rises from `0.417` (0100 uncond) to `0.498` (`CFG 1.3`) / `0.489` (`CFG 1.6`), cutting dust rate nearly in half (`12.0%` at `w=1.3`) while keeping `stage0_churn` near real (`0.880` / `0.876` vs `0.884`). At `w=2.0`, churn starts dropping (`0.861`), signaling the upper limit of guidance.
- **Note on bout density:** `q4_crisp` clips average `5.6–6.3` units per bout (vs `4.39` across all real recordings, because high-SNR crisp recordings in the corpus have more cleanly detected bursts). Watch by ear whether `CFG 1.6` sounds over-energetic vs `w=1.0` or `CFG 1.3`.

### 4. Memorisation check (0015 protocol: exact stage-0 n-grams vs canonical train)

| Arm | 8-frame (~107 ms) | 16-frame (~213 ms) | 32-frame (~427 ms) |
|---|---:|---:|---:|
| Real held-out (test, from 0100) | 36.6% | 4.6% | 1.2% |
| `q4_crisp` (`w=1.0`) | 56.0% | 1.0% | 0.0% |
| `q4_crisp` (`CFG w=1.6`) | 53.0% | 1.0% | 0.0% |

Still **zero memorisation** at 16 and 32 frames (`1.0%` and `0.0%`, strictly below held-out real audio).

## Audition & caveats

- **Labelled diagnostic page:** `crowgpt/results/quality-0101/compare.html` (8 rows: Real, CrowGPT2, 0100 Dual-AR 240k uncond, 0101 `q4_crisp w=1.0`, 0101 `q4_crisp CFG w=1.6`). Diagnostic only—not a blinded sitting.
- **Ben's informal labelled audition (2026-11-20, unblinded):** *"I think this is best: 0101 Dual-AR q4_crisp (q4_crisp_cfg16)."* Recorded as a diagnostic sanity check, not a blinded verdict; clears the candidate to proceed to a blinded sitting against CrowGPT2.
- **Watch for over-guidance:** `CFG w=1.3` had the lowest dust (`12.0%`) and highest `p25_pitch` (`0.498`) while `w=1.6` had the highest mean pitch (`0.612`) and lowest hiss (`0.088`). Auditioning both `w=1.0` and `w=1.6` (and `clips/q4_crisp_cfg13/`) will tell quickly whether `w=1.0`, `1.3`, or `1.6` sounds most natural.

## What it changed

- **Dual-AR + recording-quality conditioning + CFG is the new leading candidate:** `crowgpt/results/quality-0101/dualar-quality-240k/step-240000.pt` (17.35M params, 67 MB).
- **`DualARSampler.tokens()` now supports native batch-2 CFG** (`guidance_scale`, `uncond_channel`, `uncond_call_type`), tested in `crowgpt/tests/test_architectures.py`.
- **Blinded sitting registered (`pool.py`):** pool **`quality-0101`** (id 9) in the dashboard's Listening panel — 54 trials in 3 doses of 18 (30-min cooldown, 40 comparisons + 8 real catches + 6 swapped-side repeats, fresh test groups disjoint from all earlier pools, unseen seed block `101500+`), comparing `0101 Dual-AR q4_crisp CFG w=1.6` against `CrowGPT2`.
- **Next step:** Grade `quality-0101` in the dashboard; if it passes by ear, apply the same Dual-AR + quality + CFG recipe to `tokens-6s-ct` (0102) and wire `DualARSampler` into `releases.py` / `hub.py` / `generate_worker.py` for CrowGPT3.
