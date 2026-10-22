"""The delay pattern's arithmetic, which is silent when it is backwards.

A delay applied in the wrong direction, or unwound by the wrong offset, still
produces a K-periodic stream of legal ids that `unflatten` reshapes and the codec
decodes. The audio comes out wrong and nothing raises — the same shape of failure
as `complete_fine`'s missing duration token, which shifted every stage by one and
was caught only by a round-trip test.

So the specification is a round trip: codes in, codes out, identical.
"""

import numpy as np
import pytest

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.dac_codec import Delayed

K = 8


class _Flat:
    """The flat layout, standing in for a real codec."""

    n_codebooks = K
    bandwidth = 6.0
    kind = "encodec-24khz"
    vocab_size = CODEBOOK_SIZE * K

    def flatten(self, codes):
        codes = np.asarray(codes)
        offsets = (np.arange(codes.shape[0]) * CODEBOOK_SIZE)[:, None]
        return (codes + offsets).T.reshape(-1).astype(np.uint16)

    def unflatten(self, tokens):
        tokens = np.asarray(tokens, dtype=np.int64)
        frames = tokens.size // self.n_codebooks
        grid = tokens[: frames * self.n_codebooks].reshape(frames, self.n_codebooks).T
        return grid - (np.arange(self.n_codebooks) * CODEBOOK_SIZE)[:, None]


@pytest.fixture
def delayed():
    return Delayed(_Flat())


@pytest.fixture
def codes():
    return np.random.default_rng(0).integers(0, CODEBOOK_SIZE, size=(K, 60))


def test_the_round_trip_is_exact(delayed, codes):
    """The whole specification."""
    assert np.array_equal(delayed.unflatten(delayed.flatten(codes)), codes)


@pytest.mark.parametrize("frames", [1, 2, K - 1, K, K + 1, 225])
def test_the_round_trip_holds_at_every_length(delayed, frames):
    """Short bouts are where an off-by-one hides: the corpus has 0.08 s clips."""
    codes = np.random.default_rng(frames).integers(0, CODEBOOK_SIZE, size=(K, frames))
    assert np.array_equal(delayed.unflatten(delayed.flatten(codes)), codes)


def test_stage_k_really_carries_frame_t_minus_k(delayed, codes):
    """The delay must exist. A no-op wrapper passes the round trip trivially."""
    grid = _Flat().unflatten(delayed.flatten(codes))
    for k in range(K):
        # Past the head, block i at stage k holds frame i - k.
        for block in range(k, k + 5):
            assert grid[k][block] == codes[k][block - k]


def test_the_head_is_clamped_not_padded(delayed, codes):
    """Clamping is what keeps the vocabulary and the legality mask unchanged."""
    grid = _Flat().unflatten(delayed.flatten(codes))
    for k in range(1, K):
        for block in range(k):
            assert grid[k][block] == codes[k][0]
    assert grid.max() < CODEBOOK_SIZE, "a pad id would sit outside the codebook"


def test_the_stream_stays_k_periodic(delayed, codes):
    """Every position must still hold an id from its own stage's slice.

    This is the property `Vocabulary.allowed` and `LegalMask` rely on, and the
    reason nothing downstream needed changing.
    """
    flat = delayed.flatten(codes)
    for position, token in enumerate(flat):
        stage = position % K
        assert stage * CODEBOOK_SIZE <= token < (stage + 1) * CODEBOOK_SIZE


def test_length_grows_by_exactly_k_minus_one_blocks(delayed, codes):
    assert delayed.flatten(codes).size == (codes.shape[1] + K - 1) * K


def test_a_truncated_stream_loses_frames_rather_than_scrambling(delayed, codes):
    """Generation stops on EOS mid-stream; the tail must degrade gracefully."""
    flat = delayed.flatten(codes)
    cut = flat[: (codes.shape[1] // 2) * K]
    out = delayed.unflatten(cut)
    assert out.shape[0] == K
    assert np.array_equal(out, codes[:, : out.shape[1]])


def test_the_kind_round_trips_through_a_manifest(delayed):
    """A token set written delayed and read back flat decodes silently wrong."""
    assert delayed.kind == "encodec-24khz+delay"
    from crowgpt.tokens import codec_from_manifest

    rebuilt = codec_from_manifest(
        {"codec": "encodec-24khz+delay", "bandwidth": 6.0, "n_codebooks": 8},
        device="cpu")
    assert isinstance(rebuilt, Delayed)
