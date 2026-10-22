# Phase 3 — Representation experiment

A batch pipeline (not an app) that tests the core question of
[phase 3](../../phases/03-representation.md): **do crow call types form separable
acoustic clusters?** If a plain feature space already carries call-type
structure, the representation approach is viable and the Phase 0
acoustic-separability bet looks good.

## What it does

1. Reads the shared corpus at `cawtalker/data/corvid.db` for downloaded clips
   with clean single-label call types (`call`, `flight call`, `alarm call`,
   `song`; drops multi-label / `uncertain`).
2. Decodes each MP3 with **ffmpeg** and extracts classical features with
   **numpy/scipy** — log-mel MFCCs (20) + deltas + spectral centroid/bandwidth/ZCR,
   **pooled over the loudest frames only** (matching the loud/public-call scope).
   No librosa/numba (which conflicts with NumPy 2.x in this environment).
3. Measures separability of the *true* call-type labels:
   - supervised: 5-fold kNN and logistic-regression accuracy + macro-F1 vs a
     majority baseline (+ confusion matrices);
   - unsupervised: silhouette score, and KMeans cluster agreement (ARI).
4. Writes `results/clusters.png` (PCA + t-SNE, colored by call type) and
   `results/metrics.json`.

## Run

```sh
python3 experiment.py     # needs ffmpeg + numpy/scipy/scikit-learn/matplotlib
```

## Reading the result

- **macro-F1 and silhouette well above baseline** → call types are acoustically
  separable in an off-the-shelf space; representation approach confirmed.
- **near baseline** → classical features aren't enough; move to a pretrained
  audio embedder (BirdNET / PANNs) before concluding anything about the calls.

This is a *first pass*. It is single-species (American Crow) to avoid species
being a confound, and uses classical features as a floor — a learned embedder is
the documented upgrade. See `results/report.md` for the latest findings.
