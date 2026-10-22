# Are the field recordings loud enough to train on?

## Overview

The first two real rooftop recordings (captures 87 and 88, made on a Pixel 10 with the built-in microphone, with the crow about 30 m up) raised the worry that the phone microphone was not good enough, and the recordist asked before buying anything. Measurement showed the recordings are loud enough: no clipping, calls sitting 15–29 dB clear of the street in the crow's frequency band, and BirdNET recognising the species with high confidence. Nothing was bought, because the numbers showed that a more sensitive microphone would not help — the limit is background noise, not sensitivity.

## In depth

### Method

Peak and RMS levels in dBFS, a clipping count, and band-limited SNR in 800–4000 Hz — the fundamental and first harmonics of a caw. Band SNR was used rather than broadband because a street is mostly low-frequency rumble: broadband flatters, band tells the truth. The per-call margin above each recording's own noise floor was also measured.

### Results

| | 87 (22.5 s) | 88 (29.5 s) |
|---|---|---|
| peak | −26.8 dBFS | −26.7 dBFS |
| clipped samples | 0 | 0 |
| caw above street (800–4 k) | ~12–20 dB | **15–29 dB** |
| BirdNET | American Crow 0.984 | American Crow **1.000** ×2 |

Capture 88 holds seven distinct calls, the best of them 24–29 dB clear of the street. Capture 87 is weaker: it has continuous broadband noise from ~13 s to the end (vehicle or wind at the time of writing — later identified in experiment 0005) plus a +34 dB transient at 11.5 s that is not the bird. Its later "events" of 0.87–1.25 s are far too long to be caws.

### What it changed

Nothing was bought. Zero clipping at −27 dBFS means about 27 dB of headroom is going unused — the UNPROCESSED source sits ~17 dB below VOICE_RECOGNITION by design — so a *more sensitive* microphone buys nothing; it lifts the noise along with the signal.

The advice at the time was directionality over sensitivity, and wind protection before either. Experiment 0004 ([0004](../0004-snr-vs-confidence/)) later sharpened this: noise rejection turns out to buy *detections*, not just cleaner audio, which made the case for a directional microphone stronger than this experiment concluded. (The "wind protection before either" part was never actually tested — see the 2026-08-02 amendment in experiment 0005.)
