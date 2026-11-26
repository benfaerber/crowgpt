"""Shared clip/region pooling — used by training AND inference so the feature
definition never drifts between them.

Two BirdNET pooling schemes live side by side because five species heads were
trained on `mean+std+max` (`3072-d`) while American Crow moved to uniform
window-mean (`1024-d`) after experiments 0036 and 0121:

- `birdnet_pooled_mean_std_max` (`3072-d`): `concat(mean, std, max)` across 3 s
  segment embeddings. Kept for the archive-only species heads (`carrion-crow`,
  `common-raven`, `hooded-crow`, `large-billed-crow`, `rook`).
- `birdnet_window_mean` (`1024-d`): `mean` across 3 s segment embeddings.
  Eliminates the single-window `std = 0` / `max = mean` degeneracy where mixed
  training corpora let linear heads read region length instead of call acoustics
  (experiments 0036 and 0121: kept multi-window span accuracy 50% -> 100%).
"""

import numpy as np

#: Which embedder produced the segment vectors, and how wide one of them is.
#: Named separately from FEATURE because a backbone swap changes both, and a
#: head trained on one cannot be fed the other — see _check_bundle in
#: analyzer/birdnet.py, which is the thing that notices.
BACKBONE = "birdnet"
SEGMENT_DIM = 1024

#: mean, std, max.
BLOCKS = 3
POOLED_DIM = SEGMENT_DIM * BLOCKS
FEATURE = f"{BACKBONE}_pooled_mean_std_max"

#: Uniform window mean (experiment 0121).
MEAN_DIM = SEGMENT_DIM
MEAN_FEATURE = f"{BACKBONE}_window_mean"


def pool(segment_vectors):
    """mean+std+max over a clip/region's segment embeddings -> 3072-dim.

    A single-segment region has std=0 and max=mean; that's a valid, if flat,
    vector — the std block simply contributes little for isolated calls.
    """
    M = np.asarray(segment_vectors, dtype=np.float64)
    if M.ndim == 1:
        M = M[None, :]
    return np.concatenate([M.mean(0), M.std(0), M.max(0)])


def pool_mean(segment_vectors):
    """Uniform mean over a clip/region's 3s segment embeddings -> 1024-dim."""
    M = np.asarray(segment_vectors, dtype=np.float64)
    if M.ndim == 1:
        M = M[None, :]
    return M.mean(0)


#: Known BirdNET feature spaces -> (expected_dim, pooling_fn).
FEATURES = {
    FEATURE: (POOLED_DIM, pool),
    MEAN_FEATURE: (MEAN_DIM, pool_mean),
}


def pool_for(feature: str):
    """Return the pooling callable for a named feature space."""
    if feature not in FEATURES:
        raise KeyError(
            f"unknown BirdNET feature {feature!r}; expected one of {sorted(FEATURES)}"
        )
    return FEATURES[feature][1]
