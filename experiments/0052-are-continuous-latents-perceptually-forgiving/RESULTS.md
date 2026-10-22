# Are continuous latents perceptually forgiving in a way code indices are not?

## Overview

The crow-call generator works on discrete codec tokens, and a run of six experiments had shown that route stuck: every variation of which tokens to model came back null, and experiment 0035 found the codec's fine stages carry 9.935 bits of 10 — essentially unpredictable as symbols. But a discrete code is either right or wrong, while a continuous latent vector can be *approximately* right, and nobody had asked whether "approximately right" is inaudible. This experiment corrupted continuous codec latents with increasing amounts of noise and had Ben try to tell corrupted from clean in a blind ABX listening test. The answer is yes on both halves: 20% per-channel error was inaudible (his score sat below chance) while 80% was unmistakable (p = 0.0005). The wall the discrete route hit is a property of the encoding, not of the audio, and a continuous-generation route is open with a real, measured error budget.

## In depth

**The question.** Experiment 0035 measured DAC's stages 8–23 at 9.935 bits of 10 — unpredictable as symbol indices, because RVQ scatters near-neighbour vectors across arbitrary integers — and an extender handed the true coarse codes recovered 0.034 bits and scored 0/24 blind. That wall is real and permanent *in code space*, but it says nothing about whether the underlying vectors are predictable. Every prior null — capacity (experiments 0023, 0038), data (0048, 0049, 0050), sequence length (0038), token layout (0045), tokenizer config (0028–0037), filtering (0027), the fine-stage extender (0035) — varied *which* discrete tokens; none varied *whether* discrete tokens. There is a mechanism to match: codebook 0 must commit, every 13 ms, to one of 1024 spectral shapes with no "slightly brighter" available, and cross-entropy pays a symbol predictor to hold the modal symbol — which is why generated stage-0 churn sits at 0.801 against real audio's 0.868 (experiment 0046).

**The offline bench** (mean log-mel distance from raw, over 40 held-out American Crow bouts; lower is closer):

| representation | distance | |
|---|---|---|
| `cont32` | **0.2588** | 256-d continuous cascade, no codebook anywhere |
| `cont32+noise0.05` | 0.2771 | |
| `dac_quantized_32cb` | 0.3004 | |
| `cont32+noise0.10` | 0.3168 | |
| **`dac_quantized_24cb`** | **0.3686** | experiment 0039 proved this ABX-transparent |
| `cont32+noise0.20` | 0.4235 | |
| `dac_raw_z_no_quantizer` | 0.5492 | the 1024-d encoder output, decoded |
| `cont32+noise0.40` | 0.6951 | |
| **`encodec_6kbps`** | **0.7387** | 0039 could not resolve this by ABX either |
| `cont32+noise0.80` | 1.3306 | |
| `lowpass_2k` | 4.1432 | 0039: ABX 0.85, unmistakable |

Two things fall out. First, the continuous representation beats the codec setting already proven transparent — a model 10% wrong per channel is still closer to raw than `dac_quantized_24cb`. Second, unexpectedly, decoding the raw 1024-d encoder output `z` is worse than decoding a rank-256 approximation of it (0.5492 against 0.2588) despite carrying strictly more information: DAC's decoder was trained on quantizer output, so un-quantized `z` is off-manifold for it. That rules out "just model `z`" and names the 256-d `latents` as the modelling target — which is also 4× smaller. One trap was recorded: `quantizer.from_latents()` reads like the continuous path but calls a nearest-neighbour codebook search, so anything routed through it is quantized under a continuous name; the cascade was written out by hand for that reason. The bench ranks arms but cannot locate the audible boundary (experiment 0028's standing lesson), which is what the sitting is for.

**The sitting** — 2026-08-05, 120 ABX trials in 17m38s, one session, every trial answered. 120 distinct bouts from 120 distinct recordings, held-out American Crow, none previously played to Ben. Noise is scaled by the pool-wide per-channel standard deviation, not each clip's own, because a model's error is a fixed magnitude in latent space.

