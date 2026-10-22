# Is the new microphone necessary, or is the phone's good enough?

**2026-07-29** · captures 102, 103 (USB_HEADSET) against 87, 88 (BUILTIN_MIC)

## Why

Ben bought a USB microphone and asked whether it was needed. Both mics have now
recorded American Crows at 20–50 m from the same balcony, three days apart, so
the corpus can answer better than a listening test.

## Method

0004's `band_snr` unchanged, so these sit on the same axis as every earlier
experiment, plus absolute noise floor, peak level and a clipped-sample count.
`media.input_device` says which mic each capture actually used — checked first,
because a fallback that records the wrong mic while claiming otherwise is a bug
this app has had before. Both new captures report `USB_HEADSET`, honoured.

## Result

**Correction, same day.** The first version of this called the mic "clipping"
and told the recordist to turn the gain down. That was wrong, and wrong in the
direction that would have cost him the better microphone. Counting clipped
samples without asking *where* they were is the mistake: 195 samples reads as
overload and turns out to be two bumps.

| | 103 new | 102 new | 87 built-in | 88 built-in |
|---|---|---|---|---|
| peak | **0.0 dBFS** | **0.0 dBFS** | −26.8 | −26.7 |
| clipped samples | **195** | **374** | 0 | 0 |
| band SNR 800–4k | 19.2 | 29.7 | 12.4 | **21.7** |
| noise floor 800–4k | −92.0 | −89.6 | −105.7 | **−110.2** |

Peak is +26.7 dB over the built-in and touches full scale — but only just, and
only twice per recording:

| | clipped | events | longest | 99th pct level |
|---|---|---|---|---|
| 102 | 374 | **2** | 21 ms | **−13.8 dBFS** |
| 103 | 195 | **2** | 3 ms | **−13.9 dBFS** |

Two events each, 1–21 ms, with 0.01–0.05 % of samples anywhere near full scale.
That is not a hot microphone; that is a well-set one meeting two transients — a
bump, a door, a footstep. The 99th percentile is the number that matters, and
at −14 dBFS it is close to ideal.

The built-in mic, at −26.8 dBFS peak, is *under*-using its range by about 14 dB.
Its zero-clip record is not virtue, it is 27 dB of headroom nobody spends.

**Nor is it clearly buying SNR.** The "+2.2 dB average" is an artefact of what
it is averaged against. Against the *better* built-in capture the new mic is
2.5 dB worse (19.2 against 21.7); against 87 it is 6.8 dB better, and 0001
already described 87 as the weak one with a vehicle washing through from 13 s.
Averaging those two hides the disagreement rather than resolving it.

The noise floor is +15.9 dB in the crow band and +27.0 dB below 300 Hz — but the
whole signal is 26 dB hotter, so an absolute floor says nothing on its own. Band
SNR is the ratio that matters and it is the one that comes out inconclusive.

Capture 102 reaches 29.7 dB, the best band SNR in the corpus, on the new mic.
No distance was recorded for it, so it cannot join the matched comparison —
suggestive, not evidence, and the most interesting number here.

## What the mic is

**Røde VideoMic Me-C**, USB-C, identified after the measurements above:

| | |
|---|---|
| polar pattern | **cardioid** — directional |
| self-noise | **19.5 dBA** |
| max SPL | 115 dB |
| frequency response | 20 Hz – 20 kHz |
| gain control | none |

Two of those explain the numbers. **115 dB max SPL** is far above anything a
crow at 20 m produces, which is the independent confirmation that the two
transients were knocks rather than overload — the capsule was nowhere near its
limit.

**19.5 dBA self-noise** is well below a phone's MEMS capsule, and it shows up
where it should. Compare the usable range each mic actually delivered, floor to
ceiling:

| | noise floor | peak | range |
|---|---|---|---|
| VideoMic Me-C (103) | −92.0 | 0.0 | **92.0 dB** |
| built-in (88) | −110.2 | −26.7 | 83.5 dB |

About **8.5 dB more room between the noise and the ceiling** — which is the
comparison the absolute floors obscured, since the whole signal sits 26 dB
hotter. That is a property of the microphone rather than of a morning, and it is
the first thing in this experiment that is not confounded by n=1.

**Cardioid is the headline for this project.** 0001 concluded "directionality
over sensitivity, and wind protection before either", and 0004 then measured why
— confidence collapses with background, so rejecting off-axis noise buys
detections rather than decibels. A directional mic with a furry windshield is
precisely what those two experiments asked for. It was bought on the right
grounds, whatever the matched test eventually says.

## What it changed

**Keep using the mic.** Its level is well chosen and the two transients are a
handling problem, not a gain problem — the mic has no gain control anyway, so
there was never a dial to turn.

**The comparison is still inconclusive, and honestly so.** Against the better
built-in capture the new mic is 2.5 dB worse in band SNR (19.2 against 21.7);
against the weaker one it is 6.8 dB better. Capture 102 reaches **29.7 dB, the
best in the corpus** — but no distance was recorded, so it cannot join a matched
comparison. n=1 against n=2 cannot separate a microphone from a morning.

**To answer it properly:** record the same birds at the same distance on both
mics within a few minutes of each other, alternating. A crow's variation between
bouts is larger than the difference being measured, so one matched pair is worth
more than another ten unmatched captures.

**And avoid touching the mic while it runs.** Both transients are the kind a
hand or a cable makes. That is what a clipped-sample warning at record time
would catch, which is now in TODO.txt — not to police the gain, but to say "you
knocked it" while there is still time to re-record.

Nothing was returned and nothing was bought. The recommendation to switch back
to the phone was withdrawn within the hour.
