# 0054 — Does a flow model on continuous latents beat the incumbent?

## Overview

This experiment asked whether a new class of generator — a rectified-flow model predicting continuous audio latents instead of discrete codebook tokens — could beat the project's incumbent autoregressive model (`model-fair-k8`) at producing crow calls. The motivation was that six previous experiments had exhausted every lever on the token-based approach, while experiment 0052 had shown that continuous latents are perceptually forgiving of error. The answer is a clear loss: after five full training runs, the best flow model reached 52.8% BirdNET detection against the incumbent's 94.4%, and Ben's ear agreed, describing the output as "static" rather than a caw. The one genuine gain was that changing the shape of the timestep distribution (uniform to logit-normal) doubled detection, and diagnostics showed the model can refine a partially-given signal perfectly but cannot originate structure from noise.

## In depth

### Why this was tried

Experiment 0045 had concluded that "the modelling route is exhausted — anything further needs a genuinely new class of idea," resting on six null results:

| lever | verdict | source |
|---|---|---|
| capacity | 0.164 nats bought 0.000 audible difference | experiments 0023, 0038 |
| training data | flat past 50%; next doubling ≈ +0.017 nats | experiment 0048 |
| more species | 0.42 [0.28, 0.57], neutral | experiment 0049 |
| bigger corpus by ear | 0.51 [0.36, 0.67], dead heat | experiment 0050 |
| sequence length | −0.38 resolved, worse | experiment 0038 |
| token layout (delay) | 0.53 [0.39, 0.67] | experiment 0045 |
| fine-stage extender | 0/24, structurally dead on DAC | experiment 0035 |

All of these varied which discrete tokens the model predicted; none varied whether it predicted tokens at all. Experiment 0052 supplied the precondition for a continuous alternative: a continuous DAC latent tolerates 20% per-channel error inaudibly (10/25 in a listening test, below chance) while 80% error is unmistakable (21/25, p = 0.0005). There was also a length argument: transparent fidelity at DAC-24's 24 codebooks costs 5,400 tokens for a 3-second bout — unaffordable autoregressively — but the same three seconds is only 225 continuous positions.

### Build

