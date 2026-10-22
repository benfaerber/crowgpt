# Does dropping three inaudible codebooks make the model better?

## Overview

Experiment 0024 had measured that the last three of the codec's eight codebooks are inaudible when replaced with random draws, implying roughly 61% of the attention compute per bout was being spent on stages a listener cannot hear. This experiment trained two models on only five codebooks — one matching the incumbent's size and one spending the savings on capacity — and rated them blind against the incumbent. The answer was a sharp no: both five-codebook models scored far worse than the incumbent, and the two sizes scored identically, ruling out capacity again. The sitting also exposed a larger problem with the rating instrument itself: the same unchanged model moved 33 points between two consecutive sittings while the real-audio anchor did not move at all.

## In depth

### Method

96 blinded trials in one sitting, four arms rated together. `k5_matched` is `model-fair-k8`'s exact recipe trained at five codebooks (16.6M parameters); `k5_bigger` spends the sequence saving on capacity (41M parameters). Generation fills stages 5–7 from the measured marginal distribution and decodes at eight codebooks, so bitrate is held constant and only the model moves. Both arms were rated against the incumbent (`fairk8`) and a real-audio anchor in the same sitting.

### Results

| arm | good | rate | 95% CI |
|---|---|---|---|
| real | 22/24 | 0.92 | [0.79, 1.00] |
| fairk8 (incumbent) | 13/24 | 0.54 | [0.33, 0.75] |
| k5-bigger (41M) | 4/24 | 0.17 | [0.04, 0.33] |
| k5-matched (16.6M) | 4/24 | 0.17 | [0.04, 0.33] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| fairk8 − k5-matched | +0.38 | [+0.12, +0.62] | resolved |
| fairk8 − k5-bigger | +0.38 | [+0.12, +0.62] | resolved |
| k5-bigger − k5-matched | +0.00 | [−0.21, +0.21] | not resolved |

Five codebooks is much worse, and the interval excludes zero. The compute saving is real but the model does not convert it into quality. Capacity bought nothing: 41M and 16.6M scored identically at 4/24 each. Experiment 0023 had ruled capacity out at the original sequence length; the argument that it deserved a retest at a shorter one was tried here and withdrawn.

### Why it probably failed

The risk was flagged in advance in the experiment's own header: 0024's inaudibility result was collected on the incumbent's output, and a five-codebook model is a different distribution. 0024 replaced stages 5–7 of a model that had learned them; here the model never saw them, so its coarse codes are free to drift somewhere the independent marginal fill does not sit on top of. A separable, cheap follow-up was noted: take `fairk8`, keep its first five rows, fill 5–7 from the same marginal, and rate that — worth doing before this null is quoted as "short sequences do not help".

### The bigger finding: the instrument grades against company

`fairk8`, unchanged weights, was rated in two consecutive sittings:

| | 0037 | 0038 |
|---|---|---|
| fairk8 | 0.21 | 0.54 |
| real anchor | 0.92 | 0.92 |

The real anchor did not move and the model moved 33 points, so the anchor does not protect cross-sitting comparisons. Across every repeated arm in the series, when an arm's rank inside its sitting changed, its score moved with it (EnCodec-32 fell 13 points when its rank fell; fairk8 rose 33 when its rank rose; DAC-24 held rank and moved only 5). That is a contrast effect — the listener grades each clip against the company it keeps — and it is much larger than 0023's 8.3-point session drift and larger than most of the model effects the project has been chasing.

Within-sitting comparisons survive, so this experiment's own result stands. Cross-sitting absolute rates do not, which retires 0037's claim that generated output "never left [0.15, 0.25]" and weakens the cross-sitting ladder assembled in 0030.

### Caveats

The blinded rating measures the pipeline's output as heard by one listener; the follow-up separating the marginal fill from the K=5 training was proposed but not run here.

### What this changed

- Shorter sequences do not help, at least not this way; the 61% compute saving identified by 0024 is real and unclaimable by this route.
- Capacity is now ruled out twice, at two sequence lengths, on two model sizes each, and should stop being proposed.
- 0024's inaudibility does not transfer to a model trained without the stages.
- Every future sitting needs a fixed reference arm set — cheapest fix is keeping the real anchor and the standing incumbent in every sitting.
- The stronger fix is to stop asking for absolute ratings and move to paired forced choice, which became the next tooling job (experiment 0041).
