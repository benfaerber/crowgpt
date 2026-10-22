# Can any sampling knob reach real audio's coarse-codebook churn?

*(This folder has no README.md; this account is drawn from the docstring in `run.py` and the numbers in `results.json`.)*

## Overview

Experiment 0046 found the mechanism behind Ben's "crow + modem" description of generated audio: the generator holds coarse codec codes too long, changing its stage-0 code on about 80% of adjacent frame pairs where real audio changes on 87%. Half of that gap comes from top-k sampling truncation; the other half is the model's own. This experiment swept five sampling knobs — temperature, top-k, top-p, min-p and a repeat penalty — to see whether any setting could bring generated churn onto real audio's 0.868 target. A repeat penalty of 1.05 landed almost exactly on target (stage-0 churn 0.8655, a gap of only −0.0025), so sampling alone can reach real churn. Because churn is a mechanism and not a proof of audibility, the outcome is a shortlist that has earned a listening sitting, not a change to the sampling default.

## In depth

**Why sweep at all.** As the `run.py` docstring puts it, this was the first idea the project could triage for free: every previous candidate cost a night of GPU and a sitting of Ben's ears before anyone knew whether it did anything, while churn costs two minutes and needs no listener. Each knob had a reason to be included:

- **temperature** — the blunt instrument, included as the control every other knob has to beat.
- **top_k** — the truncation experiment 0046 already implicated; swept rather than just on/off because experiment 0044's sitting could not resolve 200-versus-none and the useful question may be "how much".
- **top_p** — nucleus sampling widens exactly where the model is uncertain and narrows where it is confident; a repeat happens where the model is confident, which is where this cuts hardest.
- **min_p** — keeps ids above a fraction of the top id's probability, the one knob whose threshold moves with the model's confidence, which is the shape of the defect.
- **repeat_penalty** — divides the logit of the code the same stage emitted in the previous frame; the only knob aimed at the defect itself rather than at the distribution's shape.

**The target is not maximum churn.** Real audio's stage-0 churn is 0.868 (measured in experiment 0046), and a knob that overshoots is making the stream jitter, which has its own sound and is not obviously better. The score is the absolute distance from 0.868, penalising overshoot exactly as much as stickiness. Each arm generated 40 clips of at least 40 frames from the `model-fair-k8` checkpoint; clips shorter than that were discarded and counted as fragments.

**Result**, from `results.json`, ordered by distance from the 0.868 target:

| arm | stage-0 churn | gap vs real | mean churn | fragments |
|---|---|---|---|---|
| **repeat 1.05** | **0.8655** | **−0.0025** | 0.9651 | 10 |
| no truncation | 0.8555 | −0.0125 | 0.9611 | 9 |
| temperature 1.1 | 0.8864 | +0.0184 | 0.9686 | 11 |
| top_k 500 | 0.8486 | −0.0194 | 0.9631 | 8 |
| top_p 0.99 | 0.8337 | −0.0343 | 0.9592 | 10 |
| temperature 1.2 | 0.9071 | +0.0391 | 0.9772 | 10 |
| baseline top_k=200 | 0.8194 | −0.0486 | 0.9538 | 9 |
| repeat 1.15 | 0.9300 | +0.0620 | 0.9785 | 10 |
| repeat 1.15 no-topk | 0.9321 | +0.0641 | 0.9844 | 10 |
| top_p 0.95 | 0.7720 | −0.0960 | 0.9444 | 6 |
| repeat 1.30 | 0.9640 | +0.0960 | 0.9884 | 10 |
| top_k 50 | 0.7581 | −0.1099 | 0.9279 | 9 |
| min_p 0.02 | 0.7130 | −0.1550 | 0.8971 | 10 |
| min_p 0.05 | 0.6238 | −0.2442 | 0.8481 | 8 |

A mild repeat penalty (1.05) is the standout, essentially closing the gap. Removing top-k truncation recovers about three quarters of it, consistent with 0046's finding that top-k owns roughly half of the original gap. The knobs that narrow the distribution — smaller top-k, top-p 0.95, and min-p at either setting — all make the stickiness substantially worse, with min_p 0.05 the worst arm in the sweep at 0.6238. Stronger repeat penalties (1.15, 1.30) overshoot into jitter, which the design deliberately penalises.

**A trap worth recording.** The sampler in `run.py` is a deliberate copy of `Sampler.tokens` rather than an edit to the shipped `sample.py`, so nothing in the source tree changed before any knob was known to be worth having. The copy initially kept the model's duration-bucket token in the code grid, which shifts every codec token by one position and makes every arm's churn read about 0.99. The baseline arm caught it: it read 0.992 where experiment 0046 had measured the identical setup at 0.801. With the fix, this run's baseline came out at 0.8194.

**What this cannot decide.** Churn is a mechanism, not audibility. Experiments 0023 and 0027 both moved an offline number for a listening difference of zero, and experiment 0044 could not hear the top-k change this predicts. So the output of this sweep is a shortlist that has earned a sitting — headed by repeat 1.05 — and never a change to the sampling default. No default was changed by this experiment.
