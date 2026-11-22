# 0113 — Does one crow call differently in different contexts?

**2026-11-22** · CPU · **answer: yes, narrowly — one crow's graded calling reads context at 0.665 (p = 0.0025), just over the 0.65 bar; removing the crowd costs almost nothing (0.687 with every crow window), and BirdNET's context signal mostly survives the same restriction (0.775 against 0.804)**

## The question

Every context difference found so far is entangled with how many crows are
calling. 0107's duty cycle scored a roost as high as an owl mob. 0110 found
roost is mostly crowd. And a mob is, by definition, many birds. The project
has never asked the question with the crowd removed by construction:
**take only the stretches where one crow is calling, and ask whether that
bird's calling differs by context.**

Two things now make that possible. 0109's count head separates one crow from
several inside a call type at 0.80. And once only one bird is calling, the
envelope segmenter's known failure goes away: 0105 found it undercounts only
when calls overlap, and a single bird's caws do not overlap.

This follows the graded approach in FUTURE.txt (the León entry): describe a
call by graded acoustic features (duration, gaps, pitch, spectrum) rather than
by a semantic name, and ask whether those features track context.

## Pre-registration (written and committed before any archive window is scored by the count head)

**Recordings.** The 423 witnessed archive recordings that 0110's
`ArchiveHeads` trains on, in five contexts: raptor mobbing, begging, roost,
food and flight. The membership filter is copied from `ArchiveHeads`, as
Alala asked.

**Crow windows.** These are 3 s BirdNET windows with American Crow ≥ 0.25,
raptor < 0.05, and no non-crow species ≥ 0.05. That last condition is 0103's
pure-crow rule, so bystander birds cannot be segmented as caws. The windows
come from the same single BirdNET pass that 0112 uses.

**The one-crow cut, fixed before any archive window is scored.** The cut comes
from 0109's own data. 0109's out-of-fold `P(several)` scores are recomputed on
its cached segments, with its folds and head. The cut `T` is the largest
threshold such that at least 90% of the segments scoring below it are labelled
one crow. A window is a **single-bird window** when the frozen 0109 head
(`count_head.joblib`) gives `P(several) < T`. `T` is recorded in
`results.json` before the archive is touched. Gating on a crow detection first
is required, because the head has never seen anything else.

**Graded features, per recording, over its single-bird windows only.**

- Caws come from 0103's `segment_caws_in_windows`, unchanged except that the
  per-recording cap of 30 is lifted so the timing is complete.
- Each caw gets 0103's pre-declared 44 acoustic features (`extract_caw_44d`),
  covering duration, pitch, pitch slope, spectrum and MFCCs. They are averaged
  over the recording's single-bird caws.
- Timing, per single-bird window: caws per second, the median gap from one
  caw onset to the next, and the coefficient of variation of that gap. These
  are averaged over the windows. A window with fewer than 2 caws contributes
  its rate only.
- A recording enters only with at least 3 single-bird caws.

**PRIMARY.** Five-context classification from the 47 graded features: macro
one-vs-rest ROC-AUC, 5-fold `StratifiedGroupKFold` by recordist (seed 0),
`StandardScaler` + `LogisticRegression(C=0.1, balanced)`, and a 400-shuffle
permutation test that permutes context labels across recordists.

- **Passes** if macro AUC ≥ 0.65 with permutation p < 0.05. That means one
  crow's graded calling carries context with the crowd removed by
  construction.
- **Null** otherwise. "Context differences are crowd differences" then
  becomes the working reading.

**Secondary, declared now.**

1. **How much survives.** The same 47 features over *all* pure-crow windows of
   the same recordings. Comparing that with the primary shows what removing
   the crowd costs.
2. **Owl against hawk, single bird.** The same features, 5-fold, recordist
   grouped. This is the third attempt at the 0103/0104 question, now with
   crowd held fixed instead of posture.
3. **BirdNET on single-bird windows.** The mean BirdNET embedding over
   single-bird windows against over all windows, five contexts. This says
   whether the embedding's context signal survives the crowd removal that the
   graded features face.
4. **Residual crowd.** Primary and secondary 3, with the recording's mean
   count-head score regressed out of every feature inside each fold. This
   catches leftover crowd within the "single" windows.
5. **Which features move (descriptive).** For each context against the other
   four: the standardised mean difference of caw duration, gap, rate and
   median pitch, with a recordist-bootstrap interval. Reported, no threshold.

**Limits known in advance.** The count head is weakest on begging (0.675
within type), so single-bird selection is least reliable in the begging
context. The segmenter has not been checked against hand counts, and no hand
caw counts exist to check it against. A single-bird window can still hold a
second bird that is silent or far away, so "single bird" means "one bird
audible above the rest".

## Results

