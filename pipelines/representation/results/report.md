# Phase 3 — first result (honest)

**Date:** 2026-07-18 · **Corpus:** American Crow, archive corpus, 117 clean
single-label clips · **Features:** classical MFCC-summary (86-dim), loud-frame
pooled, ffmpeg+numpy/scipy.

## Question

Do crow call types (`call`, `flight call`, `alarm call`, `song`) form separable
acoustic clusters in an off-the-shelf feature space?

## Headline: not in this feature space

| Metric | Value | Baseline / chance |
|--------|-------|-------------------|
| kNN accuracy | 0.598 | 0.607 (majority) |
| logreg accuracy | 0.530 | 0.607 |
| kNN macro-F1 | 0.326 | — |
| logreg macro-F1 | 0.364 | — |
| silhouette (true labels) | **-0.06** | 0 = no structure |
| KMeans ARI vs labels | **0.008** | 0 = chance |

Overall accuracy sits **at or below** the majority baseline, silhouette is ~0,
and unsupervised clustering recovers nothing. The PCA/t-SNE plot
(`clusters.png`) shows all four types thoroughly intermixed — no visible
clusters. **Classical whole-clip features do not separate crow call types.**

## The nuance: it's not uniform failure

Per-class recall (kNN) tells a sharper story:

| Call type | n | recall |
|-----------|---|--------|
| call | 71 | 73% |
| **flight call** | 25 | **72%** |
| alarm call | 10 | 0% |
| song | 11 | 0% |

`flight call` — acoustically the most distinct (given in flight) — is recovered
~72% even by crude features. `alarm call` and `song` are **entirely** absorbed
into the `call` bucket. So the features carry the *broad* distinction
(flight vs. perched) but none of the *subtle* ones, and the macro-F1 is dragged
down by the two 0%-recall classes.

## What this means (and doesn't)

**Does NOT mean** crow calls are inseparable or the project is doomed. It means
the *floor* — classical MFCC summaries over whole clips — is near baseline, which
is exactly why the plan reserves a learned embedder as the real representation.
We've now measured the floor rather than assumed it.

**Confounds that plausibly suppress the signal:**
- **Weak labels.** The archive's `type` is coarse free-text; `call` is a 71-clip
  catch-all. The labels themselves are noisy ground truth.
- **No call segmentation.** Features pool a whole 10–60s recording (loud frames,
  but still whole-clip). A clip tagged `alarm call` mixes target caws with other
  sound, wind, distance, other birds. Isolating individual caw events (onset/VAD)
  is the obvious missing step.
- **Imbalance + small n.** `call` dominates; `alarm`/`song` have ~10 each.

## Verdict & next steps

Phase 3 is **verified as run, with a negative first result and a clear signal in
one class.** Before Phase 4 or any claim about the categories:

1. **Segment calls** — detect individual vocalization events and classify those,
   not whole clips. Cheap, no new deps; likely the biggest single win.
2. **Swap in a pretrained audio embedder** (BirdNET / PANNs / an audio encoder)
   — the documented upgrade; re-run this exact harness on those embeddings.
3. **Cleaner labels** — collapse the archive's free-text types, or lean on the
   own-recording gold set where context is witnessed.

Do **not** build training (Phase 4) on classical whole-clip features — this run
shows they won't carry the finer categories.

## Follow-up: per-type detectability (one-vs-rest)

The multiclass metric is dominated by the 71-sample `call` majority — everything
collapses into it. Testing each type **one-vs-rest** (balanced) shows the raw
"0% recall" was an imbalance artifact, not an absence of signal:

| Call type | one-vs-rest AUC (0.5 = chance) |
|-----------|-------------------------------|
| flight call | **0.77** |
| alarm call | **0.77** |
| call | 0.62 |
| song | 0.49 (chance) |

And **call vs flight call** directly (n=96): accuracy 0.76 (baseline 0.74),
**macro-F1 0.71** — a real, balanced separation (majority-guess macro-F1 ≈ 0.43).

**Revised read:** there *is* real acoustic signal here, even with crude features
— `flight call` and `alarm call` are individually detectable at AUC ~0.77.
`song` is at chance (indistinguishable in this space, and the noisiest/smallest
label), and generic `call` is a weak heterogeneous bucket. The flat multiclass
result is driven by imbalance + the hopeless `song` class + coarse labels + no
call segmentation — **not** by the categories being acoustically identical.

