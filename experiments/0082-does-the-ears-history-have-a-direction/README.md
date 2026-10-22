# 0082 — does the ear's history have a direction?

**2026-08-19, predictions before results — and before doses 2–3 of
voice-0078** · build: ~40 m CPU · **answer: pending**

## The question

Five completed sittings left 304 graded answers behind, each one a pair of
clips and a −2..+2 margin from the same ear that now hears a voice gap no
machine can see. If those grades trace a consistent direction in embedding
space, a judge distilled from them can predict the ear — and the proof is
prediction, not fit: train on the five completed pools, then call
voice-0078's outcome **before Ben finishes grading it**.

## Rules (sealed)

- voice-0078's answers — including the 16 already given — are not read, not
  for training, not for peeking. The store withholds results until the
  pre-committed count for exactly the optional-stopping reason; a judge
  trained on a partial sitting would smuggle the same bias in sideways.
- Validation is **pool-held-out**: five folds, each pool predicted by a model
  trained only on the other four, so the judge must generalize across
  questions (churn, scrape, window, dust), not memorize clips.
- Catch trials are the calibration floor: a judge that cannot rank real above
  generated on the known-truth catches is disqualified whatever else it fits.

## Predictions

- The catches are learnable (real-vs-generated has already been machine-
  visible in this project).
- The compare-trial margins are the hard part: 0038 measured 8.3 points of
  drift overnight on identical weights, and memory says close arms return
  nothing — so held-out correlation will be positive but modest (Spearman
  0.2–0.4), carried mostly by the trials Ben graded ±2.
- Sealed call on voice-0078, whatever the model says: recorded here by the
  analysis before doses 2–3 land, then scored against his completed sitting.

## Build

`run.py` (CPU): pull trials+answers for the five completed pools from
field.db (read-only), AST-embed every referenced clip from
`crowgpt/results/listening-pools/<pool>/`, fit ridge/logistic preference
models on Δ-embedding features (plus dustprobe features), report
pool-held-out Spearman and catch accuracy, then emit the sealed voice-0078
prediction from a model trained on all five pools.

## Result — pending

## What it changed — pending
