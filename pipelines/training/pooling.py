"""Shared clip/region pooling — used by training AND inference so the feature
definition never drifts between them.

A clip (or a contiguous call region) is a stack of 3s BirdNET segment embeddings.
We summarize it with mean+std+max: the mean is the average voice, std+max encode
temporal spread — how much the call varies/peaks over time, which is the actual
signature of sustained/structured calls like song. -> 3 * 1024 = 3072 dims.
"""

import numpy as np

#: Which embedder produced the segment vectors, and how wide one of them is.
#: Named separately from FEATURE because a backbone swap changes both, and a
#: head trained on one cannot be fed the other — see _check_bundle in
#: analyzer/birdnet.py, which is the thing that now notices.
BACKBONE = "birdnet"
SEGMENT_DIM = 1024

#: mean, std, max.
BLOCKS = 3
POOLED_DIM = SEGMENT_DIM * BLOCKS

FEATURE = f"{BACKBONE}_pooled_mean_std_max"


def pool(segment_vectors):
    """mean+std+max over a clip/region's segment embeddings -> 3072-dim.

    A single-segment region has std=0 and max=mean; that's a valid, if flat,
    vector — the std block simply contributes little for isolated calls.
    """
    M = np.asarray(segment_vectors, dtype=np.float64)
    if M.ndim == 1:
        M = M[None, :]
    return np.concatenate([M.mean(0), M.std(0), M.max(0)])
