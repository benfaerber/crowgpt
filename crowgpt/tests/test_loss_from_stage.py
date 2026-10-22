"""The extender's loss mask, and the two ways it silently trains the wrong thing.

`loss_from_stage=8` is meant to score only the fine codebooks while still letting
the model see every coarse token as context. Both failure modes are silent: a
mask that also blanks EOS trains a model that never learns to stop, and a mask
that leaves coarse targets in trains an ordinary flat model under a name that
says otherwise. Neither raises, and both produce a plausible loss curve.

No GPU and no token directory here — the mask is arithmetic on ids, and
`Trainer.__init__` would need both.
"""

import torch

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.tokens import Vocabulary
from crowgpt.train import Trainer

SPECIES = ["american-crow", "rook"]
K = 24


class _MaskOnly:
    """Trainer's mask without Trainer's constructor."""

    def __init__(self, vocabulary, loss_from_stage):
        self.vocabulary = vocabulary
        self.loss_from_stage = loss_from_stage

    mask = Trainer._mask_coarse


def _subject(loss_from_stage=8):
    return _MaskOnly(Vocabulary(K, SPECIES), loss_from_stage)


def _code(stage, entry=7):
    return stage * CODEBOOK_SIZE + entry


def test_coarse_targets_are_blanked_and_fine_targets_survive():
    subject = _subject()
    targets = torch.tensor([[_code(s) for s in range(K)]])
    out = subject.mask(targets)
    for stage in range(K):
        if stage < 8:
            assert out[0, stage] == -1, f"stage {stage} should be masked"
        else:
            assert out[0, stage] == _code(stage), f"stage {stage} should survive"


def test_eos_survives_the_mask():
    """The failure that would train a model unable to stop.

    EOS sits at exactly CODEBOOK_SIZE * n_codebooks, so a mask written as a bare
    `targets // CODEBOOK_SIZE < cut` without the codec-range guard would still
    spare it — but only because n_codebooks happens to exceed the cut. Asserted
    directly so the guard cannot be removed on the grounds that it is redundant.
    """
    vocab = Vocabulary(K, SPECIES)
    subject = _subject()
    targets = torch.tensor([[vocab.eos, vocab.species_token("rook"),
                             vocab.duration_token(1.0), _code(0), _code(20)]])
    out = subject.mask(targets)
    assert out[0, 0] == vocab.eos
    assert out[0, 1] == vocab.species_token("rook")
    assert out[0, 2] == vocab.duration_token(1.0)
    assert out[0, 3] == -1          # coarse, masked
    assert out[0, 4] == _code(20)   # fine, kept


def test_padding_stays_masked():
    out = _subject().mask(torch.tensor([[-1, -1, _code(9)]]))
    assert out[0, 0] == -1 and out[0, 1] == -1 and out[0, 2] == _code(9)


def test_no_cut_is_the_old_behaviour():
    """None must be a no-op, or every existing run changes meaning."""
    targets = torch.tensor([[_code(0), _code(9), -1, Vocabulary(K, SPECIES).eos]])
    assert torch.equal(_subject(loss_from_stage=None).mask(targets), targets)
    assert torch.equal(_subject(loss_from_stage=0).mask(targets), targets)


def test_something_is_actually_left_to_learn():
    """Guard against a cut that masks everything and still trains happily."""
    subject = _subject()
    targets = torch.tensor([[_code(s) for s in range(K)]])
    assert int((subject.mask(targets) >= 0).sum()) == K - 8
