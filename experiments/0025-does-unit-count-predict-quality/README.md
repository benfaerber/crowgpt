# 0025 — Does unit count predict quality?

On ten bouts from a single recording, Ben's good/bad split matched the burst
count perfectly: every clip he called bad held one unit, every good one held two
to four. He said it while looking at the waveforms, which is exactly why this
page hides them.

40 clips, one per recording, waveform flat until rated, nothing about the clip
shown until after: 8 real bouts each at 0, 1, 2 and 3+ detected units, plus 8
generated taken as they came rather than forced into a bucket.

## Real audio: yes, but it is a gradient, not a switch

| units | n | good | rate |
|---|---:|---:|---:|
| 0 | 8 | 5 | 62% |
| 1 | 8 | 6 | 75% |
| 2 | 8 | 7 | 88% |
| 3+ | 8 | 8 | 100% |

**Spearman ρ = 0.355, p = 0.046.** Monotonic and real, and much weaker than the
first ten clips implied. Split as a binary it does not hold up at all: ≥2 units
scores 15/16 against ≤1 unit's 11/16, Fisher p = 0.17.

So the 10/10 correspondence was a small sample from one recording flattering a
real but modest effect. Unit count predicts quality. It does not determine it —
a real bout with no detected burst still sounds fine to him 62% of the time.

## The result worth acting on is in the generated clips

| | real | generated |
|---|---:|---:|
| ≤1 unit | 11/16 good (69%) | **0/3 good (0%)** |
| ≥2 units | 15/16 good (94%) | **5/5 good (100%)** |

**When the model produces a multi-caw bout, it passes.** Five out of five rated
good, against real audio's fifteen out of sixteen. At two or more units there is
no penalty for being generated at all.

**When it produces one caw or none, it fails.** Nought out of three, where real
audio at the same density is fine 69% of the time — Fisher p = 0.058 on tiny
numbers, so suggestive rather than established.

Put beside 0024, which measured generated clips at 70% single-unit against real
audio's 33%, the picture is coherent: **the model is not bad at making crow
sounds, it is bad at making enough of them.** Its failure mode is density, and
density is the thing it mostly produces too little of.

## Caveats, and they are not small

- **n = 8 per real stratum and 1–2 per generated cell.** The 5/5 and 0/3 are
  five and three clips. Everything here needs repeating at four or five times
  the size before it carries real weight.
- **A forced binary on a genuinely ambiguous judgement.** Ben has said he is
  calibrated on caws and not on softsong or chatter, and crow rattle sounds
  click-y in the same way the artefact does. He was told to rate natural-versus-
  broken rather than caw-versus-not, but some clips sit exactly on that line.
- **The zero-unit stratum is a detector artefact as much as an audio category.**
  Six of ten clips in an earlier "≤1 unit" bucket had no detected burst at all,
  which is a bout the segmenter cut and found nothing in.

## What changed

- **The defect is density, not timbre.** Every previous account of "it sounds
  robotic" reached for spectral or codec explanations. This one is countable, it
  is visible in the waveform, and the model's own multi-unit output is rated as
  good as real audio.
- **The model is less broken than it looked.** 0023 spent seven GPU-hours on
  capacity and regularisation for no audible gain, and 0022 spent the pretrained
  route on the same question. Neither was aimed at density.
- **The levers are specific and none of them is capacity.** Condition on unit
  count the way 0021 conditioned on call type; or train only on multi-unit bouts;
  or fix `segment.py` so a bout must contain at least two bursts, which would
  also remove the zero-unit fragments from the corpus entirely.
- **The listening instrument now has a second mode.** `RatingPage` measures what
  quality tracks rather than whether two things can be told apart, and it hides
  the waveform for the same reason `DemoPage` does — the picture gives away the
  thing being tested.

## Re-running

```bash
cd crowgpt && .venv/bin/python ../experiments/0025-does-unit-count-predict-quality/run.py
# rate the page, save into sessions/, then re-run the analysis in this README
```
