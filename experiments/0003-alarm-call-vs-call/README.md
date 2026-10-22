# Is "alarm call" acoustically different from "call", or is the model guessing?

**2026-07-26** · captures 88 (alarm) and 69 (call), both ★ kept

## Why

Two kept recordings, two verdicts from the same call-type head. Before building
anything on that distinction it was worth checking whether the signal supports
it without the model's help.

## Method

Extract individual calls from each, measure per-call duration, peak frequency,
spectral centroid, flatness (noisiness) and the fraction of energy above 2 kHz.
Then rule out the two confounds that could produce the whole difference:

1. **Distance/SNR.** 69 was recorded close, 88 is a bird ~30 m up. Degrade 69's
   SNR in steps past 88's and re-measure.
2. **Multiple birds.** 69 had three crows on a branch; overlapping voices
   broaden everything. Count amplitude sub-peaks inside each detected event.

## Result

| | 88 "alarm call" | 69 "call" |
|---|---|---|
| peak frequency | 1647 Hz | 1681 Hz |
| duration | 0.17 s | 0.37 s |
| spectral centroid | 1647 Hz | 2324 Hz |
| flatness | 0.11 | 0.29 |
| energy > 2 kHz | 7 % | 23 % |
| within-bout spacing | 0.48 s | 0.77 s |

**Same peak frequency** — same species, same register. The difference is shape.

**Confound 1 rejected, and it points the other way.** Degrading 69 past 88's SNR
raised centroid (2324→2508 Hz), flatness (0.29→0.38) and high-frequency fraction
(0.23→0.28): added noise is broadband, so it makes calls measure *harsher*. The
confound pushes opposite to the observed difference, so the real gap is if
anything larger. Duration is the one partly contaminated measure — degrading
shrank it 0.50→0.29 s as quiet tails fall below threshold — so call it ~1.7×,
not 3×.

**Confound 2 rejected.** 2 of 8 events in 69 hold two notes, versus 1 of 5 in 88.
Statistically the same. 69's calls are genuinely long single notes.

A separate check found 69's calls radiate **26.7 %** of their energy above 8 kHz,
lifting 24.1 dB during the call with envelope correlation +0.94 — real harmonic
content, not background. 88's is 1.4 %, which distance plausibly explains.

## What it changed

Confirmed the distinction is real enough to build on, and produced two warnings.

**The direction contradicts textbook expectation.** Classic ethology has
scolding/alarm as the *harsh, broadband* call. This data says 88's alarm calls
are the tonal ones. Either the head's category names do not map onto the classic
terms, or these are different call types than the labels suggest. Worth knowing
before anyone builds on the names.

**Treat the spectral measures as distance-contaminated.** Duration and rhythm are
the cleaner discriminators until there are close *and* distant recordings of both
types. Two recordings show these two clips differ; they do not establish that the
difference *is* the alarm/call distinction.

The >8 kHz finding also settled a separate question: the crow-tools denoiser runs
at 16 kHz, so it would discard a quarter of a close recording's genuine harmonic
content. Not adopted.
