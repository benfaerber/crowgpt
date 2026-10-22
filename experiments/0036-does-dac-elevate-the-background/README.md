# 0036 — Does DAC elevate the background, or does EnCodec suppress it?

**2026-08-02** · 54 held-out bouts, one per recording · no ears, no model

## The question

Ben, mid-sitting and unprompted:

> it almost seems like the dac24 elevates footsteps and wind sounds?

Plausible rather than idle. EnCodec 24 kHz is trained on speech and music; DAC is
trained on environmental audio too, which is why 0017 reached for it. A codec
spends capacity where its training distribution says the information is, so a
broadband transient and low-frequency rumble are the kind of content one would
model and the other would treat as noise to spend away.

**But "DAC elevates the background" and "EnCodec attenuates it" are the same
observation and opposite findings**, and only raw can tell them apart.

## Method

Segment each bout with the shipped 12 dB detector, then measure per-band RMS
separately over the call units and over everything else — the gaps and the
leading ambience every bout carries so the causal encoder settles. **The detector
runs on raw only and its regions are reused for every arm**, because
re-segmenting each arm would compare different stretches of time and quietly
turn a level question into a detector question.

## Results — dB relative to raw, 95% CI

**Background (non-call) regions:**

| band | EnCodec-32 | DAC-24 at 24 cb |
|---|---|---|
| wind, < 500 Hz | +0.31 [−0.36, +1.52] | **+0.56 [+0.49, +0.65]** |
| corvid, 800–4k | **−0.41 [−0.51, −0.31]** | **+0.17 [+0.12, +0.22]** |
| hiss, > 6 kHz | **−0.66 [−0.85, −0.48]** | **−0.85 [−1.00, −0.68]** |

**Call regions:**

| band | EnCodec-32 | DAC-24 at 24 cb |
|---|---|---|
| wind, < 500 Hz | −0.25 [−0.53, +0.04] | **+0.57 [+0.47, +0.71]** |
| corvid, 800–4k | **−0.67 [−0.74, −0.59]** | +0.04 [−0.01, +0.09] |
| hiss, > 6 kHz | **−0.47 [−0.70, −0.23]** | **−1.42 [−1.55, −1.29]** |

Bold intervals exclude zero.

**The observation is confirmed, and it is two effects at once.**

1. **DAC genuinely lifts the low end.** +0.56 dB in background and +0.57 dB
   under the calls, below 500 Hz, both resolved. Wind and footstep thumps live
   exactly there. This half is DAC adding level that raw does not have.
2. **EnCodec has been quietly denoising the corvid band.** −0.41 dB in the gaps
   and −0.67 dB under the calls, 800–4 kHz — the band the crow is in. DAC sits
   within 0.17 dB of raw in the gaps and within 0.04 dB under the calls, which
   is as close to exact as this measurement resolves.

So the half of the impression that reads as "DAC added something" is really
"EnCodec was taking something away, and DAC stopped." Everything mid-band is
more present than the ear is used to, and there is a genuine low-frequency lift
on top.

Both codecs roll off above 6 kHz, DAC more (−0.85 / −1.42 dB). At 24 kHz the
Nyquist is 12 kHz and there is little crow up there, so this is the cheapest
place for either to save bits.

## What this changed

- **EnCodec was attenuating the corvid band by about half a decibel, in every
  clip this project has ever produced.** Small, systematic, and never measured.
  It never showed up because nothing compared a round-trip against raw *by
  band* — 0014 through 0032 all measured whole-clip distance or detection.
- **It matters more here than the size suggests.** CrowGPT is about what crows
  say *and what was happening when they said it*; the calls × context matrix is
  the point. A tokenizer that spends ambience away is spending the context half.
  DAC is the better choice on this axis too, for a reason unrelated to why it was
  chosen.
- **A confound to keep in view, not to panic about.** DAC arms carry ~0.5 dB more
  low end than raw, so a listener has something to separate them on that is not
  quality. It is small, and it did not act as a penalty: DAC-24 scored 0.93 and
  0.88 against raw's 0.97 and 0.92 in 0033 and 0034. But "did not penalise" is
  not "was not audible", and the cue is now sized rather than assumed.
- **A cheap protocol fix if it ever matters:** band-limit or level-match the
  arms below 500 Hz before a sitting. Not done retroactively — the existing
  results stand as collected, and re-normalising them after the fact would be
  choosing a transform because of the answer it gives.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0036-does-dac-elevate-the-background/run.py
```

About four minutes. Writes `results.json` here, with per-bout numbers alongside
the summary.
