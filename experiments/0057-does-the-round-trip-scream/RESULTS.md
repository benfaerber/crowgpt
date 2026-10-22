# 0057 — does the round-trip scream, or only the model?

## Overview

Ben had complained that the generated audio "sounds so scratchy, and it sounds almost like a human screaming," and only the first of those two words had a known owner — earlier experiments had pinned "scratchy" on the audio codec, but "screaming" had never been localised. This diagnostic listen (a five-minute labelled page, not a formal sitting) played Ben real recordings round-tripped through the codec at two quality settings alongside uncurated generated clips, to find out which component owns the scream. The answer, in Ben's own settled words: "codec makes it scratchy, generated makes it scream" — two defects with two owners. The scratch appears on every codec round-trip with no model present; the scream appeared clearly in one generated draw (seed 4) and in no round-trip of real audio.

## In depth

### The question and why it mattered

Scratchy was already the codec's: experiment 0024 Part 3 heard it on the round-trip with no model in it, and experiment 0028 confirmed it blind at 40 points. Screaming had no owner, and where it lives decides where the next GPU-week goes — it gates the decoder finetune costing (experiment 0058): if the scream were the codec's, the finetune would attack the whole audible defect, not just the scratch under it.

### The page

`crowgpt/results/compare-scream-source.html` — labelled, unblinded, describe-don't-rank:

- 8 real held-out American Crow bouts, one per recording, each as RAW / K=8 round-trip / K=32 round-trip. K=8 is the tokenizer the incumbent lives in; K=32 is EnCodec's own ceiling.
- 6 generated clips from `model-fair-k8` (the incumbent), taken in seed order with no curation — seeds 0–7, two refused for being under `MIN_GRADEABLE_SECONDS` (experiment 0044's rule). Seeds are in `manifest.json`, so any clip can be regenerated exactly.

Experiment 0053 was called before this was built, so nothing was mid-flight for these clips to contaminate.

### Results — Ben's grades, 2026-08-07

He graded quality per arm rather than localising the scream (the question reached him after the sitting); the grades carry most of the answer anyway.

Real bouts, K=8 / K=32 against raw:

| row | K=8 | K=32 |
|---|---|---|
| 1 | scratchy | pretty good, minor degradation |
| 2 | scratchy (same as 1) | pretty good, minor degradation |
| 3 | degradation, less than 1–2 | still better than K=8 |
| 4 | minor degradation | similar to K=8 |
| 5 | bad — D+ to C- | good — B+ to A- |
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

What the grades establish:

- **K=8 of real audio is audibly bad on half the rows with no model involved.** Rows 5–7 grade down to D+ — inside the range of typical generated output. The codec floor alone reaches "bad".
- **The 8→32 residual is loudly audible and call-type-dependent.** Row 5 spans D+ to A- across the same recording; row 8 is fine at both. Direct support for the decoder finetune's premise — the information to recover exists, and its absence is what Ben's ear is grading.
- **K=32 is not transparent either** ("minor degradation" at best, "mediocre" on row 6) — experiment 0028's "nothing is transparent" branch, now heard on labelled rows. The finetune's K=32-derived ceiling (1.035) is itself below raw.
- **Typical uncurated generation sits at the bottom of the K=8 round-trip range** (D+, best C+). The model is not far below the codec's floor, but it lands disproportionately at that floor, where real bouts through the same codec sometimes grade "high quality".

### The scream question, answered in three steps

Asked directly afterwards, and the record keeps all three. First: *"Not really scream — they sound more like scratchy. But I guess scratchy + caw makes my brain think scream a bit."* Then, minutes later, re-hearing row 11 (generated, seed 4): *"That is a scream. That is a clear example."* And the settled reading, his words:

> **"codec makes it scratchy, generated makes it scream."**

The founding complaint decomposes into two defects with two owners. The scratch is the codec's — heard on every K=8 arm with no model present, consistent with experiments 0024 and 0028. The scream is the model's — clearly present in at least one of six uncurated draws, and in no round-trip of real audio at any K.

### Caveats

This was a diagnostic listen, not a sitting: labelled, unblinded, describe-don't-rank. The grades reached Ben before the scream question did, so scream localisation rests on his follow-up re-listen rather than a pre-registered protocol, and the positive exemplar is a single draw out of six.

### What the answer changed

- **The decoder finetune stays supported, as the scratch's owner.** The codec floor reaches D+ on real audio, the 8→32 residual is large and call-type-dependent, and nothing about the scream finding weakens that. Experiment 0058's Goodhart-aware gate (AST-FAD, churn/density, labelled listen) is the one to use. What the finetune can no longer claim is the *whole* audible defect.
- **The scream earns its own experiment, starting from an exemplar on disk.** Seed 4 is regenerable bit-exactly and tagged by ear as a clear scream; seeds 2, 3, 5, 6 and 7 are the same model on the same page without the tag. Measuring what separates seed 4 from its neighbours is the obvious first step (experiment 0046 traced "modem" to a stuck coarse codebook the same way). That became experiment 0059.
- **Experiment 0037's warning stands unchanged:** fixing the scratch is not yet known to fix generation, and typical draws grading at the bottom of the K=8 range says the model chooses bad points inside the codec's space even before it screams.
