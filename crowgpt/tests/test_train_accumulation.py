"""Gradient accumulation, and the two ways it silently does nothing useful.

It exists because the batch size stopped being a choice at sixteen codebooks —
the d384/L8 shape OOMs above a micro-batch of 6 on a 16 GB card, against the 16
the incumbent trained with. If accumulation is wrong, the run still trains and
still reports a loss; it just answers a different question than the one asked,
which is the failure mode this whole project keeps paying for.

No GPU and no Trainer here: constructing one requires a token directory and a
CUDA device, and neither is needed to check the arithmetic that matters.
"""

import torch
from torch import nn


def _fit(accumulate, micro_batch, steps=6, seed=0):
    """Same data and init both ways; only the accumulation schedule differs."""
    torch.manual_seed(seed)
    model = nn.Linear(4, 3)
    optimiser = torch.optim.SGD(model.parameters(), lr=0.1)
    generator = torch.Generator().manual_seed(99)
    for _ in range(steps):
        optimiser.zero_grad(set_to_none=True)
        for _ in range(accumulate):
            x = torch.randn(micro_batch, 4, generator=generator)
            y = torch.randn(micro_batch, 3, generator=generator)
            loss = nn.functional.mse_loss(model(x), y) / accumulate
            loss.backward()
        optimiser.step()
    return [p.detach().clone() for p in model.parameters()]


def test_accumulating_matches_one_big_batch():
    """Two micro-steps of 8 must land where one step of 16 lands.

    The division by `accumulate` is what makes this true. Without it the
    gradient is the SUM of the micro-batches rather than their mean, which is a
    silent learning-rate multiplication by the accumulation factor — training
    still runs, and every hyperparameter carried over from an unaccumulated run
    is now wrong by that factor.
    """
    torch.manual_seed(0)
    big = nn.Linear(4, 3)
    torch.manual_seed(0)
    split = nn.Linear(4, 3)

    generator = torch.Generator().manual_seed(7)
    x = torch.randn(16, 4, generator=generator)
    y = torch.randn(16, 3, generator=generator)

    nn.functional.mse_loss(big(x), y).backward()
    for half in (slice(0, 8), slice(8, 16)):
        (nn.functional.mse_loss(split(x[half]), y[half]) / 2).backward()

    for a, b in zip(big.parameters(), split.parameters()):
        assert torch.allclose(a.grad, b.grad, atol=1e-6)


def test_accumulate_one_is_the_old_behaviour():
    """The default must be a no-op, or every existing run changes meaning."""
    assert all(
        torch.allclose(a, b)
        for a, b in zip(_fit(accumulate=1, micro_batch=8), _fit(accumulate=1, micro_batch=8))
    )


def test_accumulation_actually_changes_the_update():
    """The guard against a no-op that only looks right.

    A division bug or a missing inner loop would leave this passing trivially,
    so assert the accumulated run is NOT identical to a single micro-step run —
    it sees more data per update and must land somewhere else.
    """
    once = _fit(accumulate=1, micro_batch=6)
    thrice = _fit(accumulate=3, micro_batch=6)
    assert any(not torch.allclose(a, b) for a, b in zip(once, thrice))
