# Does the furry windshield earn its place?

**2026-07-29** · captures 104, 105 (deadcat on) against 102, 103 (off) ·
VideoMic Me-C, `USB_HEADSET` honoured, 48 kHz on all four

## Why

The recordist fitted the windshield and said the waveform looked much better.
Worth checking what "better" was, because 0005 already caught this project
crediting wind for noise that turned out to be traffic.

Better controlled than 0009: same microphone, same afternoon, one deliberate
change. Predictions written down first — fewer handling transients, lower
rumble, a small loss above the caw band, and 800–4000 Hz roughly unchanged.

## Result

**The waveform does look better, and for a real reason.**

| | events | clipped samples | 99th pct | sub-200 Hz floor |
|---|---|---|---|---|
| 102 off | 2 | 374 | −13.8 | −57.5 |
| 103 off | 2 | 195 | −13.9 | −53.3 |
| **104 on** | **1** | **31** | −24.6 | **−60.4** |
| **105 on** | **0** | **0** | −22.4 | **−60.6** |

Transients fell from two per recording to one and none, and clipped samples
from hundreds to 31 and zero. Rumble under 200 Hz fell about **5 dB**. Both were
predicted, and the transient count is the one measure here that content cannot
fake.

**But band SNR fell 7.2 dB, and that number is not measuring the windshield.**
Three things say so:

- **BirdNET confidence went *up*** — 0.526/0.577 without, 0.695/0.588 with. On
  0004's calibration a genuine 7 dB loss should have cost roughly 0.5 of
  confidence. It gained. A measure and its consequence cannot move in opposite
  directions if the measure is describing what happened.
- **The whole recording is ~10 dB quieter** (99th percentile −13.9 → −23.5).
  No foam does that. A deadcat costs 1–3 dB, and mostly above the caw band.
- **The content changed.** 104 is a fledgling begging — a quieter, more
  continuous sound than an alarm caw — and both new captures are longer, so the
  quiet percentile that band SNR divides by is measuring different silence.

So the drop is different birds at different distances, not attenuation. Stated
plainly because the tidy version of this write-up would have been "windshield
costs 7 dB of SNR", which is wrong and would have taken the deadcat back off.

**Wind was never the variable.** Gustiness of the sub-200 Hz band is 1.07/0.78
without and 1.05/0.80 with — unchanged. Same conclusion as 0005 from the other
direction: the low-frequency energy around here is machinery and traffic, which
is steady, and a windshield does not touch it.

## What it changed

**Keep the windshield on.** It removed the handling transients it was predicted
to remove, cost nothing measurable in detections, and the one recording that
matters most — 104, the first begging ever detected on this fleet — is also the
cleanest of the four by transient count.

**This design cannot measure the acoustic cost**, and no amount of captures like
these will fix that: the birds, the distance and the call type all move between
recordings, and each of those swamps a 1–3 dB foam loss. Measuring it properly
needs the same source twice — a speaker playing a fixed clip, deadcat on and
off, everything else nailed down. Worth doing only if the windshield is ever
suspected of hiding something, which nothing here suggests.

**Band SNR needs a caveat when recordings differ in length or content.** It is a
percentile ratio inside one recording, so it silently compares each recording
against its own quiet. Across 0001, 0004, 0008 and 0009 that was fine because
the captures were similar; here it produced a confident wrong answer. Worth
remembering before the next comparison leans on it.
