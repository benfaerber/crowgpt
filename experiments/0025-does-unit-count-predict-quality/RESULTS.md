# 0025 — Does unit count predict quality?

## Overview

On ten bouts from a single recording, the listener's good/bad ratings had matched the number of detected call units perfectly, but he said it while looking at the waveforms. This experiment re-tested the relationship blind, on 40 clips with the waveform hidden until after each rating. The answer: unit count does predict quality on real audio, but as a modest gradient (Spearman ρ = 0.355, p = 0.046), not the switch the first ten clips implied. The more actionable finding was in the generated clips — the model's multi-unit output passed as good as real audio while its single-unit output failed every time — suggesting the model's failure mode is density, not timbre. (Note: experiment 0026 later superseded the generated-arm numbers, showing the loose rating criterion inflated them.)

## In depth

### Design

40 clips, one per recording, waveform flat until rated, nothing about the clip shown until after: 8 real bouts each at 0, 1, 2 and 3+ detected units, plus 8 generated clips taken as they came rather than forced into a bucket. The waveform is hidden precisely because the original 10/10 observation was made while looking at it.

### Real audio: yes, but a gradient, not a switch

| units | n | good | rate |
|---|---:|---:|---:|
| 0 | 8 | 5 | 62% |
| 1 | 8 | 6 | 75% |
| 2 | 8 | 7 | 88% |
| 3+ | 8 | 8 | 100% |

Spearman ρ = 0.355, p = 0.046 — monotonic and real, and much weaker than the first ten clips implied. Split as a binary it does not hold up at all: ≥2 units scores 15/16 against ≤1 unit's 11/16, Fisher p = 0.17. The original 10/10 correspondence was a small sample from one recording flattering a real but modest effect. Unit count predicts quality; it does not determine it — a real bout with no detected burst still sounds fine 62% of the time.

### The result worth acting on: the generated clips

| | real | generated |
|---|---:|---:|
| ≤1 unit | 11/16 good (69%) | 0/3 good (0%) |
| ≥2 units | 15/16 good (94%) | 5/5 good (100%) |

When the model produces a multi-caw bout, it passes — five out of five rated good, against real audio's fifteen out of sixteen; at two or more units there is no penalty for being generated at all. When it produces one caw or none, it fails — nought out of three, where real audio at the same density is fine 69% of the time (Fisher p = 0.058 on tiny numbers, so suggestive rather than established).

Put beside experiment 0024, which measured generated clips at 70% single-unit against real audio's 33%, the picture is coherent: the model is not bad at making crow sounds, it is bad at making enough of them. Its failure mode is density, and density is the thing it mostly produces too little of.

### Caveats, and they are not small

- n = 8 per real stratum and 1–2 per generated cell. The 5/5 and 0/3 are five and three clips. Everything here needs repeating at four or five times the size before it carries real weight.
- A forced binary on a genuinely ambiguous judgement. The listener is calibrated on caws and not on softsong or chatter, and crow rattle sounds click-y in the same way the artefact does. He was told to rate natural-versus-broken rather than caw-versus-not, but some clips sit exactly on that line.
- The zero-unit stratum is a detector artefact as much as an audio category: six of ten clips in an earlier "≤1 unit" bucket had no detected burst at all, which is a bout the segmenter cut and found nothing in.
- (Added by hindsight from experiment 0026: the generated-arm headline — 5/5 good at multi-unit — was later shown to be an artefact of a loose rating criterion. Re-measured with the criterion pinned down, generated multi-unit clips rated 4/10. The durable part of this experiment is the method, not the generated-arm numbers.)

### What changed

- The defect was recast as density, not timbre. Every previous account of "it sounds robotic" reached for spectral or codec explanations; this one is countable, visible in the waveform, and the model's own multi-unit output rated as good as real audio (a reading experiment 0026 subsequently revised).
- The model looked less broken than it had: experiment 0023 spent seven GPU-hours on capacity and regularisation for no audible gain, and experiment 0022 spent the pretrained route on the same question. Neither was aimed at density.
- The levers identified are specific and none of them is capacity: condition on unit count the way experiment 0021 conditioned on call type; or train only on multi-unit bouts; or fix `segment.py` so a bout must contain at least two bursts, which would also remove the zero-unit fragments from the corpus entirely.
- The listening instrument gained a second mode: `RatingPage` measures what quality tracks rather than whether two things can be told apart, and it hides the waveform for the same reason `DemoPage` does — the picture gives away the thing being tested.
