"""complete_fine's contract, on a stub model so no checkpoint is needed.

The extender's inference path has one property that makes it either right or
silently useless: the coarse codes handed in must come back out UNCHANGED and in
the right stage slots. If they are offset wrongly, every stage but the first
lands in codebook 0's range, `unflatten` still returns a plausible grid, the
codec still decodes it, and the audio is simply wrong with nothing raising.

The model here always prefers the lowest legal id, so sampling is deterministic
and the test is about routing rather than about what the model learned.
"""

import numpy as np
import pytest
import torch

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.model import LegalMask
from crowgpt.sample import Sampler
from crowgpt.tokens import Vocabulary

SPECIES = ["american-crow", "rook"]
K = 12
FROM_STAGE = 4
FRAMES = 5


class _Stub:
    """Enough of Sampler for complete_fine: a model, a vocabulary, a mask."""

    def __init__(self):
        self.device = "cpu"
        self.vocabulary = Vocabulary(K, SPECIES)
        self.manifest = {"species": SPECIES, "n_codebooks": K}

        class _Config:
            block_size = 4096

        class _Model:
            def __call__(_, window):
                # Uniform logits; the legality mask decides what is reachable.
                return torch.zeros(1, window.size(1), self.vocabulary.size), None

        self.config = _Config()
        self.model = _Model()
        # The PRODUCTION mask, not a hand-rolled one. Its row for a sequence of
        # length L is allowed(L - prefix_len), and getting that offset wrong in a
        # fixture would make this test disagree with the code it is checking
        # while looking authoritative.
        self.legal = LegalMask(self.vocabulary, 400, "cpu")

    _prefix = Sampler._prefix
    complete_fine = Sampler.complete_fine


@pytest.fixture
def stub():
    return _Stub()


@pytest.fixture
def coarse():
    rng = np.random.default_rng(0)
    return rng.integers(0, CODEBOOK_SIZE, size=(FROM_STAGE, FRAMES))


def test_the_coarse_codes_come_back_unchanged(stub, coarse):
    """The whole point: conditioning must survive the round trip exactly."""
    flat = stub.complete_fine("rook", coarse, from_stage=FROM_STAGE, seed=0)
    grid = flat.reshape(FRAMES, K).T - (np.arange(K) * CODEBOOK_SIZE)[:, None]
    assert np.array_equal(grid[:FROM_STAGE], coarse)


def test_every_token_lands_in_its_own_stage_slice(stub, coarse):
    """The offset bug that decodes fine and means nothing."""
    flat = stub.complete_fine("rook", coarse, from_stage=FROM_STAGE, seed=0)
    for position, token in enumerate(flat):
        stage = position % K
        assert stage * CODEBOOK_SIZE <= token < (stage + 1) * CODEBOOK_SIZE


def test_length_is_the_coarse_streams_to_decide(stub, coarse):
    """EOS must never be sampled — structure was fixed before this ran."""
    flat = stub.complete_fine("rook", coarse, from_stage=FROM_STAGE, seed=0)
    assert flat.size == FRAMES * K
    assert stub.vocabulary.eos not in set(flat.tolist())


def test_a_wrong_shaped_coarse_stream_is_refused(stub):
    with pytest.raises(ValueError, match="expected"):
        stub.complete_fine("rook", np.zeros((FROM_STAGE + 1, FRAMES)), from_stage=FROM_STAGE)
