"""Batching, normalisation, and the one thing an eval must be: repeatable.

A flow loss depends on a random timestep and a random noise draw as well as on
the data. An eval that redraws them measures the dice as much as the model, and
`best_val` then records which step got the friendliest sample. 0023 caught this
project's earlier version of the same error — a dropout-active training minibatch
compared against a 20-batch eval() mean, reporting negative generalisation gaps.
"""
import numpy as np
import pytest
import torch

from crowgpt.flow import Config, FlowDiT
from crowgpt.flow_train import FrozenEval, LatentBatcher


class FakeDataset:
    """Bouts of assorted lengths, each filled with its own value."""

    def __init__(self, lengths, dim=8):
        self.dim = dim
        self.records = [{"start": 0, "frames": n} for n in lengths]
        self._blocks = [np.full((n, dim), i + 1, dtype=np.float16)
                        for i, n in enumerate(lengths)]

    def __len__(self):
        return len(self.records)

    def latent(self, i):
        return self._blocks[i]

    def statistics(self):
        stacked = np.concatenate(self._blocks).astype(np.float32)
        return stacked.mean(axis=0)[None], stacked.std(axis=0)[None]


@pytest.fixture
def batcher():
    return LatentBatcher(FakeDataset([5, 12, 3, 8]), batch_size=4, device="cpu", seed=0)


def test_mask_marks_exactly_the_real_frames(batcher):
    x, mask = batcher.batch([0, 1, 2, 3])
    assert x.shape == (4, 12, 8)
    assert mask.sum(dim=1).tolist() == [5, 12, 3, 8]


def test_padding_is_exactly_zero_after_normalising(batcher):
    """Not -mean/std, which is what a normalise-then-pad order would leave."""
    x, mask = batcher.batch([0, 1, 2, 3])
    assert torch.count_nonzero(x[~mask]) == 0


def test_normalise_round_trips(batcher):
    raw = torch.from_numpy(np.asarray(batcher.dataset.latent(1), dtype=np.float32))
    assert torch.allclose(batcher.denormalise(batcher.normalise(raw)), raw, atol=1e-4)


class TestNormalisation:
    """Whitening per channel throws away the RVQ's own importance ordering.

    Measured on this corpus: stage 0's channels have 9.9x the spread of stage
    31's, stages 0-3 hold 32.7% of total variance and stages 16-31 hold 8.7%.
    0024 proved the fine codebooks inaudible and 0035 measured them near-white,
    so that decay IS the perceptual weighting. Per-channel normalisation makes
    every channel unit variance, and a plain MSE then spends half its budget on
    stages known to be inaudible — invisible in a loss curve.
    """

    @pytest.fixture
    def uneven(self):
        rng = np.random.default_rng(0)
        data = FakeDataset([40, 40], dim=4)
        scales = np.array([8.0, 4.0, 2.0, 0.5], dtype=np.float32)
        data._blocks = [(rng.standard_normal((40, 4)) * scales).astype(np.float16)
                        for _ in range(2)]
        return data

    def test_global_preserves_the_relative_scales(self, uneven):
        batcher = LatentBatcher(uneven, 2, "cpu", normalisation="global")
        x, _ = batcher.batch([0, 1])
        spread = x.reshape(-1, 4).std(dim=0).numpy()
        raw = np.concatenate(uneven._blocks).astype(np.float32).std(axis=0)
        assert np.allclose(spread / spread[0], raw / raw[0], atol=0.05)

    def test_per_channel_flattens_them(self, uneven):
        batcher = LatentBatcher(uneven, 2, "cpu", normalisation="per_channel")
        x, _ = batcher.batch([0, 1])
        spread = x.reshape(-1, 4).std(dim=0).numpy()
        assert np.allclose(spread, np.ones(4), atol=0.05)

    def test_an_unknown_mode_is_refused(self, uneven):
        with pytest.raises(ValueError):
            LatentBatcher(uneven, 2, "cpu", normalisation="whatever")


def test_a_dead_channel_does_not_divide_by_zero():
    """DAC's upper stages come close to no spread at all; inf would take the run."""
    data = FakeDataset([4, 4])
    data._blocks = [np.zeros((4, 8), dtype=np.float16) for _ in range(2)]
    x, _ = LatentBatcher(data, 2, "cpu").batch([0, 1])
    assert torch.isfinite(x).all()


def test_long_bouts_are_cropped_to_max_frames():
    data = FakeDataset([50, 300])
    batcher = LatentBatcher(data, 2, "cpu", max_frames=64)
    x, mask = batcher.batch([0, 1])
    assert x.shape[1] == 64 and mask.sum(dim=1).tolist() == [50, 64]


class TestFrozenEval:
    @pytest.fixture
    def model(self):
        torch.manual_seed(0)
        return FlowDiT(Config(dim=8, n_layer=1, n_head=2, n_embd=16, max_frames=32))

    @pytest.fixture
    def evaluator(self, batcher):
        return FrozenEval(batcher, batches=3, seed=7)

    def test_the_same_model_scores_the_same_twice(self, evaluator, model):
        """The whole point. Redrawn noise would make these differ."""
        assert evaluator(model) == pytest.approx(evaluator(model), rel=1e-9)

    def test_it_can_still_tell_two_models_apart(self, evaluator, model, batcher):
        torch.manual_seed(1)
        other = FlowDiT(model.config)
        for parameter in other.parameters():
            torch.nn.init.normal_(parameter, std=0.1)
        assert evaluator(model) != pytest.approx(evaluator(other))

    def test_it_leaves_the_model_in_training_mode(self, evaluator, model):
        model.train()
        evaluator(model)
        assert model.training


@pytest.mark.skipif(not torch.cuda.is_available(), reason="FlowTrainer refuses the CPU")
def test_history_reports_a_gap_between_comparable_numbers(tmp_path):
    """train and val must both be frozen evals, or the gap is variance.

    The training minibatch loss is ONE random (t, noise) draw; the val loss is a
    16-batch frozen mean. Subtracting them compares a noisy sample against an
    average, which is the bug 0023 found in the incumbent's history.json — a
    dropout-active minibatch against a 20-batch eval() mean, reporting NEGATIVE
    generalisation gaps. So `train_minibatch` is kept but named for what it is,
    and `gap` is built from `train_frozen`.
    """
    from test_continuous import FakeCodec, FakeStore

    from crowgpt.continuous import LatentWriter
    from crowgpt.flow_train import FlowTrainer

    store = FakeStore([2000, 2400, 1800, 2200, 2600, 2100])
    LatentWriter(store, tmp_path, FakeCodec()).run(
        {"train": [0, 1, 2, 3], "val": [4], "test": [5]}, batch_size=2)

    trainer = FlowTrainer(tmp_path, tmp_path / "out", steps=2, batch_size=2,
                          eval_every=1)
    # Val must be scaled by TRAIN's statistics. Its own would make the two splits
    # differently scaled, and the val loss a measurement of a distribution the
    # model was never fitted to.
    assert torch.equal(trainer.val_batcher.mean, trainer.train_batcher.mean)
    assert torch.equal(trainer.val_batcher.std, trainer.train_batcher.std)

    history = trainer.run()["history"]
    assert history, "no evals recorded"
    for row in history:
        assert {"train_minibatch", "train_frozen", "val", "gap"} <= set(row)
        assert row["gap"] == pytest.approx(row["val"] - row["train_frozen"])
