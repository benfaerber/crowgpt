# 0081 — can a machine hear the voice gap?

**2026-08-19, predictions before results — and before Ben's first dose** ·
build: ~25 m CPU · **answer: pending, validated against voice-0078**

## The question

Ben's ear ranks model-calltype above the b32 candidate; every in-house
instrument was blind to why. Two off-the-shelf judges get one shot each at
hearing it, scored on the exact clips of the voice-0078 pool **before he
grades them**, so his blinded sitting arrives as the validation set rather
than the thing being imitated:

- **AST-FAD** (0063's machinery, `crowgpt.metrics.frechet_distance` over
  `AstEmbedder`): distributional distance from each arm's clips to the pool's
  real clips, with the real-vs-real split as the floor. FAD agreed with Ben's
  ear once already, on the decoder.
- **CLAP** (laion/clap-htsat-unfused via transformers): each clip scored
  against crow prompts and against Ben's own defect vocabulary — "a person
  screaming", "a frog croaking", "a metallic robotic sound", "an alien sound
  effect" — as a crow-minus-defect margin. His descriptions become the
  instrument.

## Predictions (sealed now)

1. FAD: b32 → real exceeds calltype → real; both exceed the real-vs-real floor.
2. CLAP margin: real > calltype > b32; and b32's alarm clips sit measurably
   closer to "a person screaming" than calltype's do.
3. After the sitting: whichever judge ranks arms the way Ben's graded margins
   do gets promoted to a standing instrument; a judge that disagrees with him
   is recorded as a null and never used to pre-screen a pool.
4. The null shape: both judges shrug (differences inside the floor / margins
   overlapping). Then the voice gap is invisible to general audio embeddings
   too, and the sitting stands alone — worth knowing before anyone builds an
   automated grading loop on these judges.

## Build

`run.py`, CPU only (the card is 0080's tonight): AST embeddings + FAD per
arm; CLAP similarities per clip with per-call-type breakdown from the pool
filenames; everything into results.json. Correlation with Ben's grades is a
separate script run after the sitting completes.

## Result — the machines invert the ranking, or shrug

Both sealed predictions about arm order were **falsified**:

| judge | floor / real | calltype | b32 |
|---|---|---|---|
| AST-FAD (lower = closer to real) | 42.8 | 55.8 | **41.2** |
| CLAP crow-minus-defect margin | 0.312 | 0.306 | **0.308** |

FAD puts b32 *below the real-vs-real floor* — its distribution reads as
close to real as real is to itself — while calltype sits 13 points above.
That is the opposite of the informal chat ranking. Small-sample caveat is
real (44–56 clips, 768 dims; below-floor is within wobble) but the direction
offers no support for calltype's superiority. CLAP is a flat shrug: margins
identical to three decimals across arms and per type, and b32's clips are
*not* closer to "a person screaming" than calltype's (0.196 vs 0.202).

Per the sealed rule 3/4: **neither judge is promoted**; this is the recorded
null. Two readings stay open until voice-0078 lands, and the sitting now
decides between them:

- Ben's blinded grades prefer calltype → the voice gap is real and invisible
  to general audio embeddings; sittings stand alone, and no machine
  pre-screens a pool.
- The sitting comes back near a coin flip → the informal chat impression did
  not survive blinding (expectation, context, or clip length carried it),
  which the project has seen before and the pool system exists to catch.

Either way the 48 answers were never more valuable.

## What it changed

- No automated grading loop gets built on FAD or CLAP for now — the judges
  and the ear must first be reconciled by the sitting.
- clap_per_clip.json is kept for the post-sitting correlation, which is the
  step that could still rescue FAD as an instrument (its per-arm direction
  may correlate with graded margins even if the informal ranking does not).
