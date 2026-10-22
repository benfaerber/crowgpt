# 0036 — What would more manual labelling buy?

**2026-08-02** · 2,338 keyed crow-tools segments over 1,097 recordings, plus 60
field labels · recording-grouped CV throughout

## The answer

**Almost nothing, for the classes the corpus already covers.** The archive
learning curve is flat from about 1,200 segments and the fit says doubling the
corpus buys **+0.011 macro-F1** — half the 0.02 the design set as the bar. Ben
already has roughly twice the labels he needs for the four CORE classes.

**Mobbing is not a labelling problem.** Its average precision does not move
across a tenfold increase in labels — 0.769 at n=225 against 0.706 at n=2,338,
with prevalence steady near 0.30. The fitted ceiling is **0.719**, and AP 0.80 is
not reachable by adding labels of this kind at all. Nothing about the mobbing
plan survives this: no number of mobbing labels fixes mobbing.

**And the head cannot say "nothing here."** Handed 572 segments a human
explicitly marked as containing no crow, the shipped four-class head assigns a
call type with p > 0.5 to **97.0%** of them, at a mean top probability of
**0.898**, calling 388 of them *alarm call*. That is the largest defect this
experiment found, it is invisible to every metric the project currently reports,
and it is fixable with labels — just not labels of call types.

So: build the labelling pipeline, but point it at negatives and at your own
recordings, not at more archive call types.

---

## The question behind the question

"Labels took the classifier from 61% to 91%, so should I build a labelling
pipeline and collect more?"

Before designing anything, the premise needs correcting, because it changes what
"more of the same" would even mean.

**61% and 91% are not the same metric.** The 0.61 is
`pipelines/representation/results/metrics.json → baseline_majority_acc` — the
majority-class baseline on 117 archive clips, not a model score. The model at
that point scored 0.65 accuracy / 0.48 macro-F1. The "91%" is a *one-vs-rest AUC*
after crow-tools landed — specifically `song` at 0.904, or `alarm call` at 0.939.

The honest like-for-like, same features, same pooling, same logreg, same
recording-grouped harness, **only the labels changed**:

| class | archive weak tags (n=129) | + crow-tools (n=2,654) |
|---|---|---|
| alarm call | 0.724 | **0.939** |
| song | 0.649 | **0.904** |
| call | 0.699 | **0.950** |
| flight call | 0.913 | 0.975 † |
| begging | — | 0.914 |

† corpus-boundary artifact, already flagged in that file's own `caveats`.

So the effect is real and it was entirely labels. The question is whether the
*next* 3,000 labels do anything like what the first 3,000 did — and that is a
learning-curve question, which is answerable today from cached features for
roughly two hours of CPU.

**A three-point pilot was run first, to check the experiment could see a signal
at all** — single seed, 3-fold, single-label rows: 238 → 0.715, 747 → 0.755,
2,253 → 0.845. It looked like a curve still climbing, and it was read that way in
the design.

**It was wrong, and the way it was wrong is worth keeping.** With three seeds and
five folds the same sweep is flat from about 1,200 segments (arm A below). The
pilot's apparent climb came from having only three points, none between 747 and
2,253 — exactly the range where the curve turns over — and one seed, against a
seed spread that reaches ±0.10 at small n. A pilot sized to answer "can this see
anything" cannot also be read for "what does it say", and it very nearly set the
prior for the whole experiment in the wrong direction.

## What could be meant by "more labels", and why they are different experiments

Three distinct things, with three different prices and three different payoffs:

1. **More archive segments** (1 s windows) — cheap, remote,
   someone else's audio. Arm A/B.
2. **More field labels** on Ben's own recordings — expensive, and the only ones
   in the domain the app actually runs in. Arm D.
3. **Finer labels** — `mobbing` vs `alert`, `rattle`, `contact call`. Arm B.

Experiment 0018 is the reason these cannot be lumped together. The shipped head
scores **0.904–0.975 AUC on its own 1-second segments** and, applied to 2.4 s
crowgpt bouts, got the top class right **56%** of the time when *always guessing
"alarm call" scores 69%*. A head is a fact about its unit and its domain. If that
same collapse happens on field audio, the archive learning curve is measuring an
axis that does not reach the app, and arm D matters more than arms A–C combined.

## Arms

Everything below uses 3,072-d pooled BirdNET features and the same
`StratifiedGroupKFold` harness as 0012 and 0025, so the numbers land next to
those rather than beside them.

### The features had to be rebuilt, and that is a finding of its own

The design said "already-cached features". It could not use them.
`pooled_embeddings_crowtools_all-public.npz` stores only `(X, Y, groups)` — no
segment key — so recovering a row's raw flags means matching cached rows to
corpus segments **by position within a file**. That is what 0012 did, and it was
sound when 0012 ran. It is not sound now:

- the cache holds **2,494** rows; only **2,339** segments still have audio
- **98 files** disagree on segment count between cache and corpus
- and in at least one file (`212803571`) the cached label order is a
  *permutation* of the corpus order — cached `[alarm, alarm, alarm, alarm+song]`
  against corpus `[alarm, alarm, alarm+song, alarm]`

0012's `align()` catches this and stops, which is exactly what it was written to
do; it stopped this run too. A positional join would have handed one call's flags
to another call's audio, and every mob and rattle number here would have been
noise wearing a decimal point.

So `prepare.py` re-embeds the corpus with the segment key **on the row**, and the
join became a dictionary lookup. n is 2,338 over 1,097 recordings — the rows whose
audio is present, which is 0025's corpus, so these numbers sit beside 0025's
rather than 0012's.

