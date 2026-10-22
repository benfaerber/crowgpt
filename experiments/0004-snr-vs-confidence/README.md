# Does BirdNET's confidence track background noise?

**2026-07-26** · capture 88, "Single crow morning building"

## Why

A quiet call at ~15s was missed. The recordist asked whether that meant the
microphone was inadequate. Answering it by reasoning would have been guessing:
the recording has 27 dB of unused headroom and no clipping, which says
sensitivity is not the constraint — but says nothing about whether *noise* is.

## Method

Take the call BirdNET scored 0.976 on, mix in progressively more of the same
recording's own street noise, re-score at each step. The recording's own
background rather than synthetic hiss, because it has the spectrum a directional
microphone would be rejecting.

## Result

| added street | BirdNET |
|---|---|
| none (as recorded) | **0.979** |
| 0.5× | 0.968 |
| 1× | 0.955 |
| 2× | 0.907 |
| 3.5× | 0.720 |
| 5× | **0.341** |
| 8× | **0.073** |

The missed call, as recorded: **10.9 dB band SNR → 0.098**.

Confidence collapses from 0.979 to 0.073 with nothing changed but the
background. Around the range these recordings actually sit in, roughly **2.5 dB
of extra street noise costs about 0.19 of confidence**.

## What it changed

Reversed a recommendation. I had told the recordist "the mic is not your
problem", reasoning from headroom and the absence of clipping. That was correct
about *sensitivity* and wrong about what limits detection: background noise
dominates the score, so **directionality buys detections**, not merely
nicer-sounding audio.

Revised advice: a short shotgun (Rode VideoMic Me-C) gives 3–6 dB of off-axis
rejection at 1.6 kHz, which on this curve is plausibly enough to lift a 0.183
over the 0.25 gate. A parabolic gives 10–20 dB and is the real answer for a bird
30 m up.

It also motivated the candidate tier: the pipeline drops anything under
`CROW_MIN_CONF = 0.25`, so the calls the model is worst at can never be labelled
and never enter training. Better SNR moves marginal calls above the gate;
a candidate tier catches the ones that stay below it. The two are complementary.

## Caveat

Three points on the natural curve (0.976 at 24.4 dB, 0.896 at 16.3, 0.183 at
11.0) plus one synthetic sweep, from one recording. The direction is not in
doubt; the exact dB-per-confidence figure should not be quoted as a constant.
