# 0036 — Does DAC elevate the background, or does EnCodec suppress it?

## Overview

Mid-way through a listening sitting Ben remarked, unprompted, that the DAC codec seemed to elevate footsteps and wind sounds. That observation is ambiguous on its own — "DAC elevates the background" and "EnCodec attenuates it" are the same impression and opposite findings, and only comparison against raw audio can tell them apart. This experiment measured per-band levels on 54 held-out bouts and found both effects at once: DAC genuinely adds about half a decibel below 500 Hz, and EnCodec has been quietly attenuating the 800 Hz–4 kHz band the crow actually occupies — in every clip the project has ever produced — by about half a decibel. The result confirms DAC as the better choice for a project whose point is what was happening around the calls, and sizes a small listening-test confound that had previously been unmeasured.

## In depth

### Method

2026-08-02, 54 held-out bouts, one per recording — no ears and no model, purely a level measurement. Each bout is segmented with the shipped 12 dB detector, then per-band RMS is measured separately over the call units and over everything else (the gaps and the leading ambience every bout carries so the causal encoder settles). The detector runs on raw audio only and its regions are reused for every arm, because re-segmenting each arm would compare different stretches of time and quietly turn a level question into a detector question.

The prior made the observation plausible rather than idle: EnCodec 24 kHz is trained on speech and music, while DAC is trained on environmental audio too — a codec spends capacity where its training distribution says the information is.

### Results — dB relative to raw, 95% CI (bold intervals exclude zero)

Background (non-call) regions:

| band | EnCodec-32 | DAC-24 at 24 cb |
|---|---|---|
| wind, < 500 Hz | +0.31 [−0.36, +1.52] | **+0.56 [+0.49, +0.65]** |
| corvid, 800–4k | **−0.41 [−0.51, −0.31]** | **+0.17 [+0.12, +0.22]** |
| hiss, > 6 kHz | **−0.66 [−0.85, −0.48]** | **−0.85 [−1.00, −0.68]** |

Call regions:

| band | EnCodec-32 | DAC-24 at 24 cb |
|---|---|---|
| wind, < 500 Hz | −0.25 [−0.53, +0.04] | **+0.57 [+0.47, +0.71]** |
| corvid, 800–4k | **−0.67 [−0.74, −0.59]** | +0.04 [−0.01, +0.09] |
| hiss, > 6 kHz | **−0.47 [−0.70, −0.23]** | **−1.42 [−1.55, −1.29]** |

The observation is confirmed, and it is two effects at once:

1. DAC genuinely lifts the low end: +0.56 dB in background and +0.57 dB under the calls, below 500 Hz, both resolved. Wind and footstep thumps live exactly there.
2. EnCodec has been quietly denoising the corvid band: −0.41 dB in the gaps and −0.67 dB under the calls, 800 Hz–4 kHz — the band the crow is in. DAC sits within 0.17 dB of raw in the gaps and within 0.04 dB under the calls, as close to exact as this measurement resolves.

So the half of the impression that reads as "DAC added something" is really "EnCodec was taking something away, and DAC stopped." Both codecs roll off above 6 kHz, DAC more (−0.85 / −1.42 dB); at 24 kHz the Nyquist is 12 kHz and there is little crow up there, so that is the cheapest place for either to save bits.

### Caveats

This is a measurement of codec behaviour over corpus bouts — a pipeline finding, not one about crows. The DAC low-end lift is a confound to keep in view for listening tests: DAC arms carry ~0.5 dB more low end than raw, giving a listener something to separate them on that is not quality. It is small and did not act as a penalty (DAC-24 scored 0.93 and 0.88 against raw's 0.97 and 0.92 in experiments 0033 and 0034), but "did not penalise" is not "was not audible".

### What this changed

- EnCodec was attenuating the corvid band by about half a decibel in every clip this project has ever produced — small, systematic, and never measured, because experiments 0014 through 0032 all measured whole-clip distance or detection, never a round-trip against raw by band.
- It matters more than the size suggests: Cawtalker is about what crows say and what was happening when they said it, so a tokenizer that spends ambience away is spending the context half. DAC is the better choice on this axis too, for a reason unrelated to why it was chosen.
- The listening-test cue is now sized rather than assumed. A cheap protocol fix exists if it ever matters — band-limit or level-match arms below 500 Hz before a sitting — but it was not applied retroactively: the existing results stand as collected, since re-normalising after the fact would be choosing a transform because of the answer it gives.
