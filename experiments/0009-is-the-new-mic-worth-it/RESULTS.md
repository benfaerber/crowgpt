# Is the new microphone necessary, or is the phone's good enough?

## Overview

Ben bought a USB microphone (a Røde VideoMic Me-C) and asked whether it was actually needed, or whether the phone's built-in microphone was good enough. Recordings of American Crows made with each microphone from the same balcony, three days apart, were compared on signal-to-noise ratio in the crow band, noise floor, peak level and clipping. The comparison came out honestly inconclusive: against the better built-in capture the new mic measured slightly worse, against the weaker one clearly better, and the best recording in the corpus was made on the new mic but lacked the distance metadata needed for a fair comparison. The decision was to keep using the mic — its properties (directional pickup, low self-noise, more usable dynamic range) match what earlier experiments said this project needs — and an initial same-day recommendation to switch back to the phone was withdrawn as a measurement error.

## In depth

### Method

Captures 102 and 103 (recorded on the USB mic, `USB_HEADSET`) were compared with captures 87 and 88 (built-in mic), all American Crows at 20–50 m from the same balcony. The band SNR measure was experiment 0004's `band_snr`, unchanged, so these numbers sit on the same axis as every earlier experiment; absolute noise floor, peak level and a clipped-sample count were added. `media.input_device` was checked first to confirm which mic each capture actually used, because the app has previously had a fallback bug that recorded the wrong mic while claiming otherwise. Both new captures report `USB_HEADSET`.

### The clipping scare, and the same-day correction

The first version of this write-up called the mic "clipping" and told the recordist to turn the gain down. That was wrong, and wrong in the direction that would have cost him the better microphone. Counting clipped samples without asking where they were is the mistake:

| | 103 new | 102 new | 87 built-in | 88 built-in |
|---|---|---|---|---|
| peak | **0.0 dBFS** | **0.0 dBFS** | −26.8 | −26.7 |
| clipped samples | **195** | **374** | 0 | 0 |
| band SNR 800–4k | 19.2 | 29.7 | 12.4 | **21.7** |
| noise floor 800–4k | −92.0 | −89.6 | −105.7 | **−110.2** |

The clipped samples resolve into just two events per recording:

| | clipped | events | longest | 99th pct level |
|---|---|---|---|---|
| 102 | 374 | **2** | 21 ms | **−13.8 dBFS** |
| 103 | 195 | **2** | 3 ms | **−13.9 dBFS** |

Two events each, 1–21 ms long, with only 0.01–0.05% of samples anywhere near full scale. That is not a hot microphone; that is a well-set one meeting two mechanical transients — a bump, a door, a footstep. The 99th percentile level is the number that matters, and at −14 dBFS it is close to ideal. The built-in mic's zero-clip record is not virtue: at −26.8 dBFS peak it is under-using its range by about 14 dB, leaving 27 dB of headroom nobody spends.

### SNR: inconclusive, and honestly so

The apparent "+2.2 dB average" advantage for the new mic is an artefact of what it is averaged against. Against the better built-in capture (88) the new mic is 2.5 dB worse (19.2 against 21.7); against 87 it is 6.8 dB better — and experiment 0001 already described 87 as the weak capture, with a vehicle washing through from 13 s. Averaging those two hides the disagreement rather than resolving it.

The noise floor is +15.9 dB higher in the crow band and +27.0 dB higher below 300 Hz on the new mic — but the whole signal is 26 dB hotter, so an absolute floor says nothing on its own. Band SNR is the ratio that matters, and it is the one that comes out inconclusive.

Capture 102 reaches 29.7 dB, the best band SNR in the corpus, on the new mic. No distance was recorded for it, so it cannot join the matched comparison — suggestive, not evidence, and the most interesting number here.

### What the mic is

The mic was identified after the measurements: a Røde VideoMic Me-C, USB-C.

| | |
|---|---|
| polar pattern | **cardioid** — directional |
| self-noise | **19.5 dBA** |
| max SPL | 115 dB |
| frequency response | 20 Hz – 20 kHz |
| gain control | none |

The 115 dB max SPL is far above anything a crow at 20 m produces — independent confirmation that the two transients were knocks rather than overload. The 19.5 dBA self-noise shows up in the usable range each mic actually delivered:

| | noise floor | peak | range |
|---|---|---|---|
| VideoMic Me-C (103) | −92.0 | 0.0 | **92.0 dB** |
| built-in (88) | −110.2 | −26.7 | 83.5 dB |

About 8.5 dB more room between the noise and the ceiling — a property of the microphone rather than of a morning, and the first thing in this experiment not confounded by n=1.

The cardioid pattern is the headline for this project: experiment 0001 concluded "directionality over sensitivity, and wind protection before either", and experiment 0004 measured why — confidence collapses with background, so rejecting off-axis noise buys detections rather than decibels. The mic was bought on the right grounds, whatever the matched test eventually says.

### Limits

n=1 against n=2 cannot separate a microphone from a morning. A crow's variation between bouts is larger than the difference being measured. Answering the question properly requires recording the same birds at the same distance on both mics within a few minutes of each other, alternating — one matched pair is worth more than another ten unmatched captures.

### What it changed

- **Keep using the mic.** Its level is well chosen and the two transients are a handling problem, not a gain problem — the mic has no gain control anyway, so there was never a dial to turn.
- **The recommendation to switch back to the phone was withdrawn within the hour.** Nothing was returned and nothing was bought.
- **Avoid touching the mic while it runs.** Both transients are the kind a hand or a cable makes. A clipped-sample warning at record time went into TODO.txt — not to police gain, but to say "you knocked it" while there is still time to re-record.