**Worth fixing upstream:** `build_dataset.py` should write the key. The cost of
not writing it is that every downstream experiment must either re-embed or trust
an ordering that has already silently drifted once.

### A. The learning curve on archive labels — flat from 1,200

Subsampled **by recording** (never by segment — that is the leak) at 8 budgets,
5-fold recording-grouped CV, 3 seeds.

| segments | recordings | macro-F1 | sd | alarm AP | begging AP | call AP | song AP |
|---|---|---|---|---|---|---|---|
| 176 | 85 | 0.748 | .033 | 0.965 | 0.915 | 0.898 | 0.529 |
| 347 | 159 | 0.781 | .098 | 0.972 | 0.677 | 0.916 | 0.822 |
| 585 | 266 | 0.817 | .016 | 0.975 | 0.883 | 0.874 | 0.764 |
| 822 | 425 | 0.834 | .026 | 0.973 | 0.822 | 0.920 | 0.867 |
| 1,213 | 585 | **0.848** | .003 | 0.981 | 0.856 | 0.929 | 0.881 |
| 1,470 | 744 | 0.843 | .004 | 0.980 | 0.837 | 0.939 | 0.873 |
| 1,827 | 904 | 0.845 | .009 | 0.974 | 0.848 | 0.923 | 0.879 |
| 2,110 | 1,063 | 0.849 | .004 | 0.978 | 0.866 | 0.920 | 0.889 |

The last four rows are the finding. Between 1,213 and 2,110 segments — a 74%
increase in labels — macro-F1 moves from 0.848 to 0.849, inside a seed spread of
±0.004. **The curve is flat, and it went flat at roughly half the corpus Ben
already has.**

Power law `f1(n) = c − a·n^(−b)`, fitted on the means (rmse 0.005):

| | |
|---|---|
| ceiling `c` | 0.884 |
| at current n (2,110) | 0.852 |
| at 2× | 0.863 — **+0.011** |
| at 4× | 0.870 — +0.018 |

> **Decision rule was < 0.02 → not the lever. +0.011 clears it comfortably.**
> A bulk archive labelling pass is not justified. Note also that only `song`
> improved materially over the whole sweep (0.529 → 0.889); `alarm call` was at
> 0.965 with 176 segments and has learned nothing since.

### B. mob, rattle and alert in average precision — the decisive arm