That flips the outlook from "classical features fail" to "promising per-type
signal that a better method should sharpen."

## Follow-up 2: segmentation did NOT help (`segment_experiment.py`)

Tested the leading hypothesis — that whole-clip pooling was the problem — by
detecting **1,562 individual call events** (energy envelope, avg 13/clip) and
classifying those with **clip-grouped CV** (events from one recording never span
the train/test split — an honest metric).

| | flight call | alarm call | call | song |
|--|--|--|--|--|
| whole-clip AUC | 0.77 | 0.77 | 0.62 | 0.49 |
| **per-event AUC** | 0.71 | 0.69 | 0.52 | 0.38 |

Per-event multiclass acc 0.42 (baseline 0.62), macro-F1 0.33 — **no better, if
anything slightly worse.** Naive energy segmentation grabs loud regions
(including wind/noise/overlap), so it doesn't cleanly isolate caws.

**Conclusion:** the ceiling of *classical features* on this data is ~0.7 AUC for
the acoustically-distinct types, and neither segmentation nor the whole-clip view
beats it. The bottleneck is **representation quality**, not pooling.

## Follow-up 3: learned embeddings (AST) — roughly a wash

Ran AST (AudioSet-pretrained Audio Spectrogram Transformer, 768-dim, on the GPU),
same harness. It did **not** decisively beat classical features:

| one-vs-rest AUC | classical | AST |
|-----------------|-----------|-----|
| flight call | 0.77 | 0.74 |
| alarm call | 0.77 | 0.67 |
| call | 0.62 | 0.55 |
| song | 0.49 (chance) | **0.61** |

- logreg macro-F1 improved 0.36 → **0.48** (more balanced predictions), and AST
  **rescued `song`** from chance — the one class classical couldn't touch.
- But alarm/flight/call each slipped slightly, no class exceeds ~0.74 AUC, and
  unsupervised structure is still absent (silhouette −0.04, KMeans ARI ~0).

Likely why: AST is trained on *general* AudioSet audio — it captures
"crow-ish sound" but not fine intra-species call-type distinctions. **A general
learned embedder is not the silver bullet here.**

## Follow-up 4: BirdNET (bird-specific) — the diagnostic resolves

Ran BirdNET embeddings (1024-dim, trained on bird calls; isolated venv). This is
the decisive test, and the answer is **split by category**:

| one-vs-rest AUC | classical | AST | **BirdNET** |
|-----------------|-----------|-----|-------------|
| flight call | 0.77 | 0.74 | **0.89** |
| call | 0.62 | 0.55 | **0.71** |
| alarm call | 0.77 | 0.67 | 0.67 |
| song | 0.49 | 0.61 | 0.47 |
| logreg accuracy | 0.53 | 0.59 | **0.65** |

- **`flight call` breaks through to 0.89** and overall accuracy clears the
  majority baseline (0.65 > 0.607) for the first time. For the well-sampled,
  acoustically-distinct calls, **representation WAS the bottleneck** — a
  bird-specific model unlocks them.
- **`alarm call` (0.67) and `song` (0.47) don't budge** — bird-specific
  embeddings don't help. These are the two classes with the fewest samples
  (10, 11) and the noisiest archive labels. For them, **labels/data are the
  ceiling**, not the representation.
- Clusters still absent (silhouette ~0) — separability is supervised, not a
  clean unsupervised structure, consistent with noisy labels.

## Final verdict

Phase 3 verified across five experiments. The diagnostic **resolved cleanly, and
the answer is category-dependent:**

- **Representation-limited → now unlocked:** `flight call` (0.89 AUC) and generic
  `call` (0.71) separate well with BirdNET. **AI can distinguish these crow call
  types.** A flight-call detector is demoable *today*.
- **Label-limited → needs the gold set:** `alarm call` and `song` plateau
  regardless of representation. Better models won't fix them; witnessed-context
  labels (the Poe Family) will.

**Priorities:**
1. **Build Phase 4 on BirdNET embeddings** for the separable classes — a simple
   classifier on your GPU already beats baseline; flight-call detection is a real
   result and a good first demo.
2. **The gold set is the lever for the hard classes** (alarm, threat, song) —
   exactly the project's original thesis. Representation can't substitute for
   clean, contextual labels there.
3. Retire classical features, general embedders, and naive segmentation for this
   task — measured, superseded by BirdNET.
