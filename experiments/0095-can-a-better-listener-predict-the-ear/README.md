# 0095 — Can a better listener predict the ear?

**2026-11-15** · GPU about 40 minutes · **answer: no. A machine judge stays
near 0.5 whatever listens, and whatever amount of grading it learns from.**

## The question

Whether a CrowGPT candidate sounds better is decided by Ben's ear, in
blinded sittings. Two sittings have been open since September (voice-0078 at
16 of 48, capacity-0086 at 2 of 48), so no new candidate can be judged.
0082 distilled a judge from his 304 completed grades and reached a
pool-held-out rank correlation of 0.48. The bar for a pre-screen, set in
FUTURE.txt, is about 0.7 and 90% on the catch trials. Two routes were left
untried: a better listener under 0082's method, and an audio-language model
asked the question he answers.

## Method

Five completed pools, 304 graded trials, 43 of them catch trials where one
clip is a real recording. Every fitted judge is scored on a pool it never
saw, and its ridge strength is chosen inside the training pools.

- **`run.py`, listeners.** Each clip becomes one vector: 0082's own input
  (AST plus the dust features), five layers of the Whisper large-v3-turbo
  encoder, CLAP, the generator's own codec latents, and plain mel statistics.
  A ridge reads the difference between the two clips, fitted in both orders
  so swapping the clips flips the answer. `+anchor` adds how far each clip
  sits from the real reference. One ensemble averages four judges.
- **`curve.py`.** The best judge fitted on one, two, three and four pools.
- **`shortcut.py`.** Three one-number judges, to see what a trivial cue gets.
- **`realness.py`.** A judge that never sees a grade: a classifier learns
  real recording against generated clip, and its score stands in for the ear.
- **`judge_alm.py`.** Qwen2-Audio-7B-Instruct in 4-bit hears the reference
  and both clips with the pool's own question, and its answer is the
  next-token odds of "A" against "B", asked in both orders and halved.
  Zero-shot, so every pool is a test.

## Results

Mean rank correlation with the ear over the five held-out pools. "Compare
only" leaves the catch trials out. Ben himself is 39 of 46 on catches.

| judge | mean | worst pool | compare only | catches right |
|---|---|---|---|---|
| whisper, last layer | 0.54 | 0.33 | 0.50 | 33 of 43 |
| ensemble of four | 0.53 | 0.43 | 0.51 | 32 of 43 |
| whisper, layers 8 and 24 | 0.52 | 0.33 | 0.47 | 30 of 43 |
| whisper, layer 8 | 0.51 | 0.36 | 0.48 | 29 of 43 |
| ast + dust (0082's input) | 0.50 | 0.38 | 0.46 | 32 of 43 |
| clap | 0.49 | 0.35 | 0.49 | 32 of 43 |
| mel statistics | 0.41 | 0.32 | 0.42 | 29 of 43 |
| codec latents | 0.36 | 0.30 | 0.31 | 28 of 43 |
| real-vs-generated classifier | 0.29 | 0.09 | 0.13 | 38 of 43 |
| audio-language model | 0.23 | 0.17 | | 20 of 43 |

The anchored variants are in `results.json`; none beats its plain form by
more than 0.01.

More grades, same judge (whisper, last layer):

| pools fitted on | answers | mean on the held-out pool |
|---|---|---|
| 1 | 61 | 0.49 |
| 2 | 122 | 0.51 |
| 3 | 182 | 0.52 |
| 4 | 243 | 0.53 |

One-number judges: the longer clip −0.03, the louder clip 0.02, the more
periodic clip 0.23.

The audio-language model's taste for a position is fourteen times its taste
for a clip: mean absolute log odds 0.98 for "A whichever clip is A" against
0.07 for the clip itself.

The chosen judge (whisper last layer, anchored) on the 16 voice-0078 trials
already graded, which no judge was fitted on: 0.44, the right side in 11 of
15 decided trials.

## What it says

- **The listener is not the limit.** AST, CLAP and four Whisper layers all
  land between 0.46 and 0.54. Five pools cannot tell those apart.
- **More grading is not the limit either.** One sitting's worth of answers
  already gives 0.49 and four give 0.53. A judge of this kind will not reach
  0.7 by Ben grading more.
- **The judge hears something real.** It is not reading length or loudness,
  and it does as well on trials with two generated clips as on the catches.
  Periodicity alone gets 0.23, which is 0069's dust finding.
- **Telling real from generated is a different skill from ranking two
  generated clips.** The classifier that never saw a grade matches Ben on
  the catches (38 of 43) and is near useless between two generated clips
  (0.13). So a pile of real and generated audio cannot stand in for grades.
- **The audio-language model is the predicted null.** It picks the real
  recording less than half the time and mostly answers "A".
- **The ear's own verdicts are close to zero in most pools.** Ben's mean
  margin between arms is −0.03, −0.2, +0.2 and +0.05 in four of the five
  pools, and the same comparison changed sign between 0067 and 0067b. Only
  the churn pool has arms the ear clearly separates (+0.83, −0.69), and
  the three judges checked (whisper, ast + dust, the ensemble) get both
  directions right. Where the ear is
  sure, the judge agrees; where the judge is unsure, so is the ear.

## Caveats

- Thirteen listeners and their variants were compared on the same five
  pools, so the 0.54 against 0.50 is a selection among near-equals, not a
  gain. The sealed predictions are the clean test.
- How repeatable Ben's own grade is on the same pair has never been
  measured: no pool repeats a trial. Without it, 0.5 cannot be called close
  to or far from the ceiling.
- One audio-language model, one prompt, 4-bit weights. A larger hosted
  model was not tried.

## Sealed

`sealed.json` (commit d661075) holds the chosen judge's prediction for each
of the 78 ungraded trials. In summary it expects no clear winner in either
sitting: voice-0078 at a mean margin of 0.03 toward calltype (52% of
trials favouring b32), capacity-0086 at 0.06 toward CrowGPT2 (61% of trials).
`alm_scores.json` holds the audio-language model's answer for the same
trials.

## What it changed

- **Decided not to build an automated pre-screen.** No judge reaches the
  0.7 and 90% bar, and neither a better listener nor more grades moves it.
- **Decided not to pursue the audio-language judge further.** It fails the
  catch trials, the one test with an outside answer.
- The whisper judge is kept as a coarse filter only: it agrees with the ear
  where arms differ by most of a grade, so it can say "these two candidates
  are far apart" and nothing finer.
- New question for the pool builder, in FUTURE.txt: repeat a few trials in
  each sitting so the ear's own repeatability is known. That number is the
  ceiling every judge here was measured without.
- The two open sittings still need Ben. Nothing here shortens them.
