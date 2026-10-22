# Is a lawn mower 30 ft away ruining these recordings?

**2026-07-28** · captures 94–97, Pixel 10, built-in mic · four crows on the
ground, one on a wire, mowers running · reference: capture 88

## Why

The recordist made four captures in front of the apartment with mowers going and
asked whether the noise had wrecked them. The pipeline called almost everything
"alarm call", which they doubted on behavioural grounds: birds foraging on the
ground did not scatter.

"Is the noise a problem" is three questions, and 0005 is the reason to keep them
apart — a wash there *looked* like wind and turned out to be piling into the
crow band, which is the only place it matters.

## Method

1. Band energy per capture, against capture 88 as a clean-ish control.
2. The **absolute** quiet-percentile level in 800–4000 Hz, plus 0004's band SNR
   measure unchanged, so these captures land on a curve that already exists.
3. High-pass at 300 Hz — well below a caw's ~1.6 kHz fundamental, so the call
   itself is untouched — then re-run the real analyzer and compare verdicts.
4. Call-type confidence against species confidence, over every detection on the
   server.

## Result

**The rumble fraction is a red herring.** These captures are 47–89 % sub-300 Hz
and that looks alarming until you measure the control: capture 88, a *good*
recording at 21.7 dB band SNR, is **78.8 %** sub-300 Hz. A city is mostly rumble
whether or not anyone is mowing.

**But the mower does reach the crow band, by about 10 dB.**

| | 94 | 95 | 96 | 97 | 88 (ref) |
|---|---|---|---|---|---|
| noise floor 800–4k | −99.8 | −100.3 | −100.2 | −99.4 | **−110.2** |
| band SNR | 19.1 | **12.6** | **13.1** | 21.4 | 21.7 |
| peak | −36.7 | −42.6 | −37.0 | −32.7 | −26.7 |

0004 calibrated this exact microphone: ~2.5 dB of extra noise costs ~0.19 of
BirdNET confidence, and a call at 10.9 dB scored 0.098. **95 and 96 sit at 12.6
and 13.1 dB** — just above where calls start disappearing. 94 and 97 are fine.

**Removing the rumble does not change the call type.** High-passing left band
SNR identical (19.1 → 19.1, as designed — the filter is nowhere near the band)
and the alarm verdicts survived on 95, 96 and 97. Only 94 moved: two "alarm
call" segments at p=1.000 became part of one "call" region.

What it *did* do, on every single region, is raise species confidence and stitch
fragments together:

| | as recorded | high-passed |
|---|---|---|
| 94 | 0.836 / three regions | **0.891** / one region |
| 95 | 0.865 | **0.905** |
| 96 | 0.757, 0.375 | **0.824, 0.603** |
| 97 | 0.975 | **0.990** |

**The alarm verdicts are untrustworthy — but not because of the mower.** Across
all 187 detections on the server:

- call-type p vs species confidence: **r = +0.03** — no relationship at all
- **32 %** of detections sit at p = 1.000 *exactly*
- mean species confidence where p = 1.000: **0.654**, against 0.779 elsewhere

A calibrated head is less sure when the input is worse. This one is pinned at
1.000 on a third of everything, and that third skews to regions BirdNET was
*less* sure were crows. Today's clearest case: capture 97 at 15–18 s, species
confidence 0.171, call type "alarm call" at p=1.000.

## What it changed

**The mower is not the reason it says alarm.** The recordist's scepticism was
right, and the answer is that the call-type head is saturating on out-of-domain
audio rather than reporting anything about the call. A logistic regression on
standardised embeddings returns 1.000 freely for input unlike its training set,
and its training set is archive recordings, not a phone in a street.

So: **do not read p on a call type as confidence** until the head is calibrated.
It is currently closer to a distance-from-training-set measure. Filed in
FUTURE.txt.

Three things did change:

- **95 and 96 are the marginal ones**, at 12.6 and 13.1 dB. 94 and 97 are as
  good as the rooftop reference and worth keeping.
- **A 300 Hz high-pass belongs in the analyzer's preprocessing.** It costs
  nothing in the call band and bought species confidence on 4 of 4 captures,
  plus it merged fragmented regions — which matters because fragmentation is
  what produced the spurious short "alarm" segments in the first place.
- **Standing 30 ft from a mower is fine.** The 10 dB it adds to the crow band is
  survivable at this range; what it costs is the margin that would have made a
  quiet call detectable. Recording *closer* to the bird buys that back faster
  than fighting the mower does.

Nothing was bought, and no recording was discarded.
