# 0026 — Density, recording quality, or the model?

0025 ended with "the model is not bad at crow sounds, it is bad at making enough
of them" — generated clips with 2+ units rated 5/5 good, those with 0-1 rated
0/3. Ben immediately named the confound: the archive corpus is full of low-quality
single-bout recordings, so density and recording quality are tangled.

The archive's A-E ratings cannot separate them — 2% of the corpus joins to one,
and those are 245 A's against 5 C's and a single D. So the recording was held
constant instead: 14 pairs, two bouts from **the same file**, one single-unit and
one with 3+, durations matched within 0.6 s. Same mic, bird, distance, noise
floor, day. Plus 10 generated single and 10 generated multi.

## The answer: none of the above. It is the model.

| | real | generated | Fisher p |
|---|---:|---:|---:|
| single-unit | 11/14 (79%) | 2/10 (20%) | **0.011** |
| multi-unit | 14/14 (100%) | 4/10 (40%) | **0.0016** |

**Density is not the driver.** Within-pair, 11 of 14 got the identical verdict.
All 3 discordant pairs favoured the multi-unit clip and none the single, so the
direction is consistent — but on 3 discordant pairs that is McNemar p = 0.25.
Within real audio alone, single against multi is p = 0.22; within generated,
p = 0.63.

**Recording quality is not the driver either.** SNR against good-rating is
r = 0.037, p = 0.82 across all clips, and r = 0.287, p = 0.14 within real audio.
Real single-unit bouts rate 79% good on a median SNR of 4.4 dB — a poor recording
of a bird still sounds like a bird.

**The model is the driver, at both densities.** Even producing three or more
caws, it is rated good 40% of the time against real audio's 100%.

## 0025 is superseded, and the reason is a lesson

0025 measured generated multi-unit clips at 5/5 good. This measured 4/10. The
clips were drawn the same way and the listener is the same person; what changed
is the instruction. Mid-sitting Ben asked what "good" meant — "I hear one that
has caws but still sounds robotic, is that good?" — and was told that caws plus
robotic is Bad, and explicitly not to rate on how many caws he heard, since unit
count is the variable under test and rating on it would make the experiment
circular.

His standard tightened, and the generated arm fell by half. **0025's headline was
an artefact of a loose criterion**, and its numbers should not be quoted. The
durable part of 0025 is the method, not the result.

Worth keeping as a rule: a rating task needs its criterion written down before
the first clip, not clarified at clip twenty.

## What changed

- **"It sounds robotic" survives every explanation offered for it.** Not the
  fine codebooks (0024: dropping them is inaudible), not density (this), not
  recording quality (this), not capacity or regularisation (0023: 0.164 nats
  bought nothing audible), not the tokenizer's bitrate, and not a 433M or 1.4B
  pretrained base (0022). The defect is in what the model generates and nothing
  tried so far has touched it.
- **Real audio is a ceiling nobody is near.** 25 of 28 real clips rated good,
  including noisy single-caw ones. The gap is not subtle.
- **The density lead is downgraded, not dead.** Every discordant pair pointed
  the same way and 0024's count difference is real; it is just not what makes
  generated audio sound wrong. Worth revisiting with more pairs if something
  else motivates it.
- **Ben's own suggestion is the most promising untested lever**: "filtering for
  caw like sounds might work". The corpus is cut by an energy burst detector
  that 0013 measured passing 1.02 units per window even in its emptiest
  confidence band — a bootstrap, not a call detector. Training on bouts filtered
  to confidently caw-like audio has never been tried, and every model-side lever
  has now been.

## Re-running

```bash
cd crowgpt && .venv/bin/python ../experiments/0026-density-or-recording-quality/run.py
# rate the page, save into sessions/
```
