# 0036 — What would more manual labelling buy?

## Overview

Manual labels had previously produced a large jump in the call-type classifier's scores, so the question was whether to build a labelling pipeline and collect more of them. The experiment fitted learning curves and transfer tests over 2,338 keyed crow-tools segments across 1,097 recordings, plus the 60 human labels on Ben's own field captures. The answer is that more labels of the existing kind buy almost nothing: the archive learning curve is flat from about 1,200 segments, doubling the corpus is worth only +0.011 macro-F1, and the hard class (mobbing) does not improve across a tenfold increase in labels because its limit is the audio representation, not label volume. The one large, fixable defect found is that the shipped classifier cannot say "nothing here" — it confidently assigns a call type to 97% of segments a human marked as containing no crow — so the labelling pipeline is still worth building, pointed at negatives and at Ben's own recordings rather than at more archive call types.

## In depth

### Correcting the premise

The prompt was "labels took the classifier from 61% to 91%". Those are not the same metric: 0.61 is the majority-class baseline on 117 archive clips, and "91%" is a one-vs-rest AUC after the crow-tools labels landed. The honest like-for-like — same features, same pooling, same logreg, same recording-grouped harness, only the labels changed:

| class | archive weak tags (n=129) | + crow-tools (n=2,654) |
|---|---|---|
| alarm call | 0.724 | 0.939 |
| song | 0.649 | 0.904 |
| call | 0.699 | 0.950 |
| flight call | 0.913 | 0.975 (corpus-boundary artifact) |
| begging | — | 0.914 |

The effect was real and entirely labels; the question was whether the next 3,000 do anything like what the first 3,000 did.

A three-point pilot (single seed, 3-fold: 238 → 0.715, 747 → 0.755, 2,253 → 0.845) looked like a curve still climbing, and it was wrong — with three seeds and five folds the same sweep is flat from about 1,200 segments. The pilot had no point between 747 and 2,253, exactly where the curve turns over, against a seed spread reaching ±0.10 at small n. A pilot sized to answer "can this see anything" cannot also be read for "what does it say".

### The features had to be rebuilt — a finding of its own

The cached features (`pooled_embeddings_crowtools_all-public.npz`) store no segment key, so joining rows to raw flags means matching by position within a file. That was sound when experiment 0012 ran and is not now: the cache holds 2,494 rows against 2,339 segments with audio, 98 files disagree on segment count, and in at least one file the cached label order is a permutation of the corpus order. 0012's `align()` caught it and stopped the run. `prepare.py` re-embeds the corpus with the segment key on the row; n is 2,338 over 1,097 recordings, so these numbers sit beside experiment 0025's. Worth fixing upstream: `build_dataset.py` should write the key.

### Arm A — the archive learning curve is flat from 1,200

Subsampled by recording (never by segment — that is the leak) at 8 budgets, 5-fold recording-grouped CV, 3 seeds. The tail of the curve: 1,213 segments → macro-F1 0.848 (sd .003); 2,110 → 0.849 (sd .004). Between those points labels grew 74% and macro-F1 moved 0.001. A power-law fit (ceiling 0.884, rmse 0.005) puts 2× the corpus at 0.863 (+0.011) and 4× at 0.870 (+0.018). The decision rule was "< 0.02 → not the lever", and +0.011 clears it comfortably: no bulk archive labelling pass. Only `song` improved materially over the whole sweep (0.529 → 0.889); `alarm call` was at 0.965 with 176 segments and has learned nothing since.

### Arm B — mobbing is not label-limited

Raw crow-tools flags, restricted to segments where the flag was actually asked, scored in average precision because AUC ignores prevalence. Mob: AP 0.769 at 225 segments, 0.706 at 2,338 — ten times the labels, no improvement, with prevalence steady at 0.29–0.34, so this is not a prevalence artifact. Fitted ceiling 0.719; AP 0.80 and 0.85 both come back unreachable. Rattle saturated at a tenth of the corpus (AP 0.80 needs 214 segments, 9% of what exists; current 0.901). Alert behaves like mob (0.507 → 0.644, ceiling 0.658).

The decision rule was "within ~2× → collection problem; 10× → representation problem"; the answer is the stronger version of the second — unreachable. The lever is the representation, and experiment 0025 already found one: Perch lifts mob-vs-alert from 0.637 to 0.760 on the same corpus. This also settles what experiment 0012 could not distinguish: mob is hard, not thin.

`overlap_wall.py` supplies the causal story. Splitting evaluation by crow count, only `mob` and `alert` collapse when several crows call at once (mob's lift over chance falls from 2.93× to 1.33×; alert's from 3.13× to 1.88×), while `rattle` and `softSong` get better and `begging` is flat. Mobbing is defined by several crows calling over each other, and overlapping callers are exactly the condition under which the features stop separating anything — the class is hard because the class is the failure mode. What would fix it is a per-event detector (the standing Voxaboxen entry in `FUTURE.txt`), not a backbone and not labels.

### Arm C — no acquisition strategy beats random

Random, cluster-stratified and uncertainty sampling at matched budgets, scored on a held-out 25% of recordings: all three plateau by about 400–600 labels, seed spreads (±0.05) wider than every gap. No sample-efficiency argument for clustering — though cluster-sorting the queue remains worth copying for labelling throughput. Uncertainty sampling not winning means the labelling pipeline does not need a model in the loop, which is the expensive half of that build.

