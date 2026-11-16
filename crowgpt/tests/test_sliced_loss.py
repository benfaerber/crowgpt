import numpy as np
import pytest
import torch

from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.sliced import LegalSlices
from crowgpt.tokens import Vocabulary


@pytest.fixture
def setup():
    torch.manual_seed(0)
    vocabulary = Vocabulary(8, ["american-crow", "common-raven"], n_unit_buckets=5)
    block = 80
    model = CrowGPT(Config(vocab_size=vocabulary.size, n_codebooks=8, block_size=block,
                           n_layer=2, n_head=2, n_embd=32, dropout=0.0,
                           prefix_len=vocabulary.prefix_len)).double()
    legal = LegalMask(vocabulary, block + 1)
    rng = np.random.default_rng(0)
    sequences = []
    for length in (81, 49, 27):
        sequences.append([int(rng.choice(np.flatnonzero(legal.mask[p].numpy())))
                          for p in range(length)])
    longest = max(map(len, sequences))
    inputs = torch.zeros(len(sequences), longest - 1, dtype=torch.long)
    targets = torch.full((len(sequences), longest - 1), -1, dtype=torch.long)
    for row, sequence in enumerate(sequences):
        inputs[row, : len(sequence) - 1] = torch.tensor(sequence[:-1])
        targets[row, : len(sequence) - 1] = torch.tensor(sequence[1:])
    return model, legal, inputs, targets


def test_sliced_loss_equals_the_masked_loss(setup):
    model, legal, inputs, targets = setup
    _, masked = model(inputs, targets, legal.for_batch(inputs.size(1)))
    sliced = LegalSlices(legal).loss(model, inputs, targets)
    assert torch.isclose(masked.double(), sliced.double(), rtol=1e-6)


def test_sliced_gradients_equal_the_masked_gradients(setup):
    model, legal, inputs, targets = setup
    _, masked = model(inputs, targets, legal.for_batch(inputs.size(1)))
    masked.backward()
    expected = [p.grad.clone() for p in model.parameters()]
    model.zero_grad()
    LegalSlices(legal).loss(model, inputs, targets).backward()
    for want, parameter in zip(expected, model.parameters()):
        assert torch.allclose(want, parameter.grad, rtol=1e-4, atol=1e-7)


def test_an_illegal_target_is_refused(setup):
    model, legal, inputs, targets = setup
    targets[0, 20] = int(np.flatnonzero(~legal.mask[21].numpy())[0])
    with pytest.raises(ValueError):
        LegalSlices(legal).loss(model, inputs, targets)