| arm | correct | rate | 95% CI | p(chance) | reading |
|---|---|---|---|---|---|
| `cont32` | 11 / 25 | 0.440 | [0.267, 0.629] | 0.788 | not resolved — at most 62.9% |
| `cont32+noise0.20` | 10 / 25 | 0.400 | [0.234, 0.593] | 0.885 | not resolved — at most 59.3% |
| `cont32+noise0.40` | 14 / 25 | 0.560 | [0.371, 0.733] | 0.345 | not resolved — at most 73.3% |
| **`cont32+noise0.80`** | **21 / 25** | **0.840** | [0.653, 0.936] | **0.0005** | **AUDIBLE** |
| **`lowpass_2k`** (anchor) | **15 / 20** | **0.750** | [0.531, 0.888] | **0.021** | **AUDIBLE** |

Ben's comment: *"most of the cont sound pretty ok. Low pass really bad."* This is a **pass** on the pre-registered reading: the anchor resolved (so the page and playback chain worked), the ceiling arm is clean, and 20% per-channel error is clean — both null arms sit below chance, which is what genuinely no signal looks like. The 0.80 arm earned its place as a second control: without it, four arms at chance would have been exactly as consistent with "the page cannot see latent noise" as with "the representation is forgiving". It resolved at p = 0.0005, so the nulls are real nulls.

The nulls also survive effort. ABX reveals the answer each trial, so a difference findable only by hunting is still a difference. Restricted to trials Ben played four or more times: `cont32` 5/8, `+0.20` 5/12 (still below chance), `+0.80` 7/8, anchor 7/7 — the effort gradient runs the right way for exactly the arms that should have one.

**The three misclicks.** Ben reported trials 11, 13 and 75 as wrong-button presses; all three were scored incorrect, all answered "b" against a truth of "a". They are kept in the primary analysis on a bias argument: a misclick that lands correct is one nobody notices, so excluding self-reported misclicks can only move scores up. It changes nothing — none fall in a null arm, and dropping them only strengthens what already resolved (`+0.80` 21/24, p 0.0001; anchor 15/18, p 0.004).

**Where the budget sits.** Inaudible at 0.20, unmistakable at 0.80, and the 0.40 rung unresolved with its point estimate above chance (14/25) — so the knee is somewhere between 0.20 and 0.80, probably nearer 0.40 than either end, and this sitting was not built to locate it more precisely. The working budget for a flow model is 20% per-channel error, with 40% a coin-toss and 80% out of the question — and 20% is a soft target, meaning "at least 20%, not resolved above it".

**Instrument note.** The pairwise sittings lose about 45% of their power to a resolved left-button bias (P(left) = 0.628 over 317 trials). Measured over all 210 saved ABX trials, ABX does not inherit that defect — P(answer = A) = 0.433, CI [0.366, 0.500], with the page balancing truth at 0.505 — so ABX sittings are worth their nominal power and the standing "fix PairPage first" advice does not gate them.

**Honest limits.** Gaussian noise is a stand-in for model error, not model error: a trained flow model's residual is correlated across time and channel and may be biased in ways white noise is not. So this measures whether the *representation* is forgiving — a precondition — not whether any particular model will succeed; a pass does not predict a good generator, while a fail would have killed the route outright, and that asymmetry is why it ran first and cheap. Nothing here says "transparent": at n=25 the upper bounds are about 60%, and equivalence needs roughly 200 trials (experiment 0039). The offline log-mel table must not be quoted as evidence of audibility either way.

**What this changed:**

1. **The modelling route is reopened** — the first result to reopen it since experiment 0045 declared it exhausted. 0035's wall is an encoding artifact, not a fact about the audio: "unpredictable as a symbol" and "unpredictable as a sound" are different claims, and only the first had ever been measured.
2. **A flow model over the 256-d latent has a real error budget** — at least 20% per channel, in units of the corpus's own per-channel spread — a quantity a training run can be checked against directly, which no previous generator target here has had.
3. **The modelling target is the 256-d `latents`, not the 1024-d `z`**, which decodes worse despite carrying more information.
4. **`from_latents` is off-limits** for any continuous measurement, written down before it cost a result.
5. **ABX does not carry PairPage's left-button bias**, so ABX sittings are not gated by the PairPage fix.

The knee between 0.20 and 0.80 is not located; if the budget ever needs to be tight, the 0.40 rung is where to spend trials.
