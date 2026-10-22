# 0014 — Can a neural codec carry a caw?

## Overview

Generating audio with a model like CrowGPT means first turning the audio into discrete tokens with a neural codec, and codecs like EnCodec are trained on speech and music — a corvid call is neither. This experiment was a gate, built to be allowed to fail: if the codec cannot round-trip a caw, a model trained on its tokens is finished before it starts. On 300 crow-positive windows, EnCodec at 1.5 kbps destroyed the call and at 3 kbps badly damaged it, but from 6 kbps upward the median window lost almost nothing — a qualified yes. The strict pre-registered pass criterion technically failed at every bitrate, partly because one of its bars was accidentally unsatisfiable and partly because it was set without knowing the ceiling; the graded numbers, read honestly after the fact, support 6 kbps and up. CrowGPT tokenises at 6 kbps as a result, and a side finding — that BirdNET ranks deliberately ruined audio above codec audio that is three times closer spectrally — means BirdNET is no longer trusted to rank audio quality anywhere in the project.

## In depth

### Method

2026-07-30. `facebook/encodec_24khz` at every bandwidth it supports — 1.5, 3, 6, 12 and 24 kbps, i.e. 2, 4, 8, 16 and 32 residual codebooks — on 300 crow-positive windows, 50 per species, drawn stratified with BirdNET's own `CROW_MIN_CONF` gate and one window per recording. Nine arms:

| arm | what |
|---|---|
| `native` | the file as recorded — what BirdNET confidence is measured against |
| `resample_24k` | native → 24 kHz, no codec — separates band loss from codec loss; the reference all spectral distances are measured from |
| `encodec_*` | the five bitrates |
| `encodec_3kbps_x2` | encoded and decoded twice, to expose accumulating artefacts |
| `lowpass_2k` | deliberately ruined, to prove the metrics can fail |

Primary metric: multi-resolution STFT distance (windows 1200/240/60), not a single log-mel — a 25 ms hop integrates away the 10–30 ms pulse structure that carries a caw's onset, the first thing a codec loses. BirdNET retention was secondary by design, because BirdNET was trained on archive mp3s with heavy augmentation and is robust to exactly the smearing being measured. Pre-registered pass criterion: retention ≥ 0.90 among windows the original scored ≥ 0.25, median paired Δconfidence ≥ −0.05, and spectral distance no worse than half the deliberately-ruined anchor.

### Resampling to 24 kHz is free

| arm | mean conf | retention | median Δconf |
|---|---|---|---|
| native | 0.752 | 1.000 | 0.000 |
| resample_24k | 0.774 | **0.987** | **+0.007** |

Throwing away everything above 12 kHz costs nothing measurable — mean confidence goes very slightly up. This independently reproduces experiment 0013's bandwidth finding (96.8% of call units roll off below 8 kHz) by a completely different route, and it establishes the ceiling: 0.987, not 1.0. No codec arm can do better, and the pass criterion was written as though one could.

### Codec degradation is graded, and steep below 6 kbps

| bitrate | codebooks | retention | median Δconf | STFT dist | entropy (bits) |
|---|---|---|---|---|---|
| 1.5 | 2 | 0.373 | −0.512 | 1.581 | 6.3 – 7.1 |
| 3 | 4 | 0.690 | −0.192 | 1.463 | 6.3 – 7.5 |
| **6** | **8** | **0.810** | **−0.030** | **1.355** | 6.3 – 7.8 |
| 12 | 16 | 0.877 | −0.005 | 1.247 | 6.3 – 8.2 |
| 24 | 32 | 0.887 | −0.004 | 1.195 | 6.3 – 8.7 |

At 1.5 kbps the caw is destroyed — over 60% of windows stop being a corvid. From 6 kbps the median window loses almost nothing, and by 12 kbps essentially nothing at all (−0.005 against a −0.05 bar). Every codebook is doing work — even the 32nd residual stage sits at 6.3 bits of a possible 10 — so there is no dead stage to prune and code entropy does not choose the bitrate; sequence length has to. The double round-trip control behaves: 3 kbps twice drops retention from 0.690 to 0.527, so artefacts accumulate rather than saturating.

### The pre-registered criterion failed at every bitrate

Not one arm passed. Retention never reaches 0.90 — 24 kbps gets closest at 0.887 — while the spectral and Δconfidence bars are cleared comfortably from 6 kbps up. The bar was set badly, in two distinct ways:

- **An arithmetic self-infliction.** The spectral criterion was originally "within 2× the resample-only arm" — but resample-only *is* the reference all spectral distances are measured from, so its distance to itself is zero and nothing could ever satisfy it. Every codec arm failed a check that had nothing to do with the codec. It is now set against the ruined `lowpass_2k` anchor instead, which all five arms clear.
- **A real judgement error.** Retention was pinned at an absolute 0.90 without knowing the ceiling, which turned out to be 0.987 — resampling alone costs 1.3%. Against that, 12 kbps at 0.877 and 24 kbps at 0.887 are both within about a point of the bar.

The honest statement: the gate failed as written, and the failure is graded rather than categorical. Reading the numbers rather than the verdict gives a qualified yes from 6 kbps upward — a reading made after seeing the data, and labelled as such.

### A 2 kHz lowpass beats the codec, and this is the important result

| arm | retention | median Δconf | STFT distance |
|---|---|---|---|
| `lowpass_2k` (deliberately ruined) | **0.733** | −0.190 | **4.752** |
| `encodec_3kbps` | **0.690** | −0.192 | **1.463** |

Audio with everything above 2 kHz thrown away keeps **more** BirdNET detections than EnCodec at 3 kbps, while being 3.2× further away spectrally. The two metrics rank these arms in opposite directions. The reason: corvid calls have a median rolloff of 2,688 Hz (experiment 0013), so a 2 kHz lowpass leaves the fundamental intact and merely dulls it, while low-bitrate codec artefacts smear the onsets and add structure that was never there — exactly what a detector keys on.

This retroactively justifies making BirdNET the secondary metric. Run with BirdNET retention alone — the obvious cheap design — this experiment would have concluded that a 2 kHz lowpass is a better tokenizer than a neural codec.

### The answer, and what changed

**Qualified yes, from 6 kbps up.** The codec is not the blocker, but it is not free, and it sets a ceiling the model cannot exceed.

- **`crowgpt` tokenises at 6 kbps / 8 codebooks** — previously an unmeasured guess; 1.5 and 3 kbps would have been reasonable-looking choices and both destroy the call. 12 kbps is measurably better for the codec (0.877 retention against 0.810) but doubles the sequence length (3,600 tokens per 3-second bout against 1,800) and the vocabulary, and at a corpus of ~24,000 bouts the model, not the tokenizer, is the binding constraint. A deliberate trade.
- **The judge gained an arm.** Because the codec ceiling is 0.810 rather than 1.0, comparing generated audio against untouched recordings would blame the model for the tokenizer's losses. Real audio round-tripped through the codec is now scored as its own arm and is the comparison that means anything.
- **BirdNET is no longer trusted to rank audio quality** anywhere in this project, on the strength of the lowpass result. It ranks content, not quality.
- **A criterion phrased as a multiple of the reference arm is always unsatisfiable** — written down because the same shape of mistake is easy to repeat, and it cost one full run to notice.
- Nothing changed about the corpus, and no re-collection is warranted: the resampling result reproduces 0013's bandwidth finding independently.

### Re-running

`cd ../../crowgpt && make gate` (N=50 per species by default). About 40 minutes, mostly BirdNET. Needs `crowgpt/.venv` and downloads the EnCodec weights on first use. Results to `results.json`.
