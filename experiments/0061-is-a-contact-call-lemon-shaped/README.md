# 0061 — is a contact call lemon-shaped?

**2026-08-09** · 81 contact vs 381 alarm bouts, 0060's audio re-segmented ·
**answer: half the lemon is real — smooth, single-peaked, short — but shape
alone narrows the funnel only ~1.6×**

## The question

Ben named the signature himself: contact calls "have a lemon shaped sound
wave" — swelling in the middle, tapering at both ends. 0046 turned "modem"
into a stuck codebook and 0059 turned "scream" into duty cycle; this asks the
envelope whether "lemon" is measurable, because 0060 proved BirdNET *finds*
contact bouts at the alarm rate — meaning it finds the alarm-heavy majority
at that rate too, and a shape ranking could spare the trained ear most of the
wading.

## Method

Per 0013-detector unit, on the in-band linear envelope, medianed within each
bout of 0060's arms (re-segmented identically, counts cross-checked): peak
position, centroid, symmetry, total-variation "wiggle", local-maxima count,
unit duration; plus per-bout unit count and duty. AUC per feature at bout and
recording level, and within each species — ravens are 58% of contact bouts
but 20% of alarm, so a pooled AUC can be species timbre wearing a call-type
costume. Combo: logistic over all eight, recording-grouped 5-fold CV.

## Result

AUCs flipped where contact scores lower, so every number reads "how well
this separates" (direction in the second column):

| feature | contact is… | bout AUC | Hooded | Raven |
|---|---|---|---|---|
| n_peaks | single-peaked | 0.70 | 0.68 | 0.59 |
| unit_sec | shorter | 0.67 | 0.67 | 0.60 |
| wiggle | smoother | 0.63 | 0.61 | 0.60 |
| duty | sparser | 0.59 | 0.67 | 0.50 |
| peak_pos / centroid / symmetry | — | ≈ 0.5 | ≈ 0.5 | ≈ 0.5 |
| n_units | *unstable* | 0.51 | 0.64 | 0.25 flipped sign |

**The unimodal half of the lemon is real and survives the species control**:
a contact unit rises and falls once, cleanly, and is over quickly, where an
alarm unit pulses. **The symmetric mid-swell half is not there** at this
envelope resolution (125 fps, 800–4000 Hz band): where the single peak sits
inside the unit separates nothing.

Combined, recording-grouped CV: **AUC 0.637**. At the operating point Ben
would actually use — keep 80% of contact bouts — **59.5% of alarm bouts
survive**. A real narrowing, not a useful one: his ear would still hear three
alarms for every contact call at 0060's base rates.

Caveats: ground truth is recording-level recordist assertion on both arms;
European corvids; and alarm is only the dominant confuser — begging and song
were never in the comparison.

## What it changed

- **"Lemon" is now three numbers** — n_peaks, unit_sec, wiggle — worth
  carrying into any future contact feature set, and the peak-position family
  is measured dead: stop reaching for symmetry.
- **A shape-only prefilter is not the ranker.** The described signature is
  real but too weak alone to gate the funnel; 0062 asks whether BirdNET's
  own embeddings, probed on these same arms, do better before anything new
  gets built.
