# 0057 — does the round-trip scream, or only the model?

**2026-08-07** · diagnostic listen, not a sitting · **answer, corrected the
same hour: the scratch is the codec's on every row — and the scream is real,
clearly present in one generated draw (row 11, seed 4) and in no round-trip
of real audio. Two defects, two owners.**

## The question

Ben's words for the generated audio: *"it sounds so scratchy, and it sounds
almost like a human screaming. So it's kinda taxing to grade."* Those are two
words, and only one of them has an owner. **Scratchy is the codec's** — 0024
Part 3 heard it on the round-trip with no model in it, 0028 confirmed it blind
at 40 points. **Screaming has never been localised**, and where it lives decides
where the next GPU-week goes.

This costs a five-minute listen, not a sitting, and it gates the decoder
finetune costing (0058): if the scream is the codec's, the finetune attacks the
whole audible defect, not just the scratch under it.

## The page

`crowgpt/results/compare-scream-source.html` — labelled, unblinded, describe
don't rank:

- **8 real held-out American Crow bouts**, one per recording, each as
  RAW / K=8 round-trip / K=32 round-trip. K=8 is the tokenizer the incumbent
  lives in; K=32 is EnCodec's own ceiling.
- **6 generated clips from `model-fair-k8`** (the incumbent), taken in seed
  order with no curation — seeds 0–7, two refused for being under
  `MIN_GRADEABLE_SECONDS` (0044's rule). Seeds are in `manifest.json`, so any
  clip can be regenerated exactly.

0053 was called before this was built, so nothing is mid-flight for these
clips to contaminate.

## How to read the answer

| what Ben hears | what it means |
|---|---|
| K=8 of real caws already screams | the model's share of the defect is near zero; the decoder finetune is the whole game |
| K=8 scratches but does not scream; generated rows scream | the scream is the model's contribution on top of the codec's scratch — it earns its own experiment before decoder work |
| even K=32 screams | the defect is the encoder/decoder pair itself, not the 8-codebook truncation; the finetune's premise still holds but the K=32 ceiling argument (0028's 1.035) does not |
| RAW screams | the corpus itself carries it and every downstream judgement needs rethinking (not expected — his field recordings don't scream) |

## Results — Ben's grades, 2026-08-07

He graded quality per arm rather than localising the scream (the question
reached him after the sitting); the grades carry most of the answer anyway.

Real bouts, K=8 / K=32 against raw:

| row | K=8 | K=32 |
|---|---|---|
| 1 | scratchy | pretty good, minor degradation |
| 2 | scratchy (same as 1) | pretty good, minor degradation |
| 3 | degradation, less than 1–2 | still better than K=8 |
| 4 | minor degradation | similar to K=8 |
| 5 | **bad — D+ to C-** | **good — B+ to A-** |
| 6 | bad | mediocre |
| 7 | bad | good |
| 8 | high quality | high quality |

Generated (model-fair-k8, uncurated, rows 9–14 = seeds 2–7):

| row | seed | grade |
|---|---|---|
| 9 | 2 | C+ — "matches shape, coarse" |
| 10 | 3 | D+ |
| 11 | 4 | D+ |
| 12 | 5 | D+ |
| 13 | 6 | C- to C+ |
| 14 | 7 | D+ |

**What the grades establish without any follow-up:**

- **K=8 of real audio is audibly bad on half the rows, with no model
  involved.** Rows 5–7 grade down to D+ — inside the range of typical
  generated output. The codec floor alone reaches "bad".
- **The 8→32 residual is loudly audible and call-type-dependent.** Row 5
  spans D+ to A- across the same recording; row 8 is fine at both. Whatever
  those eight coarse rows drop, it is not dropped evenly across call types.
  This is direct support for the decoder finetune's premise — the information
  to recover exists, and its absence is what Ben's ear is grading.
- **K=32 is not transparent either** ("minor degradation" at best, "mediocre"
  on row 6). 0028's "nothing is transparent" branch, now heard on labelled
  rows: the finetune's K=32-derived ceiling (1.035) is itself below raw.
- **Typical uncurated generation sits at the bottom of the K=8 round-trip
  range** (D+, best C+). The model is not grading far below the codec's own
  floor — but it lands disproportionately AT that floor, where real bouts
  through the same codec sometimes grade "high quality".

**The scream question, asked directly afterwards — answered in three steps,
and the record keeps all three.** First: *"Not really scream — they sound more
like scratchy. But I guess scratchy + caw makes my brain think scream a bit."*
Then, minutes later, re-hearing row 11 (generated, seed 4): *"That is a
scream. That is a clear example."* And the settled reading, his words:

> **"codec makes it scratchy, generated makes it scream."**

So the founding complaint decomposes into two defects with two owners. The
scratch is the codec's — heard on every K=8 arm with no model present,
consistent with 0024 Part 3 and 0028. The scream is the model's — clearly
present in at least one of six uncurated draws, and in no round-trip of real
audio at any K.

## What the answer changed

Both halves of the next move now have evidence rather than a guess:

- **The decoder finetune stays supported, as the scratch's owner.** The codec
  floor reaches D+ on real audio, the 8→32 residual is large and
  call-type-dependent (row 5: D+ to A- on one recording), and nothing about
  the scream finding weakens that. 0058's Goodhart-aware gate (AST-FAD +
  churn/density + labelled listen) is the one to use. What the finetune can no
  longer claim is the *whole* audible defect.
- **The scream earns its own experiment, and it starts with an exemplar on
  disk.** Seed 4 is regenerable bit-exactly and tagged by ear as a clear
  scream; seeds 2, 3, 5, 6, 7 are the same model on the same page without the
  clear tag. What the instruments say separates seed 4 from its neighbours is
  the obvious first measurement (0046 traced "modem" to a stuck coarse
  codebook the same way — a described defect, then its token signature).
- 0037's warning stands unchanged: fixing the scratch is not yet known to fix
  generation, and typical draws grading at the *bottom* of the K=8 range (D+
  where real round-trips reach "high quality") says the model chooses bad
  points inside the codec's space even before it screams.