Run once, `results.json`. 245 recordings from 149 recordists had at least
three caws in single-bird windows; 2,206 of 4,603 pure-crow windows passed the
cut.

**The cut.** From 0109's out-of-fold scores, `P(several) < 0.583` keeps
1,858 of 2,479 hand-labelled segments at 90.0% one-crow precision and 87.9%
one-crow recall. Fixed before any archive window was scored.

**Primary: passes, narrowly.**

| | macro AUC | 95% interval | permutation p |
|---|---:|---:|---:|
| graded features, single-bird windows | **0.665** | 0.606 – 0.728 | 0.0025 (null mean 0.472) |

Per context: raptor mobbing 0.711, food 0.697, begging 0.694, flight 0.692,
roost 0.533. The cells are very unequal: raptor 162, begging 29, food 27,
roost 16, flight 11.

**Secondary.**

| | macro AUC | 95% interval |
|---|---:|---:|
| 1. graded, all pure windows (crowd left in) | 0.687 | 0.629 – 0.746 |
| 3. BirdNET mean, single-bird windows | 0.775 | 0.732 – 0.818 |
| 3. BirdNET mean, all pure windows | 0.804 | 0.763 – 0.843 |
| 4. graded single-bird, count score regressed out | 0.641 | 0.580 – 0.703 |
| 4. BirdNET single-bird, count score regressed out | 0.746 | 0.700 – 0.791 |

2. Owl against hawk from single-bird graded features: 0.610 (81 against 81).
No permutation was declared for this number.

5. Which features move, in standardised mean differences against the other
four contexts, with recordist-bootstrap 95% intervals:

| context | caw duration | median pitch | caw rate | median gap |
|---|---:|---:|---:|---:|
| begging | **+0.95** (0.51, 1.42) | **−0.73** (−1.36, −0.15) | **−0.48** (−0.84, −0.07) | **+0.90** (0.29, 1.47) |
| raptor mobbing | −0.09 | **+0.52** (0.21, 0.83) | **+0.47** (0.23, 0.71) | −0.12 |
| flight | **−0.72** (−1.19, −0.33) | −0.50 | −0.17 | −0.26 |
| food | −0.35 | −0.11 | **−0.49** (−0.82, −0.13) | −0.26 |
| roost | −0.21 | −0.15 | +0.01 | **−0.50** (−0.82, −0.19) |

## Reading

- **Context is not only crowd.** Every earlier context result could have been
  "more birds were calling". Restricted to stretches where one bird is
  audible, graded features still read context. Keeping only those stretches
  costs 0.02, and regressing out what the count head still sees costs another
  0.02. BirdNET's embedding behaves the same way, losing 0.03.
- **The biggest single difference is begging, and it is probably a different
  caller, not a different call.** Long, low, slow caws with long gaps are what
  a fledgling's begging sounds like. In a begging recording the "one crow" is
  most often the young bird. That makes it a statement about who is calling,
  not about one adult changing its call.
- **Flight caws are shorter (−0.72 SD).** This is the León result (shorter caws
  when the signaller is flying) seen in American Crow archive audio, on 11
  recordings. It is worth a proper test, not a claim.
- **Raptor mobbing is higher and faster from a single bird.** This is the first
  sign that a mobbing caw differs from other caws with crowd held fixed. Owl
  against hawk from the same features is 0.61, which is weak.
- Roost reads at chance from one bird (0.533), as 0110's "roost is crowd"
  predicts.

## Limits

- Archive only, recordist-grouped cross-validation. There is no sealed set
  left to replicate on (0110 spent it).
- The segmenter has not been checked against hand caw counts, and none exist.
  Single-bird windows are where it is most trustworthy, but that is argued,
  not measured.
- "Single bird" means one bird audible above the rest, by a head that is 90%
  precise on hand labels and weakest on begging (0.675 within type in 0109).
- Raptor mobbing is two thirds of the recordings. Roost and flight are 16 and
  11, so their per-context numbers are thin.
- Feature movements are descriptive. No threshold was set and none is
  claimed.

## What it changed

- **"Context differences are crowd differences" is no longer the working
  reading.** One audible crow's calling carries context at 0.665, and the
  embedding keeps most of its signal on single-bird windows. The next context
  claim can start from single-bird windows instead of having to argue the
  crowd away.
- **A graded axis beside the call type is now justified, as the León entry in
  FUTURE.txt asked.** Caw duration is the strongest single axis: begging long,
  flight short. Pitch and rate separate mobbing.
- **The flight-caw-is-shorter observation goes into FUTURE.txt** as a
  confirmatory test to pre-register. It needs more flight recordings than
  eleven, or the roof-station camera.
- Nothing for the app. A 0.665 ranking of whole archive recordings is a
  research result.
