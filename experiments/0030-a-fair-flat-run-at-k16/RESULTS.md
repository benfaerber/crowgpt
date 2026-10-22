# 0030 — Does flat-at-12-kbps still lose once the two known bugs are gone?

## Overview

An earlier run (experiment 0018) had concluded that training a flat crow-call generator at 12 kbps (16 codebooks) was worse than 6 kbps (8 codebooks), but that run carried two training defects: a batch size silently clipped to about 4 and a dropout of 0.25 later measured as wrong for this corpus. This experiment reran the comparison fairly — two arms with an identical corrected recipe, differing only in bandwidth — and asked whether 12 kbps still loses. It does: in a blind listening sitting, the 16-codebook model scored 0.15 good-rate against 0.25 for its 8-codebook control, a difference that runs the wrong way for 12 kbps and is not statistically resolvable. The earlier conclusion was right even though its reasoning rested on a buggy run, and the fallback plan of flat high-bandwidth modelling is now a collected null rather than an open option.

## In depth

### Method

Two training arms, identical recipe, one difference. The incumbent model had trained at dropout 0.25 and effective batch 16, so comparing a new flat-K16 run against it would have moved bandwidth, dropout and batch size together. Instead a matched control (`model-fair-k8`) was trained at eight codebooks with everything else held equal, making bandwidth the only variable:

| | flat-k16 | fair-k8 (control) | incumbent (reference) |
|---|---|---|---|
| codebooks | 16 (12 kbps) | 8 (6 kbps) | 8 (6 kbps) |
| architecture | d384 L8 H6 | d384 L8 H6 | d384 L8 H6 |
| effective batch | 18 (6 × 3) | 18 (18 × 1) | 16 |
| dropout | 0 | 0 | 0.25 |
| steps | 30,000 | 30,000 | — |

Gradient accumulation had to be built first: the logits tensor grows fourfold from 6 to 12 kbps, and the d384/L8 shape fits a micro-batch of 6 at K=16 on the 4070 Ti (it OOMs at 8). A guard aborted the run if the memory-budget heuristic clipped either arm off the shared effective batch of 18. A synthetic timing benchmark also proved wrong by about 3× — the batcher pads to the longest sequence in the batch, not to the block size — so the step budget was taken off the live run.

The run took 3.8 hours on 2026-08-01 (K=16: 2.7 h; K=8 control: 61 min). Both arms found their best validation loss around step 26,500–27,000 and then oscillated, so neither is meaningfully undertrained. Validation losses (4.5874 and 5.1346) are not compared across arms — different vocabularies and sequence lengths make them different quantities.

### Bits recovered over the codec marginal

| stage | K=16 arm | K=8 control | | stage | K=16 arm |
|---|---|---|---|---|---|
| 0 | 3.423 | 3.278 | | 8 | 1.527 |
| 1 | 2.854 | 2.765 | | 9 | 1.438 |
| 2 | 2.801 | 2.688 | | 10 | 1.314 |
| 3 | 2.443 | 2.403 | | 11 | 1.245 |
| 4 | 2.208 | 2.119 | | 12 | 1.183 |
| 5 | 2.001 | 1.883 | | 13 | 1.072 |
| 6 | 1.818 | 1.677 | | 14 | 1.024 |
| 7 | 1.661 | 1.460 | | 15 | 0.939 |

Coarse mean +2.401, fine mean +1.218. The plan's automated gate ("beats the codec marginal by more than 0.3 bits") passes comfortably — and a prediction from experiment 0028, that the near-white fine-stage residual would be hard to model, did not survive: the model recovers 0.94 to 1.53 bits in stages 8–15.

But the K=8 control shows the gate cannot mean what the plan wants. At K=8 the model recovers 1.883, 1.677 and 1.460 bits in codebooks 5, 6 and 7 — and experiment 0024 established by ear that replacing exactly those three codebooks with draws from the codec's own marginals is inaudible. A stage can recover roughly 1.5–1.9 bits and still carry nothing a listener can hear, and the planned extender's target stages recover 0.94–1.53 bits, a band lying entirely below the one already shown to be inaudible. The honest counter-argument, left open: 0024 removed three stages while the extender would add eight, and bits recovered per stage is not obviously additive in perceptual terms.