American Crow only (licensed by experiment 0049's neutral result on species mix; American Crow is 70.6% of the corpus anyway):

| | |
|---|---|
| corpus | 59,654 bouts → 50,108 train / val / test, grouped split, seed 0 |
| latents | 8,332,469 frames × 256 dims, float16, 4.27 GB |
| representation | DAC-24 kHz, 32-stage continuous cascade, no codebook |
| model | 22.1M parameters, d384 / L8 / H6, adaLN-Zero DiT |
| objective | rectified flow, uniform t, masked velocity MSE |
| sampling | 32 Euler steps; length drawn from the corpus, floored at 1.0 s |

### The judge, and the headline numbers

The verdict instrument was a four-arm BirdNET judgement with the incumbent regenerated in the same run — same corpus, same ambience, same BirdNET invocation — to avoid the cross-sitting comparison mistake experiment 0038 caught costing 33 points. First run, 36 clips per arm:

| arm | detected | mean conf |
|---|---|---|
| A · real held-out | 94.4% | 0.7486 |
| B · real through the continuous cascade | 91.7% | 0.7650 |
| C · flow model | 25.0% | 0.1501 |
| D · per-channel marginal control | 0.0% | 0.0000 |
| E · incumbent `model-fair-k8` | 94.4% | 0.8601 |

Three readings. First, the flow model loses badly, 25.0% against 94.4%. Second, the representation is not the problem: arm B shows the continuous cascade throws away almost nothing (91.7% versus real audio's 94.4%, comfortably above EnCodec's 80.6% ceiling), so the entire loss is the model's. Third, what the model learned is real — the marginal control scores exactly 0.0%, so 25% is genuine structure, not an artefact of ambience or decoding.

Two alternative explanations were ruled out: under-integration of the ODE (8 to 256 Euler steps all land within noise of each other at n=24, ±19 points) and a broken decode path (arm B uses the same decoder and scores 91.7%). A circularity caveat stands — the incumbent scores a mean confidence of 0.8601, higher than real audio's 0.7486, the symptom experiment 0022 named because BirdNET selected the training corpus — but circularity cannot explain a 25-versus-94 gap.

### The one gain: timestep shape

Five full 30,000-step runs, identical except one variable each:

| run | change | C detected | share of ceiling |
|---|---|---|---|
| `model-flow` | uniform t, per-channel norm | 25.0% | 27% |
| `model-flow-global` | global norm | 22.2% | 24% |
| `model-flow-lognorm` | logit-normal t, mean −0.5 | 52.8% | 58% |
| `model-flow-t15` | logit-normal t, mean −1.5 | 52.8% | 58% |
| `model-flow-t20` | logit-normal t, mean −2.0 | 41.7% | 45% |

Switching uniform to logit-normal timestep sampling doubled detection; every mean from −0.5 to −1.5 landed identically; −2.0 was worse; normalisation did nothing (22.2% versus 25.0% at n=36, ±15 points, indistinguishable — a measured null recorded because it was the author's own hypothesis and it failed). `-1.5` is kept as the default on a modest, unresolved mean-confidence edge (0.3742 against 0.3177), not on detection.

A cautionary methodological result sits alongside: a five-arm sweep at 12,000 steps ranked −1.5 as 2.5× better than −0.5 (27.8% versus 11.1%), and at 30,000 steps they are identical. The pre-registered risk in `sweep.py` — that a 12k ranking need not hold at 30k — fired. Short sweeps here filter obviously bad settings and nothing finer.

### The diagnostic that localised the failure

Starting the ODE from a real latent, partially noised, and integrating to t=1:

| start from | uniform-t model | logit-normal model |
|---|---|---|
| t=0.0 (pure noise) | 8.3% | 41.7% |
| t=0.3 | 75.0% | 100% |
| t=0.5 | 100% (conf 0.919) | 100% (conf 0.930) |
| t=0.9 | 100% | — |

The velocity field was learned correctly all along: given 30% of a real signal, even the first model reconstructed to 100% detection at confidence 0.919 — above real audio's 0.749. The failure lives entirely in the earliest, noise-dominated stretch where global structure is invented, and the logit-normal gain landed exactly there (t=0.0 went 8.3% → 41.7%; t=0.5 was saturated and did not move). The model refines superbly and cannot originate.

### The ear's verdict, and the defect it located

Ben, 2026-08-06, unprompted, on `flow-clips-best`: *"these flows are pretty bad. It doesnt sound like the caw at all. more like static."* The ear agreed with the judge rather than overturning it — the circularity caveat was a live reason to distrust the low score and turned out not to be the explanation.

"Static" is a claim about temporal structure, and it measured out:

| | real | flow | marginal control |
|---|---|---|---|
| per-stage std ratio | — | 0.90–1.08 | — |
| lag-1 correlation | 0.1346 | 0.0700 | 0.0013 |
| lag-2 | 0.1013 | 0.0654 | 0.0008 |
| lag-8 | 0.0480 | 0.0426 | −0.0009 |
| lag-16 | 0.0030 | 0.0296 | 0.0007 |

The marginals are essentially perfect — every per-stage standard deviation matches real audio within 10% — but the arrangement in time is not: the flow model has half the short-range correlation of real audio and ten times the long-range. Too rough frame-to-frame, too smooth across a bout: the profile of a mode-averaged generator. This also corrected a misreading of churn — the churn overshoot (+0.018 where the incumbent undershoots by −0.066 in EnCodec terms) *is* this defect, and had been reporting it all along. Churn triage on the best model (60 clips per side, DAC reference measured fresh because 0046's 0.868 is an EnCodec constant that does not transfer): stage-0 real 0.9547 versus generated 0.9729, gap +0.0182, essentially unchanged while detection doubled — a demonstration of churn's limits as an instrument.

### Caveats

- Validation losses are not comparable across model classes: the flow model's best val of 0.9072 is MSE on a velocity field, the incumbent's 4.587 is cross-entropy in nats; no ratio between them means anything.
- BirdNET carries the standing circularity caveat from experiment 0022 and is a sanity check, never the verdict; churn is triage only, 1-for-2 against the ear.
- No formal blind sitting was held. The clips in `crowgpt/results/flow-clips-lognorm/` and `crowgpt/results/flow-clips/` cost no held-out bouts, but Ben's impression was informal and unblinded. A real sitting waits on experiment 0053 closing and the bout ledger being fixed.

### What this changed

- The representation question is settled: the continuous route's precondition holds end-to-end, measured twice (arm B at 91.7%). A good representation buys nothing on its own — the risk moved exactly where experiment 0052 predicted, onto the model.
- The failure now has a precise, cheap, listener-free signature: the autocorrelation profile. Any future run must roughly double lag-1 toward 0.135 and drop lag-16 by an order of magnitude toward 0.003 before it is judged, let alone heard.
- Three methodological traps are written down: a 12k sweep that mis-ranked the arms that mattered, a churn reading initially got wrong, and an EnCodec constant that does not transfer to DAC.
- The cheap levers are spent. The one remaining idea with a mechanism behind it is classifier-free guidance conditioned on the channel embedding; capacity is argued against by the refinement result, and the conditioning-asymmetry excuse was retracted. Whether to continue is Ben's call.
