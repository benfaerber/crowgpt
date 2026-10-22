# Phase 4 — Training

> **Status: DONE (acoustic call types)** — built more simply than first planned.

The original plan was to *fine-tune* the encoder on a GPU. In practice that was
unnecessary: BirdNET embeddings are left **frozen**, and a small
**logistic-regression head** classifies the pooled fingerprint. At a few hundred
examples per class a regularized linear model beats a deep net — confirmed here
(logreg CV macro-F1 **0.48** vs. a GPU MLP's **0.35**).

## What was built

- **Feature:** mean+std+max pooling of a clip/region's 3-second BirdNET segments →
  3072-dim ([`pipelines/training/pooling.py`](../pipelines/training/pooling.py)),
  shared by training *and* the demo so the feature never drifts.
- **Multi-label:** a clip tagged "alarm call, call" is a positive for **both**,
  not discarded — recovers over half the alarm data.
- **Per-species heads:** one logreg per species on the shared embedding
  ([`pipelines/ingest/train_species.py`](../pipelines/ingest/)), so the demo routes
  each detected species to its own model. Five trained: American Crow + Carrion
  Crow, Common Raven, Rook, Hooded Crow.
- **Honest evaluation:** recording-grouped cross-validation and per-class AUC — no
  recording spans the train/test split.

## The result

On the archives' weak `type` labels, flight call is strong (~0.9) but alarm/song
stay weak. On the human-reviewed crow-tools corpus (2,221 segments, grouped CV)
the same pipeline lifts them: **alarm 0.68→0.97, song 0.59→0.91** — the classes
were **label-limited, not unlearnable**. The shipped American Crow head trains on
those clean labels (plus the archive set for flight call).

## Still ahead (the semantics half)

The above solves problem 1 — *acoustic* call types. The tiered **semantic** plan
(supervised tier 1 "dog" first; behavior-anchored tier 2 threat-vs-unknown human;
self-supervised tier 3) waits on the labeled gold set and stays the goal.
**Class imbalance** (contact calls vastly outnumber threat) is real — handled
today with balanced class weights, and by targeted collection later.