### Calibration and density

Cross-entropy equals predictive entropy at every one of the 16 stages (overconfidence between −0.05 and +0.02), and the loss-minimising temperature is 1.00 at every stage, in both arms. The model is correctly uncertain in the fine codebooks, not blurry — the same flat-calibration verdict experiment 0019 found at 8 codebooks, now confirmed at 16. Per-stage temperature is dead as an idea at both sizes.

Units per bout (20 clips per arm, same segmenter at the shipped 12 dB):

| arm | mean units | single-unit share |
|---|---|---|
| real | 3.70 | 20% |
| flat-k16 | 2.60 | 35% |
| fair-k8 | 2.35 | 30% |
| incumbent (0024) | 1.37 | 70% |

The density gap experiment 0024 measured has roughly halved with no change to the loss — this is the training-recipe correction alone. The proposed burst-weighted loss (WP4) would now be chasing a much smaller gap and should be re-costed. At n=20 per arm, flat-k16 versus fair-k8 (2.60 vs 2.35) is not a difference this can resolve.

### The blind sitting (rated 2026-08-02)

60 trials, waveform hidden, 20 clips per arm. Session in `crowgpt/results/listening/flat-k16-0030/`.

| arm | good | rate | 95% CI |
|---|---|---|---|
| real | 17/20 | 0.85 | [0.70, 1.00] |
| fair-k8 | 5/20 | 0.25 | [0.10, 0.45] |
| flat-k16 | 3/20 | 0.15 | [0.00, 0.35] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| real − flat-k16 | +0.70 | [+0.45, +0.90] | resolved |
| real − fair-k8 | +0.60 | [+0.35, +0.85] | resolved |
| flat-k16 − fair-k8 | −0.10 | [−0.35, +0.15] | not resolved |

Twelve kbps does not beat six at a matched recipe; the point estimate runs the wrong way and the difference is unresolved.

Because real audio scored 17/20 in both back-to-back sittings, the control licensed a cross-sitting decomposition that was otherwise pre-committed against (experiment 0023 had measured 8.3 points of listener drift between sittings):

| | good-rate | cost against real |
|---|---|---|
| real | 0.85 | — |
| codec K=16 (0028) | 0.65 | −0.20 |
| codec K=8 (0028) | 0.45 | −0.40 |
| model fair-k8 | 0.25 | −0.60 |
| model flat-k16 | 0.15 | −0.70 |

Both defects are real and the codec is the larger single one: the round-trip at 6 kbps costs 40 points, and the generator a further 20 on top (+0.20, CI [−0.10, +0.50], not resolvable at this n). Fixing either alone is not enough — a perfect generator on this tokenizer inherits a 40-point deficit.

### Caveats

The 10-point gap between the two model arms, like the 20-point gaps in experiment 0028, is below what 20 trials per arm can resolve; settling them would need roughly 70–95 trials per arm (three to five sittings). All listening material here is codec round-trips and model generations over the corpus, so these are pipeline measurements, not findings about crows.

### What this changed

- The automated "+0.3 bits over marginal" kill gate is dead as a discriminator; any future version must be calibrated against a listening result, not zero.
- The prediction that near-white fine stages would be hard to model was wrong — the entropy of a residual says little about how much is predictable from context.
- Per-stage temperature is dead at 16 codebooks as well as 8.
- WP4 (burst-weighted loss) lost most of its premise to the recipe fix and should be re-costed.
- Diagnosis point 4 is closed and WP3 with it: flat-at-12-kbps had its fair attempt and still does not beat 6 kbps by ear. WP3 is done and null, not an available fallback.
- The two defects are sized on one scale, with the codec the bigger one (−40 points against −20).
- Two new trained checkpoints exist (`results/model-flat-k16`, `results/model-fair-k8`); neither is promoted and `results/model` is untouched.