### Arm D — archive labels transfer to Ben's own audio

The 50 human labels on ★kept captures (13 captures) plus the rest of the 60 field labels give 52 trainable spans — enough to detect a catastrophic domain gap, not a subtle one. Pooled over the whole labelled span, the shipped head scores top-1 0.769 against a constant-classifier baseline of 0.519 (0.857 vs 0.595 on ★kept only). It transfers — a different answer from experiment 0018 — and the poolings explain why: with a single 3 s window, 41 of 52 answers are "alarm call" (0018's exact collapse signature), because a single window has std = 0 and max = mean, leaving a third of the feature vector empty. Pooling over the span drops that to 25 of 52 and recovers 7 of 12 `call`. The actionable rule: pool over the call region, never a single window. Caveats kept attached: `song` and `flight call` have one field label each (untested rather than passing), 27 of 52 labels are `alarm call` so the constant baseline is high, and top-1 of a one-vs-rest head is not a calibrated confidence.

### Arm E — three crow-tools practices measured

- **E1, quality filtering: small real win.** `quality ≥ 2` gives macro-F1 0.861 against 0.850 for a size-matched random drop of the same 69 rows. Free, taken.
- **E2, the head cannot say "nothing here" — the finding of the experiment.** Handed 572 segments a labeller explicitly marked `crowCount = 0`, the shipped four-class head assigns a call type at p > 0.5 to 97.0% of them, at mean top probability 0.898, calling 388 of them `alarm call`. A five-class head with `none` rejects 70.6% of the garbage for 0.021 of CORE macro-F1. This is invisible to every metric the project reports and fixable with the cheapest labels a human can give — negatives. (Caveat: recordings may overlap between fit and garbage sets, so 97.0% is an upper bound on the failure; it is not a small enough number for that to matter.)
- **E3, auxiliary heads: clean null.** Adding crow-tools' crowCount/crowAge/quality losses moves macro-F1 0.856 → 0.852 (−0.004). The 240 K-parameter MLP also barely beats the logreg (0.856 vs 0.852), so "a regularised linear model is the right size for this corpus" survives at 2,110 rows.

### Head to head with crow-tools, and their numbers

Running our features through their exact protocol (segment-level 88/12 split, seed 18202, balanced accuracy) gives a mean of 0.853 against their reported 0.864 — a tie on four of five classes, with one real loss (`alert`, −0.090, unresolved between three candidate causes). Their split is worth +0.043 on average and up to +0.085 on their most concentrated class, behaving exactly as a leak should — the gain tracks how concentrated a class is inside recordings. Their reported figures would land near 0.82 under our harness; nobody is clearly ahead, the protocols were doing most of the talking. A recordist-disjoint split (567 recordists, read from the archive's `library.csv` for the first time) changes nothing — every grouped number the project has reported stands.

Also inventoried: 14 GB of audio in their fork including all 111 recordings cawtalker is missing (stranding 170 labelled segments), free behavioural and location metadata, playback-contaminated recordings to drop, and hard-negative download manifests. Their model checkpoints are unloadable LFS stubs; their separator — built for exactly the overlap problem found here — was never wired into anything. Their labels are not a random sample of crow vocalisation: their detector is their classifier, so the pool is shaped by what the model already found. Two of their practices are bugs, not features: feeding a 16 kHz model audio at 8 kHz, and a train/inference denoising mismatch.

### The field-label gap that outranks the rest

After 60 field labels: zero use `mobbing`, `scold`, `rattle` or `contact call`; the re-answer mechanism has never fired; the first 35 labels contained 67.7 seconds of actual call audio. The corpus cannot currently score a mobbing detector at all — and field mobbing labels are now wanted as a test set, not a training set, since arm B says training signal is not what is missing. Sharpest of all, from experiment 0012: the corpus's `call` class is a rattle detector — the class the field will exercise hardest, contact calls, has zero examples anywhere in the project. No amount of archive labelling fixes that; Ben's own microphone does.

### What this changed

1. No archive labelling push for the CORE classes — Ben has roughly twice the labels those four classes can use.
2. Mobbing moved off the labelling roadmap and onto the representation roadmap (next try: Perch, per experiment 0025); the `FUTURE.txt` split-alarm entry should be updated accordingly.
3. The head needs a `none` class, and that is where manual labelling pays — the single most valuable labelling change available, and the fastest to collect. The field vocabulary's `not_a_crow` chip exists but is `trains = 0`.
4. Pool over the call region, never a single window; audit every caller of `pool`.
5. `build_dataset.py` should write the segment key to end a whole class of silent mis-join bugs.

Two measured nulls banked: auxiliary heads do not help, and no acquisition strategy beats random. And one free win taken: filter to `quality ≥ 2`.

### What this cannot say

Arms A–C measure "more labels like crow-tools'", a pool shaped by what their model already found — a flat curve on it proves more of the same will not help, not that no labelling scheme could. Arm D is 52 labels over 13 captures and can only detect a catastrophic gap. Nothing here measures contact calls, because nothing anywhere has one.
