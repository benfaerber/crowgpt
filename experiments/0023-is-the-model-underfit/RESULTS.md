# 0023 — Is the model underfit?

## Overview

The crow-call generator's training had never had a trustworthy train-versus-validation comparison, so every decision about model capacity and regularisation was being made blind. This experiment fixed the measurement, ran a five-arm sweep, and found the model unambiguously underfit: it fits its own training data no better than unseen data, removing dropout only helps, and a silently halved batch size was the biggest single loss on the table. But when the improved checkpoint was judged by a human listener, the 0.164-nat gain in validation loss produced no audible improvement at all — and along the way the listening test itself was shown to drift by more between sittings than the model effect being measured.

## In depth

### The broken measurement, fixed first

The training history had recorded `loss.item()` from a single training minibatch with dropout 0.25 still active, and compared it against a 20-batch mean under `eval()`. Those are two different measurements rather than a train/val gap, which is why several recorded "gaps" came out negative — including a run where train sat above val at step 38,000. `Trainer.evaluate` now scores both splits identically: same batch count, both under `eval()`, with its own batcher so scoring cannot perturb training's sampling order. The cost is twenty extra forward passes per eval, well under 1% of runtime. The old figure is preserved in each row as `train_minibatch` so older histories still line up.

### The sweep

Five arms, 40,000 steps, same seed, one knob moved per arm. Every arm early-stopped at 38,000 steps, so they are directly comparable.

| arm | best val | final gap (val − train) | batch | minutes |
|---|---:|---:|---:|---:|
| baseline (dropout 0.25) | 4.7021 | −0.008 | 16 | 72 |
| dropout 0.10 | 4.6573 | +0.011 | 16 | 69 |
| dropout 0.00 | 4.6230 | +0.036 | 16 | 67 |
| batch 32 | 4.6043 | +0.104 | 32 | 140 |
| anneal to zero | 4.7018 | −0.011 | 16 | 69 |

Three readings:

- **The baseline gap is −0.008.** After 38,000 steps the model is no better on data it trained on than on data it has never seen. There is nothing to regularise against, so dropout was insurance against a risk that does not exist.
- **Removing dropout monotonically improves validation loss** — 4.7021 to 4.6573 to 4.6230 as dropout goes 0.25 to 0.10 to 0.00. That is the clean signature of a model that cannot fit its own training set.
- **Unclipping the batch helps most.** A requested batch of 32 had been silently running as 16 for the whole project, clipped by a `budget = 240_000_000` constant nobody chose. Restoring it gives the best validation loss of the five (4.6043) and the first honest positive gap (+0.104).

Baseline to best is 0.098 nats, about 0.14 bits per token — real, and not enormous. One measured null: the learning-rate floor does nothing. Annealing the cosine to zero instead of settling at 10% of peak scores 4.7018 against the baseline's 4.7021, a difference of 0.0003. That knob is closed.

### Then the ear disagreed — and then the instrument did

Validation loss is not the ear, so the combined arm (batch 32 + dropout 0, best val 4.538) was put through the 60-trial listening sheet against the standing checkpoint `model-d384-6k` (best val 4.711). In the listening test, chance is the target, so a higher correct rate is worse for the model. Across three sittings:

| sitting | correct | 95% CI | d′ | fooled him |
|---|---:|---:|---:|---:|
| old model, Fri 21:33 evening | 75.0% | [63, 85] | 1.34 | 10/30 |
| new model, Sat 12:15 morning | 88.3% | [80, 97] | 2.27 | 4/30 |
| old model, Sat 12:29 morning (control) | 83.3% | [73, 92] | 1.91 | 7/30 |

The first two rows read like a quality regression: the better-loss model fooled the listener four times out of thirty where the old model managed ten. But Ben objected that the sittings were an evening and a morning apart, and the control row proves him right: identical weights scored 75.0% in the evening and 83.3% the next morning — 8.3 points of listener, not model, roughly two thirds of the apparent regression. Practice is the likely mechanism; the evening notes end with the tell ("all the bad ones seem to have the xelophone / modem sounds in them") that was then applied the next day. Morning against morning, the comparison is 88.3% vs 83.3%, paired +0.067 [−0.133, +0.233] — not significant.

The question was settled the same afternoon with an interleaved sheet: 60 trials, 30 per checkpoint, shuffled together so practice and time of day apply equally to both.

| checkpoint | correct | 95% CI | d′ | fooled him |
|---|---:|---:|---:|---:|
| model-d384-6k | 86.7% | [73, 97] | 2.09 | 3/15 |
| batch-32-dropout-0 | 83.3% | [70, 97] | 1.79 | 2/15 |

Paired on the 15 matched conditions: mean difference 0.000, CI [−0.27, +0.27]. He got exactly the same number right for each model. The apparent effect shrank monotonically as the confound was removed — 13.3 points across an evening and a morning, 5.0 points morning-to-morning, 0.0 within a single sitting — which is what a confound looks like when it is taken out properly. The interval is still ±0.27 on 15 pairs, so a moderate difference cannot be excluded; what can be excluded is the one this experiment was built to find.

### Caveats

- Validation loss is measured over the whole training corpus, which is mostly seeded archive audio; the listening test is the only judge of whether output sounds like a crow, and it is a single listener.
- The interleaved comparison has only 15 pairs per checkpoint, so its ±0.27 interval leaves room for a moderate audible difference.

### What changed

- "Underfit or overfit" is settled: the model is capacity-starved, not over-regularised — the same direction experiment 0019 pointed from the dead-codebook side.
- Two defaults are now known to be wrong: `dropout=0.25` costs about 0.08 nats, and `memory_budget` had been halving the batch since the beginning. Neither should stay.
- The learning-rate floor is closed as a measured null.
- More capacity is *not* the evidenced next move after all: the knobs did exactly what the loss said they would and the output got no better to a person. The lever is more likely the objective or the tokenizer than raw parameter count.
- Rank checkpoints by ear, not by validation loss — loss has now failed once as a proxy for quality, though it stays useful for catching breakage.
- A single listener across two sittings is a confounded instrument. Eight points moved on identical weights between an evening and a morning. Future cross-session comparisons need interleaved sheets or a same-session control; this nearly produced a wrong conclusion in this very experiment, and the objection came from Ben rather than from the analysis.
