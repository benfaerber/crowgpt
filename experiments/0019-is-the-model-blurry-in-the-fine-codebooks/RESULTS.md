# Is the model blurry in the fine codebooks, or correctly uncertain?

## Overview

The crow-call generator samples every token at a single temperature, and no single value had ever worked for both the coarse structure of a call (its timing and contour) and its fine texture. The hypothesis was that the model might be well fitted at the coarse end and blurry at the fine end, which a per-stage temperature schedule could fix. This experiment measured the model's calibration at every codec stage and found the opposite: the model is almost perfectly calibrated everywhere, so the per-stage temperature idea is dead — cooling the fine stages would have made the output worse. The real finding is that the model's predictive power decays to nothing by stage 5, meaning three of the eight codebooks are generated at essentially chance; that is unfixable by any sampling parameter and became the concrete candidate for why the output sounds robotic.

## In depth

Run 2026-07-31 on `model-d384-6k` (18.0M parameters, best validation loss 4.7112), teacher-forced over 768 held-out sequences on CPU.

### Why

The sampling temperature's history is a fight it cannot win: 0.95 was written first; experiment 0015 measured 1.15 and cut training-set overlap from 8.7× the held-out base rate to 1.0×; then 1.0 beat 1.15 on the better-trained model by 21 points of detection, because at 1.15 bouts come out 29% short with a flattened contour. In a residual codec the first codebook carries coarse shape — duration, contour, when to stop — and the later stages carry texture, so one knob doing two jobs would force exactly that trade. Two kill conditions were written down before the numbers existed: flat calibration across stages, or fine stages that are *correctly* uncertain rather than blurry.

### Both kill conditions fired

| stage | cross-ent | predictive | codec marginal | recovered | overconf | calib T |
|---|---|---|---|---|---|---|
| 0 | 4.340 | 4.308 | 6.30 | **1.960** | +0.032 | 1.00 |
| 1 | 5.740 | 5.739 | 7.06 | 1.320 | 0.000 | 1.00 |
| 2 | 6.332 | 6.304 | 7.34 | 1.008 | +0.028 | 1.00 |
| 3 | 6.959 | 6.916 | 7.50 | 0.541 | +0.043 | 1.00 |
| 4 | 7.418 | 7.380 | 7.63 | 0.212 | +0.037 | 1.00 |
| 5 | 7.763 | 7.756 | 7.73 | **−0.033** | +0.007 | 1.00 |
| 6 | 8.043 | 8.050 | 7.80 | **−0.243** | −0.007 | 1.00 |
| 7 | 8.248 | 8.272 | 7.84 | **−0.407** | −0.024 | 1.00 |

All values are in bits; `recovered` is the codec's own marginal entropy minus the model's cross-entropy — how much the model knows that the marginal distribution does not.

**Calibration is flat at exactly 1.00 on every stage.** The temperature that minimises held-out loss does not vary, so a per-stage schedule is a global one in a costume. That alone ends the idea. **Overconfidence is roughly zero everywhere** — the largest magnitude is 0.043 bits, meaning the model's cross-entropy matches its own predictive entropy at every stage. It is neither hedging nor overclaiming: it knows exactly how uncertain it is. That is the second kill condition, and the one that matters more, because cooling a correctly-uncertain distribution does not clean it up — it makes the sampler re-pick the same arbitrary residual code repeatedly, which is periodic, and periodic is what robotic sounds like.

### The finding that actually matters

Predictive power decays monotonically — 1.96, 1.32, 1.01, 0.54, 0.21 bits recovered — and then goes negative. At stages 5, 6 and 7 the model predicts the residual no better than drawing from the codec's marginal distribution. So three of the eight codebooks in every generated token are close to noise wearing the shape of real statistics: a decent coarse signal with structured-looking randomness laid on top. That is a concrete, mechanical candidate for the "cyborg" sound, and no sampling parameter can fix it, because the model is right about its own uncertainty — the information simply is not there.

One honest caveat on the sign: the marginal vector comes from experiment 0014, measured on BirdNET-gated windows rather than this corpus, so "negative" should be read as "at or below the marginal" rather than as a precise deficit. The monotone decay across stages is unambiguous either way.

### EOS is not the problem, and the obvious reading of it is wrong

Sampling keeps the top 200 token ids, so an EOS ranked below that cannot be emitted. Pooled over every frame boundary, EOS is inside the top 200 only 35.4% of the time, median rank 304 — which looks damning and is not. A 2.2 s bout has about 165 frame boundaries and exactly one is the end; a model that ranked EOS highly at all of them would be broken. Split apart:

| | median rank | inside top-200 | n |
|---|---|---|---|
| the boundary the bout really ends on | **0** | **99.9%** | 768 |
| boundaries mid-bout | 304 | 35.4% | 106,070 |

At the true ending EOS is the single most likely token, essentially always. Top-k is not deleting stopping opportunities, and the bout-length behaviour blamed on temperature since 0015 is not a top-k artefact. This was recorded because the pooled number is the one a quicker version of the experiment would have reported, and it would have sent someone to fix a sampler that was working correctly.

### Per-species loss does not settle the balance question

| species | bits/token |
|---|---|
| common-raven | 6.562 |
| hooded-crow | 6.652 |
| carrion-crow | 6.674 |
| american-crow | 6.782 |
| eurasian-jackdaw | 7.205 |
| rook | 7.252 |

The prediction going in was that American Crow would be cheapest, which would have closed the `--balance` question on the spot. It is not cheapest — it sits fourth of six, despite being 70.6% of the corpus. So the balance question stays open, and per-token difficulty does not track the detection ranking from experiment 0018 (where American Crow is at 99% of its codec ceiling and Hooded Crow at 48%). Two different quantities; do not substitute one for the other.

### Caveats

These are teacher-forced measurements over held-out sequences from the training corpus, which is dominated by archive audio; they describe the model and its tokenizer, not any particular birds. The negative-`recovered` sign depends on a marginal measured on a different window sample, as noted above.

### What changed

- **Killed per-stage temperature before any sampler code was written** — the leading candidate fix, which would have cost a night of sweeps. Both pre-registered kill conditions fired independently.
- **Killed cooling the fine stages at all**, the intuitive move that would have made the output worse by making the residual periodic.
- **Killed the top-k-is-eating-EOS theory** before anyone changed the sampler, and recorded the misreading that would have caused it.
- **Redirected the work toward capacity or the objective at the fine end.** Three of eight codebooks carry no learned signal — agreeing with experiment 0017's conclusion that what remains for audio quality is the model or the objective, not the representation, now with a number attached and a location.
- **Left `--balance` open** rather than closing it on a prediction that turned out wrong.
