# 0014 — Can a neural codec carry a caw?

**2026-07-30** · 300 crow-positive windows, 50 per species, all from distinct recordings

## The question

Experiment 0013 found the corpus could pay for synthesising a caw and left one
thing unmeasured: whether the audio survives being turned into tokens at all.

Every practical route to generating audio goes through a neural codec — encode
to discrete tokens, model the tokens, decode back. EnCodec and its relatives are
trained on **speech and music**. A corvid call is neither. If the codec cannot
round-trip a caw then a model trained on its tokens is finished before it
starts, and no amount of training recovers what the tokenizer already threw
away.

So this is a gate, and it was built to be allowed to fail.

## Method

`facebook/encodec_24khz`, at every bandwidth it supports: 1.5, 3, 6, 12 and
24 kbps, which is 2, 4, 8, 16 and 32 residual codebooks. Nine arms on the same
300 windows, drawn stratified by species with BirdNET's own `CROW_MIN_CONF` gate
and one window per recording.

| arm | what |
|---|---|
| `native` | the file as recorded — what BirdNET confidence is measured against |
| `resample_24k` | native → 24 kHz, no codec — separates band loss from codec loss, and is the reference every spectral distance is measured from |
| `encodec_*` | the five bitrates |
| `encodec_3kbps_x2` | encoded and decoded twice, to expose artefacts that accumulate |
| `lowpass_2k` | deliberately ruined, to prove the metrics can fail |

Primary metric is **multi-resolution STFT distance** (windows 1200/240/60), not
a single log-mel — a 25 ms hop integrates away the 10–30 ms pulse structure that
carries a caw's onset, which is the first thing a codec loses. BirdNET retention
is secondary *by design*, because BirdNET was trained on archive mp3s with
heavy augmentation and is robust to the very smearing being measured. Section D
is where that caution earns its place.

Pre-registered pass criterion: retention ≥ 0.90 among windows the original
scored ≥ 0.25, median paired Δconfidence ≥ −0.05, and spectral distance no worse
than half the deliberately-ruined anchor.

## A. Resampling to 24 kHz is free

| arm | mean conf | retention | median Δconf |
|---|---|---|---|
| native | 0.752 | 1.000 | 0.000 |
| resample_24k | 0.774 | **0.987** | **+0.007** |

Throwing away everything above 12 kHz costs nothing measurable — mean confidence
goes very slightly *up*. This independently reproduces 0013's bandwidth finding
(96.8% of call units roll off below 8 kHz) by a completely different route, and
it establishes the **ceiling**: 0.987, not 1.0. No codec arm can do better than
this, and the pass criterion was written as though it could.

## B. Codec degradation is graded, and steep below 6 kbps

| bitrate | codebooks | retention | median Δconf | STFT dist | entropy (bits) |
|---|---|---|---|---|---|
| 1.5 | 2 | 0.373 | −0.512 | 1.581 | 6.3 – 7.1 |
| 3 | 4 | 0.690 | −0.192 | 1.463 | 6.3 – 7.5 |
| **6** | **8** | **0.810** | **−0.030** | **1.355** | 6.3 – 7.8 |
| 12 | 16 | 0.877 | −0.005 | 1.247 | 6.3 – 8.2 |
| 24 | 32 | 0.887 | −0.004 | 1.195 | 6.3 – 8.7 |

At 1.5 kbps the caw is destroyed — over 60% of windows stop being a corvid.
From 6 kbps the median window loses almost nothing, and by 12 kbps essentially
nothing at all (−0.005 against a −0.05 bar).

**Every codebook is doing work.** Even the 32nd residual stage sits at 6.3 bits
of a possible 10, so there is no dead stage to prune and code entropy does not
choose the bitrate. Sequence length has to.

The double round-trip is the control that behaves: 3 kbps twice drops retention
from 0.690 to 0.527, so these artefacts accumulate rather than saturating.

## C. The pre-registered criterion failed at every bitrate

Not one arm passed. Retention never reaches 0.90 — 24 kbps gets closest at
0.887 — while the spectral and Δconfidence bars are cleared comfortably from
6 kbps up.

