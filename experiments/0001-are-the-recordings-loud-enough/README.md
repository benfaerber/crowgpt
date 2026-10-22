# Are the field recordings loud enough to train on?

**2026-07-26** · captures 87 and 88, Pixel 10, built-in mic, crow ~30 m up

## Why

First two real rooftop recordings. The recordist was worried the phone
microphone was insufficient and asked before buying anything.

## Method

Peak and RMS in dBFS, clipping count, and band-limited SNR in 800–4000 Hz — the
fundamental and first harmonics of a caw. Band SNR rather than broadband because
a street is mostly low-frequency rumble: broadband flatters, band tells the
truth. Also the per-call margin above the recording's own noise floor.

## Result

| | 87 (22.5 s) | 88 (29.5 s) |
|---|---|---|
| peak | −26.8 dBFS | −26.7 dBFS |
| clipped samples | 0 | 0 |
| caw above street (800–4 k) | ~12–20 dB | **15–29 dB** |
| BirdNET | American Crow 0.984 | American Crow **1.000** ×2 |

Capture 88 holds seven distinct calls, the best 24–29 dB clear of the street.
Capture 87 is weaker: continuous broadband noise from ~13 s to the end (vehicle
or wind) plus a +34 dB transient at 11.5 s that is not the bird. Its later
"events" of 0.87–1.25 s are far too long to be caws.

## What it changed

Nothing was bought. Zero clipping at −27 dBFS means ~27 dB of headroom is going
unused — the UNPROCESSED source sits ~17 dB below VOICE_RECOGNITION by design —
so a *more sensitive* microphone buys nothing; it lifts the noise with the
signal.

The advice at the time was directionality over sensitivity, and wind protection
before either. See [0004](../0004-snr-vs-confidence/) for the measurement that
later sharpened this: noise rejection turns out to buy *detections*, not just
cleaner audio, which made the case for a directional mic stronger than this
experiment concluded.
