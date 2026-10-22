# Does the furry windshield earn its place?

## Overview

After fitting a furry windshield (a "deadcat") to the new microphone, the recordist said the waveform looked much better; this experiment checked what "better" actually was, since the project had previously caught itself crediting wind for noise that turned out to be traffic (experiment 0005). Recordings with the windshield on and off, on the same microphone in the same afternoon, showed the windshield genuinely removed handling transients and about 5 dB of low-frequency rumble — exactly what was predicted in advance. An apparent 7.2 dB loss in signal-to-noise ratio turned out not to be measuring the windshield at all: the birds, distances and call types differed between recordings, and bird-detection confidence actually went up with the windshield on. The windshield stays on.

## In depth

### Method

Captures 104 and 105 (windshield on) against 102 and 103 (windshield off), all on the VideoMic Me-C at 48 kHz with `USB_HEADSET` honoured. Better controlled than experiment 0009: same microphone, same afternoon, one deliberate change. Predictions were written down first — fewer handling transients, lower rumble, a small loss above the caw band, and 800–4000 Hz roughly unchanged.

### The windshield did what it was predicted to do

| | events | clipped samples | 99th pct | sub-200 Hz floor |
|---|---|---|---|---|
| 102 off | 2 | 374 | −13.8 | −57.5 |
| 103 off | 2 | 195 | −13.9 | −53.3 |
| **104 on** | **1** | **31** | −24.6 | **−60.4** |
| **105 on** | **0** | **0** | −22.4 | **−60.6** |

Transients fell from two per recording to one and none, and clipped samples from hundreds to 31 and zero. Rumble under 200 Hz fell about 5 dB. Both were predicted, and the transient count is the one measure here that content cannot fake.

### The 7.2 dB SNR drop is not the windshield

Band SNR fell 7.2 dB with the windshield on, but three things say that number is not measuring the windshield:

- **BirdNET confidence went up** — 0.526/0.577 without, 0.695/0.588 with. On experiment 0004's calibration, a genuine 7 dB loss should have cost roughly 0.5 of confidence. It gained. A measure and its consequence cannot move in opposite directions if the measure is describing what happened.
- **The whole recording is about 10 dB quieter** (99th percentile −13.9 → −23.5). No foam does that. A deadcat costs 1–3 dB, and mostly above the caw band.
- **The content changed.** Capture 104 is a fledgling begging — a quieter, more continuous sound than an alarm caw — and both new captures are longer, so the quiet percentile that band SNR divides by is measuring different silence.

The drop is different birds at different distances, not attenuation. The tidy version of this write-up would have been "windshield costs 7 dB of SNR", which is wrong and would have taken the deadcat back off.

### Wind was never the variable

Gustiness of the sub-200 Hz band is 1.07/0.78 without the windshield and 1.05/0.80 with it — unchanged. This is experiment 0005's conclusion arrived at from the other direction: the low-frequency energy around here is machinery and traffic, which is steady, and a windshield does not touch it.

### Limits

This design cannot measure the acoustic cost of the windshield, and no amount of captures like these will fix that: the birds, the distance and the call type all move between recordings, and each of those swamps a 1–3 dB foam loss. Measuring it properly needs the same source twice — a speaker playing a fixed clip, deadcat on and off, everything else nailed down. That is worth doing only if the windshield is ever suspected of hiding something, which nothing here suggests.

### What it changed

- **Keep the windshield on.** It removed the handling transients it was predicted to remove, cost nothing measurable in detections, and the one recording that matters most — capture 104, the first begging ever detected on this fleet — is also the cleanest of the four by transient count.
- **Band SNR now carries a caveat when recordings differ in length or content.** It is a percentile ratio inside one recording, so it silently compares each recording against its own quiet. Across experiments 0001, 0004, 0008 and 0009 that was fine because the captures were similar; here it produced a confident wrong answer.
