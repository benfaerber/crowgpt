# Did the stranger get a different call?

## Overview

On 2026-07-31 a stranger walked ahead of the recordist — who feeds these crows weekly — for a full 93-second recording, and by ear the crows sounded far angrier at her than at him. Crows recognising individual humans is the headline result in the literature, so this is the flagship question of the whole project, and this was the first recording where a stranger and a known human were separable on the same span. The measured answer: it cannot be told from this data, and the apparent difference is mostly recording quality. The stranger recording did show call units nearly twice as long and 2.5× the calling rate, but artificially noising it down to the control recording's signal-to-noise level destroyed roughly half of both gaps, and the measures that seemed to survive moved in exactly the direction added noise pushes them. With only one stranger recording in existence, "stranger" and "that particular walk" are the same variable — the recordist's ear is not contradicted, just not yet testable.

## In depth

### Method

Alarm-call spans, human labels only, on ★kept captures. Segmented with `crowgpt.segment.Segmenter` at its packaged 12 dB — not a new detector; experiment 0013 section E swept 6/8/12 dB and only 12 passed the control, and `FUTURE.txt` flags re-tuning it as the trap. Per unit: duration, peak frequency, spectral centroid, flatness, and fraction of energy above 2 kHz — experiment 0003's feature set, so the two are readable against each other.

The comparison is capture 113 (stranger present) against capture 114 (recordist alone), 32 minutes later, same fleet, same mic, same block — the closest thing to a control the corpus has, and still not a controlled one: 5–20 m against under 5 m. Two confound checks, because with one stranger recording the confounds are the whole result: a correlation of detected units/sec against band SNR across recordings (underpowered at n=5 and reported as such), and the decisive one — noising the stranger recording down past the control's SNR and re-measuring, so that whatever gap survives is not made of recording quality.

### Results

Alarm spans, by recording:

| cap | group | dist | SNR dB | secs | units | units/s | dur s | peak Hz | flatness |
|---|---|---|---|---|---|---|---|---|---|
| 100 | known | 5–20 m | — | 45.0 | 27 | 0.60 | 0.104 | 1578 | 0.089 |
| 103 | known | 20–50 m | 19.3 | 6.0 | 2 | 0.33 | 0.096 | 1476 | 0.094 |
| 114 | known | under 5 m | 16.5 | 18.0 | 4 | 0.22 | 0.128 | 1618 | 0.111 |
| **113** | **stranger** | 5–20 m | 25.6 | 87.0 | 49 | 0.56 | **0.224** | 1546 | 0.101 |

(Capture 100's band SNR is undefined — `p99/p10` divides by zero on a digitally silent frame; a real property of that recording, excluded from the correlation.)

Raw, capture 113's call units are nearly twice as long as 114's (0.224 s vs 0.128 s) and it calls at 2.5× the rate. That looks like the ear was right. Then the degradation control:

| | SNR dB | units | units/s | dur s | peak Hz | flatness | >2 kHz |
|---|---|---|---|---|---|---|---|
| stranger | 25.6 | 49 | 0.56 | 0.224 | 1546 | 0.101 | 0.080 |
| stranger, degraded | 16.4 | 25 | 0.29 | 0.168 | 1594 | 0.127 | 0.100 |
| recordist alone | 16.5 | 4 | 0.22 | 0.128 | 1618 | 0.111 | 0.057 |

Noising 113 down to 114's SNR destroyed 49% of its detected units and half the rate advantage. The rate difference is largely the range, not the birds. How much of each gap survives:

| measure | raw gap | degraded | kept | reading |
|---|---|---|---|---|
| unit duration | +0.096 | +0.040 | 42% | mostly SNR |
| peak frequency | −72.4 | −24.7 | 34% | mostly SNR |
| flatness | −0.011 | +0.015 | −145% | reverses |
| >2 kHz fraction | +0.024 | +0.043 | +183% | grows |

The last two need care, and this is where the experiment differs from experiment 0003. Added noise is broadband, so it raises flatness and high-frequency fraction. In 0003 the confound happened to push opposite to the observed difference, which made that result conservative. Here it pushes with it: the two measures that appear to "survive" moved away from the control under degradation, which is the noise being added, not the birds. Only duration and peak frequency moved toward the control, and both lost most of their gap. Every measure behaves as recording quality predicts; nothing is left that points at the stranger.

### And it could not have been tested anyway

One stranger recording (49 units) against three known recordings (33 units). Experiment 0006 makes the case that folds must hold out whole recordings, because two caws from one bout are nearly the same data point — and with one stranger recording, the fold that holds it out holds out the class. No accuracy and no p-value are reported, following 0006's refusal: a number from this much data would be noise wearing a result's clothes. "Stranger" and "that particular walk" are currently the same variable, and no amount of analysis separates them. Only more encounters can.

### What it changed

**Nothing was concluded about crows, and that is the result.** The ear is not contradicted and not confirmed; the measurement cannot reach it yet. Three things it did change:

1. **Call rate is off the table as evidence between recordings at different ranges.** Half of 113's rate advantage evaporated under a controlled 9 dB of noise. Any future claim about calling more or faster needs matched range or this control run beside it.
2. **The collection target now has a number.** Experiment 0006 set the general target — independent sessions are the binding constraint, not total calls. For stranger-vs-known specifically the floor is 2 stranger recordings before anything is testable at all, with 0006's feasibility band of 10+ sessions per class before a number means much. One walk behind one stranger, on 2026-07-31, is the entire stranger corpus.
3. **Record range with the encounter, deliberately.** `distance_band` is already collected and is what made the control possible. The strangers worth recording are the ones at the same distance band as an existing known-human recording — a stranger at 20–50 m will not be comparable to anything.

The honest field instruction: when a stranger walks the turf, record it, and try to be as far from the birds as you were the last time you recorded yourself.

### Re-running

`pipelines/representation/.venv-birdnet/bin/python experiments/0016-did-the-stranger-get-a-different-call/run.py` — writes `results.json` beside this file. The corpus is gitignored, so the numbers here are the durable part.