**The bar was set badly, and in two distinct ways.**

The first is arithmetic and was entirely self-inflicted. The spectral criterion
was originally written as "within 2× the resample-only arm", but resample-only
*is* the reference all spectral distances are measured from, so its distance to
itself is zero and nothing could ever satisfy it. Every codec arm failed a check
that had nothing to do with the codec. It is now set against the ruined
`lowpass_2k` anchor instead, which all five arms clear.

The second is a real judgement error. Retention was pinned at an absolute 0.90
without knowing the ceiling, and the ceiling turns out to be 0.987 — resampling
alone costs 1.3%. Against that, 12 kbps retains 0.877 and 24 kbps 0.887, both
within about a point of the bar.

The honest statement is therefore: **the gate failed as written, and the failure
is graded rather than categorical.** Reading the numbers rather than the verdict
gives a qualified yes from 6 kbps upward. That reading was made after seeing the
data and is labelled as such.

## D. A 2 kHz lowpass beats the codec, and this is the important result

| arm | retention | median Δconf | STFT distance |
|---|---|---|---|
| `lowpass_2k` (deliberately ruined) | **0.733** | −0.190 | **4.752** |
| `encodec_3kbps` | **0.690** | −0.192 | **1.463** |

Audio with everything above 2 kHz thrown away keeps **more** BirdNET detections
than EnCodec at 3 kbps, while being **3.2× further away spectrally**. The two
metrics rank these arms in opposite directions.

The reason is that BirdNET does not care about most of what a codec damages.
Corvid calls have a median rolloff of 2,688 Hz (0013), so a 2 kHz lowpass leaves
the fundamental intact and merely dulls it; low-bitrate codec artefacts instead
smear the onsets and add structure that was never there, which is exactly what a
detector keys on.

**This retroactively justifies making BirdNET the secondary metric.** Had this
experiment been run with BirdNET retention alone — the obvious cheap design, and
the one this project already has the tooling for — it would have concluded that
a 2 kHz lowpass is a better tokenizer than a neural codec. Any future work using
BirdNET to score audio *quality* rather than audio *content* should read this
section first.

## The answer

**Qualified yes, from 6 kbps up.** The codec is not the blocker, but it is not
free either, and it sets a ceiling the model cannot exceed.

`crowgpt` uses **6 kbps / 8 codebooks**. 12 kbps is measurably better for the
codec — 0.877 retention against 0.810 — but it doubles the sequence length
(3,600 tokens per 3-second bout against 1,800) and the vocabulary, and at a
corpus of ~24,000 bouts the model is the binding constraint rather than the
tokenizer. That is a trade made deliberately and it is visible in the result:
the ceiling for anything generated through these tokens is 0.810 retention, not
0.987, which is why `crowgpt`'s judge scores real audio round-tripped through
the codec as its own arm rather than comparing generated audio to untouched
recordings.

## What changed

- **`crowgpt` tokenises at 6 kbps.** Previously an unmeasured guess; 1.5 and
  3 kbps would have been reasonable-looking choices and both destroy the call.
- **The judge gained an arm.** Because the codec ceiling is 0.810 rather than
  1.0, comparing generated audio against untouched recordings would have blamed
  the model for the tokenizer's losses. Real-round-tripped-through-the-codec is
  now scored separately and is the comparison that means anything.
- **BirdNET is no longer trusted to rank audio quality** anywhere in this
  project, on the strength of section D. It ranks a 2 kHz lowpass above a neural
  codec that is three times closer spectrally.
- **A criterion phrased as a multiple of the reference arm is always
  unsatisfiable**, which cost one full run to notice. Written down because the
  same shape of mistake is easy to repeat.
- Nothing changed about the corpus, and no re-collection is warranted: section A
  reproduces 0013's bandwidth result independently.

## Re-running

```bash
cd ../../crowgpt && make gate          # N=50 per species by default
```

About 40 minutes: most of it is BirdNET, run 9 times per window plus once per
candidate recording during selection. Needs `crowgpt/.venv` (`make venv`) and
downloads the EnCodec weights on first use. Results to `results.json`.
