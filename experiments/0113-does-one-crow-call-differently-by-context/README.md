# 0113 — Does one crow call differently in different contexts?

**2026-11-22** · CPU · **answer: see Results**

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

_Filled in after the single run._