Raw crow-tools flags, restricted to segments where the flag was actually *asked*
(0012's trap: a missing key is not a negative). AP rather than AUC, because AUC
ignores prevalence and that is exactly what flatters mob.

**mob — ten times the labels, no improvement:**

| segments | positives | prevalence | AP | sd | AUC |
|---|---|---|---|---|---|
| 225 | 65 | 0.289 | **0.769** | .027 | 0.875 |
| 524 | 176 | 0.336 | 0.711 | .049 | 0.835 |
| 905 | 268 | 0.296 | 0.693 | .022 | 0.831 |
| 1,645 | 481 | 0.292 | 0.711 | .036 | 0.855 |
| 2,338 | 689 | 0.295 | **0.706** | .013 | 0.850 |

Prevalence holds between 0.29 and 0.34 across the whole sweep, so this is not the
prevalence artifact that AP curves are prone to — it is flat because mob is flat.
The fit puts the ceiling at **0.719**, and both AP 0.80 and 0.85 come back
unreachable.

**rattle — saturated at a tenth of the corpus:**

| segments | positives | prevalence | AP | AUC |
|---|---|---|---|---|
| 225 | 60 | 0.267 | 0.817 | 0.951 |
| 524 | 100 | 0.191 | 0.938 | 0.979 |
| 1,645 | 331 | 0.201 | 0.880 | 0.961 |
| 2,338 | 511 | 0.219 | **0.901** | 0.967 |

The fit says AP 0.80 needs **214 segments (9% of what exists)** and 0.85 needs
**390 (17%)**. Rattle was solved before most of the labelling happened.

**alert** behaves like mob: 0.507 → 0.644 with a fitted ceiling of 0.658.

> **Decision rule was: within ~2× → collection problem; 10× → representation
> problem.** It is neither — it is *unreachable*, which is the stronger version
> of the second answer. **Mobbing is not label-limited.** The lever is the
> representation, and 0025 already found one: Perch lifts mob-vs-alert from 0.637
> to 0.760 on the same corpus, where BirdNET-centred *drops* it to 0.540.
>
> Read against 0012, this also settles something. 0012 could not distinguish "mob
> is thin at 138 segments" from "mob is hard". It is hard.

### C. Does labelling *order* matter? — the arm that designs the pipeline

Simulate three acquisition strategies at matched budget, seeded identically:

- **random** (the honest baseline)
- **cluster-stratified** — round-robin over crow-tools' 86 `cluster` ids, which
  are already in the vendored labels and currently unused by CrowGPT
- **uncertainty sampling** — train on a seed set, acquire the lowest-margin
  segments, retrain

Scored on a held-out 25% of **recordings**; acquisition only ever sees the pool.

| labels | random | cluster-stratified | uncertainty |
|---|---|---|---|
| 100 | 0.772 | 0.767 | 0.772 |
| 200 | 0.813 | 0.799 | 0.792 |
| 400 | 0.825 | 0.804 | 0.826 |
| 600 | **0.836** | 0.813 | 0.833 |
| 900 | 0.827 | 0.807 | 0.821 |
| 1,500 | 0.823 | 0.818 | 0.822 |

**No strategy wins.** Seed spreads run to ±0.05, wider than every gap in the
table. Random is nominally best; cluster-stratified is nominally worst. Neither
difference means anything.

The real result is the *column* rather than the comparison: all three plateau by
about 400–600 labels, which is arm A again from a different direction and on a
genuinely held-out set.

> **Decision rule was: cluster-stratified at ≤60% of labels → sort the queue by
> cluster.** It missed, so there is no sample-efficiency argument for clustering.
> But note what that does *not* say: crow-tools sorts by cluster for **throughput**
> — adjacent similar sounds make "copy previous" one click — and this arm says
> nothing against that. Cluster the queue to label faster, not to label less.
>
> Uncertainty sampling not winning is worth banking too: **the labelling pipeline
> does not need a model in the loop**, which is the expensive half of the build.

Cluster purity against the CORE label set is **0.713** with 48 of 86 clusters
≥80% pure — informative, but evidently not informative enough to beat chance
ordering on a saturated problem.

### D. What is an archive label worth on Ben's own audio?

The transfer test, and the one that can invalidate arms A–C.

Take the **50 human labels on ★kept captures** (13 captures, all audio present in
`fieldserver/instance/media/`), embed each label span with BirdNET, pool with the
same `mean+std+max`, and score the shipped `american-crow` head against them.
Compare against the constant-classifier baseline, exactly as 0018 did.

**Stated honestly up front: n is 52 trainable labels over 13 captures.** This arm
can detect a catastrophic domain gap (0018 found one) and cannot measure a subtle
one.

| pooling | scope | n | top-1 | constant baseline |
|---|---|---|---|---|
| **whole span** | all trainable | 52 | **0.769** | 0.519 |
| **whole span** | ★kept only | 42 | **0.857** | 0.595 |
| single 3 s window | all trainable | 52 | 0.673 | 0.519 |
| single 3 s window | ★kept only | 42 | 0.786 | 0.595 |

**It transfers.** Pooled over the labelled span the head beats the constant by 25
points on all field labels and by 26 on kept captures. That is a different answer
from 0018, and the two poolings explain why.

Look at what the single-window variant predicts: **41 of 52 answers are "alarm
call"**, and all 9 true `call` spans are called alarm. That is 0018's exact
signature — a head that answers alarm to everything. Pooling the same audio over
the whole span instead drops that to 25 of 52 and recovers 7 of 12 `call`.

So the collapse 0018 attributed to unit/domain shift is at least partly a
**pooling** artifact: a single 3 s window has std = 0 and max = mean, leaving a
third of the feature vector empty and a third redundant. Whatever the head learned
about temporal spread cannot fire.

> **Decision rule was: at or below constant → field labels are the only ones that
> count.** It cleared the baseline, so archive labels are legitimate — and arm A
> then says there are already enough of them.
>
> The actionable part is the pooling, not the transfer: **pool over the call
> region, never a single window.** `predict.py` already does region pooling; this
> is a reason to check that every caller does.

Caveats worth keeping attached: `song` and `flight call` have one field label
each, so they are untested rather than passing; 27 of 52 are `alarm call`, so the
constant baseline is high and the task is easy; and top-1 of a one-vs-rest head
is what the app displays but not a calibrated confidence.

### E. Three things crow-tools does that CrowGPT does not

Each is testable on cached features, and each is a real methodological
difference rather than a tuning knob. (The full comparison is in the section
below; these are the three worth *measuring* rather than just noting.)

**E1 — quality filtering: a small real win.** Against a *size-matched random
drop*, which is the control that separates purity from quantity:

| | n | macro-F1 |
|---|---|---|
| all rows | 2,110 | 0.852 |
| `quality ≥ 2` | 2,041 | **0.861** |
| random drop of the same 69 | 2,041 | 0.850 |

+0.011 over the control, driven by `call` (AP 0.911 → 0.944). Only 69 rows are
dropped in the single-label subset, so this is a small effect on a small mask —
worth taking because it is free, not worth a paragraph in a paper.

**E2 — the head cannot say "nothing here", and this is the finding.** Handed the
572 segments a crow-tools labeller explicitly marked `crowCount = 0`:

| | four-class head (shipped) | five-class, with `none` |
|---|---|---|
| garbage given a call type at p > 0.5 | **97.0%** | — |
| mean top probability on garbage | **0.898** | — |
| garbage correctly rejected | 0 by construction | **70.6%** |
| CORE macro-F1 | 0.852 | 0.831 |

It calls 388 of 572 empty segments *alarm call*, 119 *song*. The shipped head has
no abstain, so on silence it does not merely guess — it guesses **confidently**,
at a mean top probability of 0.90. Adding a `none` class buys back 70.6% of that
for 0.021 of CORE macro-F1.

This is the one place where more manual labelling has a large, measured payoff,
and the labels it wants are *negatives* — "there is no crow here" — which is the
cheapest possible thing for a human to say and the one thing the field vocabulary
has no chip for. `not_a_crow` exists but is `trains = 0`.

*Caveat:* the four-class number is fitted on all call rows and scored on garbage
it never saw, with recordings possibly overlapping — so 97.0% is an upper bound
on the failure. It is not a small enough number for that to matter.

**E3 — auxiliary heads do nothing.** Same trunk, same folds, same 60 epochs; the
only difference is whether crow-tools' crowCount/crowAge/quality losses are added:

| | macro-F1 | sd |
|---|---|---|
| single task | **0.856** | .004 |
| + auxiliary heads | 0.852 | .006 |

A clean null at −0.004. Worth recording twice over, because it also says the
**240 K-parameter MLP barely beats the logreg** (0.856 vs 0.852) — the Phase 4
note that a regularised linear model is the right size for this corpus still
holds at 2,110 rows, not just at 117.

## Cost, and the GPU constraint

**Zero VRAM used, as promised.** Every arm is CPU. The logistic regressions are
sklearn on 3,072-d features; the three embedding passes are BirdNET via
`birdnetlib`, which is TFLite on CPU; and E3's 240 K-parameter MLP is pinned to
CPU in `arm_e3` rather than merely being small enough for the GPU — the GPU was
Ben's for the duration and never touched.

Actual: **~50 min** of embedding (60 field labels, 572 garbage segments, 2,338
call segments re-keyed, 30 workers) and **~75 min** of fitting. Progress was
printed throughout; `results.json` is written incrementally after every
arm, so a crash costs one arm rather than the run.

## Re-running

```bash
../../pipelines/representation/.venv-birdnet/bin/python prepare.py   # caches, ~50 min
../../pipelines/representation/.venv-birdnet/bin/python run.py       # arms A-E2
../../crowgpt/.venv/bin/python run.py --only e3                      # E3 needs torch
```

`prepare.py` skips any cache that already exists. E3 lives in the second venv
because the BirdNET venv carries no torch and the crowgpt venv carries both torch
and sklearn; `run.py` loads `results.json` before writing, so the two runs merge
rather than overwrite.

---

# What crow-tools does that CrowGPT does not

Read from the fork at `~/Code/crow-tools`. Two headline corrections first,
because they cut in opposite directions.

## Head to head, on matched protocol — `compare_crowtools.py`

Their numbers and ours normally cannot be set side by side: they report accuracy
and balanced accuracy on a segment-level 88/12 split, we report AUC and AP on
recording-grouped folds, and neither converts into the other.

But **the labels are the same labels.** CrowGPT vendored their corpus, so the
task, the classes and the ground truth are identical, and only the backbone, the
head and the split differ. Running our features through *their* exact protocol —
segment-level 88/12, seed 18202, balanced accuracy as the mean of the two class
recalls — makes one number comparable. (Their metric definitions were reproduced
and checked against their own file: alert (93.37 + 77.63)/2 = 85.50, matching.)

Pool: 2,910 embedded segments over 1,387 recordings, garbage rows included as
negatives the way they include theirs.

| flag | prevalence | crow-tools reported | ours, their protocol | ours, grouped |
|---|---|---|---|---|
| alert | 0.176 | **0.855** | 0.765 | 0.753 |
| begging | 0.096 | **0.879** | 0.861 | 0.826 |
| softSong | 0.199 | 0.877 | **0.895** | 0.809 |
| rattle | 0.176 | 0.925 | **0.939** | 0.905 |
| mob | 0.237 | 0.782 | **0.805** | 0.756 |
| **mean** | | **0.864** | 0.853 | 0.810 |

*(balanced accuracy throughout)*

### Backbone and head: roughly a tie, with one real loss

On matched protocol we win `mob` (+0.023), `softSong` (+0.018) and `rattle`
(+0.014), and lose `begging` (−0.019) and — badly — **`alert` (−0.090)**. Mean
0.853 against their 0.864.

That is close enough to call a tie on four of five classes, and the comparison is
**generous to them** on two counts: their 468 validation samples are also what
selected their checkpoint and what Optuna optimised across 60 trials with the
random seed as a searched hyperparameter, while ours is a plain fit with no
selection against the evaluation set at all.

`alert` is the one place they have something we do not, and this experiment does
not resolve which of three candidates it is: AVES may simply be better at alert;
their oversampling duplicates alert ×3 while ours uses `class_weight="balanced"`;
or the multi-task trunk helps a class that E3 showed does not help CORE. Worth a
follow-up, because −0.090 is not noise.

### The split is worth +0.043, and it behaves exactly as a leak should

Same features, same head, same rows — only the split changes:

| flag | segments/recording | their split is worth |
|---|---|---|
| softSong | 3.35 | **+0.085** |
| mob | 1.29 | +0.049 |
| rattle | 3.09 | +0.035 |
| begging | 2.38 | +0.035 |
| alert | 1.65 | **+0.013** |

**+0.043 on average.** And the size of the effect tracks how *concentrated* a
class is inside recordings, which is precisely what a segment-level split
predicts: softSong, at 3.35 positives per recording, gains six times what alert
gains at 1.65. Four of five classes fall in that order; `mob` is the exception.

That internal consistency is the reason to believe the number. It turns "their
reported figures are optimistic" from an assertion into **+0.043 balanced
accuracy, up to +0.085 on their most concentrated class** — and it means their
0.864 mean would land near 0.82 under our harness, below our 0.853-on-their-
protocol but above our 0.810 grouped. Nobody is clearly ahead; the protocols were
doing most of the talking.

## Their reported numbers are optimistic, and CrowGPT's harness is stricter

crow-tools splits **at the segment level**: `TRAIN_SPLIT_FRACTION = 0.88`,
`random_split(..., manual_seed(18202))` in `classifier/dataset.py`. Recordings
contribute up to 12+ segments and land on **both sides** — same bird, same mic,
same background, often the same call bout. `rattle`'s 543 positives come from
just **176 recordings** (~3.1 each), so rattle is the class most inflated by this.

There is also **no test set**: the same 12% validation split is used for
checkpoint selection *and* Optuna's objective — 60 trials in which **the random
seed itself is a searched hyperparameter** (`optuna_tuning.py`).

So `RESULTS.txt`'s rattle 95.5% / mob 88.7% are not comparable to CrowGPT's
recording-grouped numbers, and CrowGPT should not chase them. CrowGPT's
grouped CV, AP-alongside-AUC reporting and `label_revisions` provenance are all
ahead of the fork here. The honest read of their own results is the *recall*
column: **rattle 88.2%, mob 61.4%** — and mob being their worst class, on their
own optimistic split, is a strong independent corroboration of 0012's finding
that mob is the hard one.

## Nine things they do differently

| | crow-tools | CrowGPT | worth taking? |
|---|---|---|---|
| Embedding | **AVES `aves-base-bio`**, 768-d, final layer | BirdNET 1024-d (Perch tested, 0025) | untested here — but see the bug below |
| Denoising | biodenoising DNS48 **before** embedding | none | 0031 measured this; see below |
| Window | fixed 1 s, hop 1 s, no overlap | 3 s BirdNET windows | their resolution is finer |
| Pooling | mean over 25 frames → 1×768 | **mean+std+max → 3,072** | CrowGPT's is better; 0.44→0.48 macro-F1 when it shipped |
| Head | 240 K-param MLP, 8 heads, shared trunk | one logreg per task | **E3** |
| Negatives | 596 explicit garbage segments | dropped at import | **E2** |
| Quality | `quality ∈ {1,2,3}` per segment | ignored | **E1** |
| Balancing | oversample by duplication (`rattle`×4, `alert`×3, **`mob`×1**) | `class_weight="balanced"` | equivalent-ish |
| Rare-class mining | **seeded FAISS 10-NN retrieval** | none | **C** |
| Augmentation | **none** | none | neither does it |
| Calibration | none — `logit > 0`, `confidence` hardcoded `0` | AUC-based tiers (also wrong, per 0012) | both need work |

### The three genuinely worth stealing

**1. Seeded similarity mining is how they got 543 rattles.** Their own detector
auto-fires `rattle` on only **1.5%** of 139,018 machine detections, yet their
human set is 17% rattle. The mechanism (`classifier/cluster.py`): hand-pick 7
rattle exemplars → PCA to 75 → L2-normalise → FAISS `IndexFlatIP` → take the 10
nearest neighbours of each seed, max 4 per file, and queue those for review. That
is how you build mass in a class the model rarely fires on — which is exactly
Ben's mobbing problem. Arm C tests the cheap version of this idea.

**2. Labelling throughput is a UI problem they solved and CrowGPT has not.**
One action labels one 1-second segment. Cards are sorted **by cluster** so
acoustically similar items sit adjacent, 30 to a page, with a **"copy previous"**
button that clones all 9 fields from the last card and starts playback — so a run
of similar segments costs one click each. Plus global 1×–4× playback speed. If
Ben builds a labelling pipeline, this is the design to copy, and it is more
important than any modelling choice in this document.

**3. An explicit garbage class.** Pressing `Z` in `review_detections.py` files a
false detection as `crowCount=0, quality=1`. 19% of their labelled set is
"nothing here". CrowGPT's head cannot express that, and in the field it is the
most common truth.

### Is BirdNET's 3 s window the problem? No — 0025 already asked

A reasonable worry, since every crow-tools span is **exactly 1 second** (3,162 of
3,162) while `build_dataset.py` pools a 3 s BirdNET window at `3*(second//3)`.
The label describes a third of what the feature describes.

Measured here, from the labels alone: **20.0%** of reviewed segments have another
labelled second inside their 3 s window, but only **2.5%** have a neighbour
carrying a CORE label the segment itself does not. So direct label contamination
is small. (What it does not measure is the unlabelled audio — crow-tools labelled
about two seconds per recording, so most of every window is audio nobody
described.)

0025 settled it experimentally, and its answer was the opposite of the intuition:

- **centring BirdNET's window on the label makes things worse** — +0.006 macro-F1
  but −0.10 on `mob vs alert` (0.637 → 0.540, spreads separate). The grid window
  keeps the *preceding* audio, which evidently carries something.
- **Perch at 1 s beats BirdNET at 3 s** — 0.856 vs 0.849 macro-F1 and 0.759 vs
  0.637 on `mob vs alert`, with a third of the audio. A rival that wins while
  starved is the strong form of the result.
- **Perch at 5 s is the worst arm in the table**, so ~3 s is close to right for
  both models.

0025's own summary: *"it is the backbone, and Perch 2.0 is better at it. The
window is a null."* Combined with arm B here, that is the whole mobbing story:
not labels, not the window, the backbone.

### Overlapping crows are why mobbing is hard — `overlap_wall.py`

Arm B said mob is not label-limited. 0025 said a better backbone does not fix it
either (all of Perch's gain is on single-crow segments; at `crowCount>=2` Perch
is slightly *worse*, 0.775 → 0.747). This asks what the wall does per class, with
one model fitted under recording-grouped CV and the **same out-of-fold
predictions scored inside each stratum** — splitting the evaluation, not the
training.

Raw AP is misleading here because prevalence moves between strata, so both are
shown with lift over chance:

| flag | one crow: AP / prev / lift | two or more: AP / prev / lift | lift change |
|---|---|---|---|
| **mob** | 0.551 / 0.19 / **2.93×** | 0.867 / 0.65 / **1.33×** | **−1.60** |
| **alert** | 0.709 / 0.23 / **3.13×** | 0.365 / 0.19 / **1.88×** | **−1.24** |
| begging | 0.800 / 0.12 / 6.52× | 0.733 / 0.11 / 6.77× | −0.25 |
| softSong | 0.830 / 0.28 / 2.95× | 0.692 / 0.14 / 5.02× | +2.06 |
| rattle | 0.923 / 0.25 / 3.74× | 0.833 / 0.12 / 6.67× | +2.93 |

**The wall is not general — it is specific to the alarm family.** `rattle` and
`softSong` are *better* against chance when several crows are calling; `begging`
is flat. Only `mob` and `alert` collapse.

And mob's collapse is hidden by the raw number. Its AP *rises* from 0.551 to
0.867 with more crows — but its prevalence rises from 0.19 to 0.65, so at
`crowCount>=2` an AP of 0.867 is 1.33× chance. On multi-crow audio the head is
barely doing better than answering "this is a crowd."

That is the causal story arm B was missing:

> **Mobbing is defined by several crows calling over each other, and overlapping
> callers are exactly the condition under which the features stop separating
> anything. The class is hard because the class *is* the failure mode.**

It also re-reads 0025's aggregate. CORE macro-F1 falls 0.852 → 0.774 at
`crowCount>=2`, but accuracy *rises* 0.871 → 0.939, because multi-crow segments
are 367 `alarm call` against 20 `song` and **1 `call`**. Much of the macro-F1
drop is a class-mix artifact of a stratum that is 86% one class. The honest
statement is the per-class lift table above, not the aggregate.

**What would fix it is a detector, not a backbone and not labels** — which is
`FUTURE.txt`'s standing Voxaboxen entry, per-event onset and duration for
overlapping vocalisations. crow-tools built exactly this and never used it (below).

### Recording-grouped CV is already strict enough — `recordist_split.py`

The big archive's `library.csv` carries a **Recordist** on 100% of rows and nothing in
this project had ever read it. A recordist brings one microphone, one garden and
often the same birds across many recordings, so recordist-disjoint folds are the
obvious next tightening — 567 distinct recordists over the 1,097 labelled
recordings, 1.93 recordings each.

It changes nothing:

| | by recording | by recordist |
|---|---|---|
| CORE macro-F1 | 0.852 | **0.855** |
| mob AP | 0.706 | 0.694 |
| alert AP | 0.638 | 0.629 |
| rattle AP | 0.912 | 0.905 |
| softSong AP | 0.813 | 0.814 |
| begging AP | 0.784 | 0.757 |

Every delta is inside seed noise and CORE macro-F1 moves the *wrong* way. **The
recordist is not an additional leak, so every grouped number this project has
ever reported stands.** Worth having asked — it was the most plausible remaining
threat to the harness, and now it is a measured null rather than an open worry.

### BirdAVES — assessed and rejected, so their backbone is not the thing to take

crow-tools embeds with **AVES `aves-base-bio`**, and `FUTURE.txt` already
evaluated that family on the literature rather than on a hunch: the 2026
comparative review (arXiv 2508.01277) puts AVES at **63.8** and BirdAVES at
**65.6** BEANS linear-probe AUROC, against **85.6** for Perch 2.0 and BEATs.
Self-supervised bird models have not caught the supervised ones on linear
probing, which is exactly how this project uses an embedding.

And crow-tools runs AVES **at 8 kHz when it is a 16 kHz model** (§below), pitching
every call an octave down and capping bandwidth at 4 kHz. So their backbone is
worse than the incumbent on paper and handicapped in practice. **There is nothing
to extract from their embedding choice** — the migration target is Perch 2.0, on
0025's evidence, not AVES.

### Two things of theirs that are bugs, not features

**They feed a 16 kHz model audio at 8 kHz.** AVES/BirdAVES is a 16 kHz model —
their own `embedder/ispa/utils.py` defaults `tgt_sr=16_000` — but the pipeline
loads everything at `sr=8000` (`embed_all.py:26`). The model sees crow calls
pitched an octave down and time-stretched 2×, outside its pretraining
distribution, with a hard **4 kHz Nyquist cap** that discards rattle and clack
energy above it. Never discussed anywhere in the repo. **Do not copy this**, and
treat any AVES-vs-BirdNET comparison drawn from their numbers as uninformative.

**Train/inference denoising mismatch.** The classifier trains on
`embeddings-denoised/` (`dataset.py:19`, `denoised=True`) but the detector reads
raw `embeddings/` at inference (`detect.py:133`) while gating on *denoised*
volumes — and the uncached path denoises not at all. Undocumented and looks
unintentional.

On denoising generally: CrowGPT already measured this in **0031** rather than
assuming it, which is the right posture. Their unconditional denoise-everything
is not evidence for adopting it.

## Capture 104's two caws — `capture_104.py`

`TODO.txt` records that Ben's ear put a caw over the begging at **~12s** and
again at **~27s**, and that the analyzer stored 9-27s as one 18-second `begging`
region at 0.998 so both were invisible. That entry named three causes and a fix
order. **Two of the three have since shipped**, and the current analysis
(`analysis_id` 243) shows it:

| span | call type | conf | alternates |
|---|---|---|---|
| 6-9s | begging | 1.000 | — |
| **9-27s** | begging | 1.000 | **`call` 0.998** |
| 27-30s | begging | 1.000 | — |
| 39-42s | begging | 0.997 | `song` 0.939 |
| 42-51s | call | 0.973 | — |

The head is now `MultiLabelHead` (one-vs-rest, `multi_label = 1`) and
`detected_calls` carries an `alternates` column. **The caw is no longer
invisible** — the 9-27s region says `begging` and `call` at once, which is
exactly what the old argmax could not express.

Scoring the reported moments directly, at a ladder of widths:

| centred on | 3s | 9s | 18s |
|---|---|---|---|
| **12s** | begging 0.924, call 0.094 | begging 0.996, **call 0.745** | begging 1.000, **call 0.990** |
| **27s** | begging 1.000, **call 0.994** | **call 1.000**, begging 1.000 | call 1.000, begging 1.000 |
| 45s *(control)* | call 0.390, flight 0.390 | call 0.998 | call 1.000 |

Two things follow.

**The ~27s caw is not a sensitivity failure.** `call` is at 0.994 even in the
narrowest window. The head hears it. What the shipped output cannot do is say
*where* — the 9-27s region reports `call` 0.998 across eighteen seconds, and the
caw's energy sits in the 24-27s window, on the far side of the region from the
~12s one. The 27-30s region has no alternate because the caw is at ~26s, inside
the *previous* region. ai_description row 14 guessed this at the time: "27s is
also where the analyzer split 9-27s from 27-30s, so the boundary and the
overlapping caw fall at the same moment."

**Narrow regions systematically under-report.** Every row of the ladder rises
with width, including the control (`call` 0.390 → 1.000). A 3 s region is one
BirdNET window, where std = 0 and max = mean, and arm D measured the same
degeneracy on field spans. So a short region is not just less informed, it is
differently shaped.

> **What is left is fix #3 and only fix #3.** `group_regions` fuses windows
> within `REGION_GAP` (1.5 s) into one span before the head runs, so an 18-second
> beg with a caw in it is one row. The head and the schema can now both express
> a co-occurrence; the region is what cannot localise it. That is a
> segmentation problem — the same one the overlap arm above found behind mobbing,
> and the same one Voxaboxen targets.

*Scope: one capture, diagnosed. It shows the head hears both caws and the region
structure hides one; it does not measure how often that happens.*

## What is still extractable from the fork, and what is not

A full inventory of `~/Code/crow-tools/.cache`, beyond the labels already
vendored. Ranked by what it would actually buy.

**Worth taking:**

| asset | size | what it is |
|---|---|---|
| **14 GB of audio** — 10,550 MP3s, ~123 h | 14 GB | real files, not LFS. Includes **all 111 recordings CrowGPT is missing**, which strand **170 labelled segments**. Copying beats re-downloading from a rate-limited archive. |
| `library.csv` **Behaviors** | 3,690 rows, 54 values | human behavioural annotation — `Call` 2,999, `Call; Flying` 122, `Song` 85. Free weak labels nobody has read. |
| `library.csv` **Playback** | 15 rows `Used` | **recordings made with playback stimulus.** These are contaminated and should be dropped from any training set. Cheapest quality win in the inventory. |
| `library.csv` lat/long/date | 99.5% / 100% | 1,532 of 1,549 labelled recordings geolocated, dates 1957–2025 — the only route to a dialect or seasonal question. |
| `library.csv` **Background Species** | 1,449 rows, 840 values | which other birds are audible. Directly useful for the `none`/confusion work in E2. |
| `backgrounds/*.csv` | 58,419 rows, 7 species | download manifests for chickadee, blue jay, cardinal, robin, mockingbird, woodpecker, starling. **No audio downloaded**, but these are the *hard* negatives E2 wants — confusable species that co-occur with crows, rather than silence. |
| XC `segments.json` | 11,912 segments | detector-proposed 1 s candidates with **no label**, audio on disk. An expansion pool if a labelling pipeline gets built. |

**Not worth taking, measured rather than assumed:**

- **Every model checkpoint is a Git-LFS pointer** and `git lfs` is not installed
  here. The classifier (2.9 MB), the **separator (44 MB)** and the AVES weights
  (378 MB) are all 130-byte stubs. Nothing is loadable.
- **The transcriber is a stub.** One recording transcribed, **20 tokens total**,
  and the tokens actually saved (`kaugh`, `kaaw`) are not even in their own
  23-token vocabulary — free text was typed. The vocabulary itself is a nice
  piece of human design worth keeping as a reference; there is no corpus.
- **No human rejections were ever persisted.** `excluded_segments.json` is
  created as `[]` and read in three places but exists nowhere on disk, and
  `remove_dupes.py` overwrites in place leaving no record. That negative-decision
  data does not exist.
- **`auto.json`** — 139,018 machine labels, but `quality` is `2` on every single
  row, `crowCount` is never 0 or 3, and mob fires on 51%. It is the model's own
  bias at scale; useful only as a distillation target, never as truth.
- **No separator mixtures on disk** — generated per run, and `mix.py` needs the
  background audio that was never downloaded, so re-running it today yields
  crow-on-silence rather than realistic mixtures.

### The separator is the one substantial thing they built and never used

Given the overlap finding above, this is the most interesting entry in the
inventory. `separator/train.py` trains an **asteroid `DPRNNTasNet`, `n_src=2`**,
PIT loss on SI-SDR, 40,000 synthetic two-source mixtures — and **nothing
downstream consumes its output.** `get-data.py` never calls it; the classifier
never sees a separated stem. That is why `crowCount` is a classifier head rather
than a product of separation.

So they built the tool for the exact failure this experiment just measured, and
left it unwired. But it is not extractable as a working model: the checkpoint is
a 44 MB LFS stub, the training mixtures need background audio that was never
fetched, and it runs at **8 kHz** — the same bandwidth cap that handicaps their
AVES path, discarding the above-4 kHz energy that distinguishes a rattle.

**The recipe transfers; the model does not.** And on 0025's evidence the better
bet is Voxaboxen — per-event onset and duration for overlapping vocalisations,
which is `FUTURE.txt`'s standing entry and now has a measured motivation rather
than an argued one.

### The structural limit on their whole corpus

Their detector **is** their classifier — a window becomes a detection only if the
classifier's own `quality > 1` and `crowCount > 0` heads fire
(`detect.py:265`). Labels come from reviewing detector output; similarity mining
retrieves the model's *confident* neighbours. Nothing in that loop can discover a
call type the current model is blind to, and there is no random-sample audit of
undetected audio, so **their recall is unknown**.

That matters for CrowGPT directly: the vendored 3,162 labels are **not a random
sample of crow vocalisation**. They are a sample of what one model found and one
person chose to review. A learning curve fitted to them (arm A) describes
"more labels like these", which is a narrower claim than "more labels".

Their whole labelled corpus is **~53 minutes of audio** — 3,162 one-second
windows, 543 rattles from 176 recordings, 738 mobs from 570 recordings.

---

# The thing this experiment cannot fix, and Ben should hear first

Arms A–C are all about archive audio. The field server has **60 human labels**,
50 of them on ★kept captures, across 13 captures. And after 60 labels:

- **zero** use `mobbing`, `scold`, `rattle` or `contact call` — all four have
  been on the menu in `label_defs` since version 1
- `label_revisions` has **0 rows**; the re-answer mechanism has never fired
- 0013 measured the first 35 labels as **67.7 seconds** of actual call audio,
  with only **5** isolating a single call

So the corpus cannot currently score a mobbing detector *at all*. 0012 said
"label mobbing in the field first, then split the class" — and arm B now changes
that instruction rather than merely deferring it. Field mobbing labels are still
worth collecting, but **as a test set, not a training set**: arm B says the
training signal is not the thing that is missing, so labels that can only add
volume will not help. Labels that can *falsify* the 0.71 will.

And the finding that outranks everything above, from 0012: **the corpus's `call`
class is a rattle detector.** Exactly one crow-tools flag (`rattle`) maps to it,
so the class the field will exercise hardest — contact calls, the most common
thing a crow says — is trained on something else entirely, and there are zero
contact-call examples anywhere in the project. Arm B makes this sharper rather
than softer: `rattle` reached its ceiling at 9% of the labels that exist, so the
class is not just mistrained, it is *comprehensively* mistrained on a problem
that was solved early. No amount of archive labelling fixes it. Ben's own
microphone does.

## What this changed

**The headline instruction reversed.** The question was "should I label more, and
is it worth building a pipeline". The answer is that more call-type labels of the
kind that exist are worth +0.011 macro-F1 at double the corpus, so **no bulk
labelling pass** — and that the pipeline is still worth building, pointed
somewhere else.

Five concrete things:

1. **Do not run an archive labelling push for the CORE classes.** Arm A, and arm
   C agreeing from a held-out direction. Ben has roughly twice the labels those
   four classes can use.

2. **Mobbing is off the labelling roadmap and onto the representation roadmap.**
   AP flat at ~0.71 over a tenfold range with stable prevalence, fitted ceiling
   0.719, AP 0.80 unreachable. The next thing to try is 0025's Perch arm
   (mob-vs-alert 0.637 → 0.760), not more mob labels. This supersedes the
   labelling half of `FUTURE.txt`'s "split alarm into mobbing vs alerting" —
   that entry should be updated to say the split is blocked on the backbone, and
   that field mobbing labels are now wanted as a *test* set.

3. **The head needs a `none` class, and that is where manual labelling pays.**
   97.0% of explicitly-empty segments get a call type at p > 0.5, mean top
   probability 0.898, 388 of 572 called *alarm call*. A five-class head rejects
   70.6% of them for 0.021 of CORE macro-F1. The field vocabulary has
   `not_a_crow` already but it is `trains = 0`, so the one cheap thing a human
   can say is the one thing the model never learns. **This is the single most
   valuable labelling change available**, and it is also the fastest to collect.

4. **Pool over the call region, never a single window.** Arm D reproduced 0018's
   "alarm call to everything" collapse purely by changing the pooling — 41 of 52
   field spans called alarm with a single 3 s window, 25 of 52 with the whole
   span. Some of what 0018 attributed to unit shift is a degenerate feature
   vector (std = 0, max = mean). Worth auditing every caller of `pool`.

5. **`build_dataset.py` should write the segment key.** The cache had already
   drifted out of positional alignment — 2,494 rows against 2,339 segments, 98
   files disagreeing, one file permuted. 0012's `align()` caught it, which is the
   good news; the bad news is that every future experiment pays to re-embed or
   risks a silent mis-join. A key on the row ends the whole class of bug.

Two things that changed nothing, recorded because a measured null is worth as
much as a positive one:

- **crow-tools' auxiliary heads do not help** (−0.004, arm E3), and the 240 K MLP
  barely beats the logreg (0.856 vs 0.852). The Phase 4 "a linear model is the
  right size here" note survives at 2,110 rows.
- **No acquisition strategy beats random** (arm C). Cluster-sorting the queue is
  a throughput trick worth copying for the UI; it is not a sample-efficiency
  trick. Uncertainty sampling not winning means the labelling pipeline **does not
  need a model in the loop** — the expensive half of that build is unnecessary.

And one small free win taken: **filter to `quality ≥ 2`** (+0.011 over a
size-matched random drop, arm E1).

## What this cannot say

- Arms A–C measure "more labels **like crow-tools'**". Their labels are not a
  random sample of crow vocalisation — their detector *is* their classifier, and
  their rare-class mining retrieves the model's own confident neighbours, so the
  pool is shaped by what the model already found. A flat curve on that pool is
  not proof that no labelling scheme could do better; it is proof that *more of
  the same* will not.
- Arm D is 52 labels over 13 captures, with `song` and `flight call` at one label
  each. It cleared the constant baseline, which is all it was built to detect.
- Nothing here measures contact calls, because nothing anywhere has one.
