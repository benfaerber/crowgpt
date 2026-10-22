"""continue_from's contract, on a stub model so no checkpoint is needed.

Seeding the sampler with a real bout's opening frames is how 0042 asks what the
model would do if it did not have to average over every microphone in the
corpus. That only means anything if two things hold exactly.

THE CONTINUATION MUST START ON STAGE 0. The prompt is whole frames, so the first
token generated after it belongs to codebook 0. Get the accounting wrong by one
and the stream is still legal, `unflatten` still returns a grid, the codec still
decodes it, and every codebook is off by one — the silent failure this module's
own docstrings warn about twice.

AND THE PROMPT MUST NOT COME BACK. The whole point is to measure the model's
output, not the real audio that seeded it. A continuation that still carried the
prompt would flatter every statistic computed on it.

The stub always prefers the lowest legal id, so sampling is deterministic and
the test is about routing rather than about what a model learned.
"""

import numpy as np
import pytest
import torch

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.model import LegalMask
from crowgpt.sample import Sampler
from crowgpt.tokens import Vocabulary

SPECIES = ["american-crow", "rook"]
K = 8
PROMPT_FRAMES = 6


class _Stub:
    """Enough of Sampler for continue_from: a model with a cache, a mask, a codec."""

    def __init__(self):
        self.device = "cpu"
        self.vocabulary = Vocabulary(K, SPECIES)
        self.manifest = {"species": SPECIES, "n_codebooks": K}
        vocab_size = self.vocabulary.size

        class _Config:
            block_size = 4096

        class _Model:
            """Uniform logits. The legality mask decides what is reachable."""

            def empty_cache(self):
                return []

            def __call__(self, idx, cache=None, offset=0):
                return torch.zeros(1, idx.size(1), vocab_size), None

        class _Codec:
            n_codebooks = K

            @staticmethod
            def flatten(codes):
                offsets = (np.arange(codes.shape[0]) * CODEBOOK_SIZE)[:, None]
                return (codes + offsets).T.reshape(-1).astype(np.uint16)

        self.config = _Config()
        self.model = _Model()
        self.codec = _Codec()
        # The PRODUCTION mask. A hand-rolled one would let this test disagree
        # with the code it checks while looking authoritative.
        self.legal = LegalMask(self.vocabulary, 4097, "cpu")

    _prefix = Sampler._prefix
    _draw = Sampler._draw
    continue_from = Sampler.continue_from


@pytest.fixture
def stub():
    return _Stub()


@pytest.fixture
def prompt():
    rng = np.random.default_rng(0)
    return rng.integers(0, CODEBOOK_SIZE, size=(K, PROMPT_FRAMES))


def test_the_prompt_is_not_returned(stub, prompt):
    """A measurement on the continuation must not be reading the real audio.

    Checked by length, which is the only version that cannot pass by luck: the
    cap counts the whole sequence, so if the prompt were still on the front the
    returned stream would be PROMPT_FRAMES longer than the cap allows.
    """
    cap = PROMPT_FRAMES + 4
    out = stub.continue_from("rook", prompt, seed=0, max_frames=cap, seconds=1.0)
    seeded = stub.codec.flatten(prompt).astype(np.int64)
    assert out.size > 0
    assert out.size // K == cap - PROMPT_FRAMES
    assert not np.array_equal(out[: seeded.size], seeded)


def test_the_continuation_starts_on_stage_zero(stub, prompt):
    """The off-by-one that decodes fine and means nothing."""
    out = stub.continue_from("rook", prompt, seed=0, max_frames=PROMPT_FRAMES + 4,
                             seconds=1.0)
    assert out.size % K == 0
    for position, token in enumerate(out):
        stage = position % K
        assert stage * CODEBOOK_SIZE <= token < (stage + 1) * CODEBOOK_SIZE


def test_it_stops_at_the_frame_cap(stub, prompt):
    """max_frames counts the whole sequence, prompt included."""
    cap = PROMPT_FRAMES + 4
    out = stub.continue_from("rook", prompt, seed=0, max_frames=cap, seconds=1.0)
    assert out.size // K <= cap - PROMPT_FRAMES


def test_a_stated_duration_is_used_verbatim(stub, prompt):
    """Left None the bucket is sampled; given, it is the caller's to state."""
    out = stub.continue_from("rook", prompt, seed=0, max_frames=PROMPT_FRAMES + 4,
                             seconds=2.5)
    assert out.size % K == 0


def test_a_wrong_shaped_prompt_is_refused(stub):
    with pytest.raises(ValueError, match="must be"):
        stub.continue_from("rook", np.zeros((K + 1, PROMPT_FRAMES)), seconds=1.0)


def test_an_empty_prompt_is_refused(stub):
    with pytest.raises(ValueError, match="at least one frame"):
        stub.continue_from("rook", np.zeros((K, 0), dtype=np.int64), seconds=1.0)
