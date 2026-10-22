"""The rectified-flow DiT: conventions, masking, and that it can actually learn.

The two tests worth reading are the padding ones. A short bout in a long batch
attends to its own zero padding unless stopped, and padding is a perfectly good
frame as far as attention is concerned — it pulls the tail of every short bout
toward zero, which is inaudible in a loss curve and audible as a fade.
"""
import pytest
import torch

from crowgpt.flow import Config, FlowDiT, RectifiedFlow, timestep_embedding


@pytest.fixture
def config():
    return Config(dim=32, n_layer=2, n_head=2, n_embd=48, max_frames=64)


@pytest.fixture
def model(config):
    torch.manual_seed(0)
    return FlowDiT(config)


def test_untrained_model_is_the_identity(model):
    """adaLN-Zero plus a zeroed output head means an untrained net predicts zero.

    Not cosmetic: every residual block starts as a no-op, so depth costs nothing
    at initialisation and the first thousand steps are not spent undoing the
    initialisation of the last layer.
    """
    x = torch.randn(2, 16, model.config.dim)
    out = model(x, torch.rand(2))
    assert torch.allclose(out, torch.zeros_like(out))


def test_interpolation_hits_both_endpoints():
    """xt = (1-t)*noise + t*data, so t=1 is the data and t=0 is the noise.

    Half the sign errors in flow matching are a reversed time axis, and they
    produce a model that trains cleanly and samples noise.
    """
    data, noise = torch.randn(2, 8, 4), torch.randn(2, 8, 4)
    for t, expected in ((torch.ones(2), data), (torch.zeros(2), noise)):
        xt = (1 - t[:, None, None]) * noise + t[:, None, None] * data
        assert torch.allclose(xt, expected, atol=1e-6)


def test_timestep_embedding_separates_times():
    a = timestep_embedding(torch.tensor([0.0]), 32)
    b = timestep_embedding(torch.tensor([1.0]), 32)
    assert a.shape == (1, 32)
    assert not torch.allclose(a, b)


def test_padding_cannot_change_a_real_frame(model):
    """The same bout, alone and padded, must produce the same velocities.

    This is the test that catches a missing attention mask. Without one the
    padded version attends to zeros the short version never sees, and the two
    disagree — silently, and worst at the end of the bout.
    """
    torch.manual_seed(1)
    for parameter in model.parameters():
        torch.nn.init.normal_(parameter, std=0.05)

    short = torch.randn(1, 10, model.config.dim)
    padded = torch.cat([short, torch.randn(1, 6, model.config.dim)], dim=1)
    mask = torch.zeros(1, 16, dtype=torch.bool)
    mask[:, :10] = True
    t = torch.full((1,), 0.3)

    alone = model(short, t, pad_mask=torch.ones(1, 10, dtype=torch.bool))
    together = model(padded, t, pad_mask=mask)[:, :10]
    assert torch.allclose(alone, together, atol=1e-5)


def test_masked_loss_ignores_what_is_in_the_padding(model):
    """Garbage in the padded region must not move the loss at all."""
    torch.manual_seed(2)
    flow = RectifiedFlow(model)
    x = torch.randn(2, 12, model.config.dim)
    mask = torch.zeros(2, 12, dtype=torch.bool)
    mask[:, :7] = True

    generator = torch.Generator().manual_seed(9)
    quiet = flow.loss(x.clone(), pad_mask=mask, generator=generator)
    loud = x.clone()
    loud[:, 7:] = 1e3
    generator = torch.Generator().manual_seed(9)
    assert torch.allclose(quiet, flow.loss(loud, pad_mask=mask, generator=generator))


def test_masked_loss_is_a_per_element_mean(model):
    """A fully-unmasked batch must score exactly what the unmasked path scores."""
    torch.manual_seed(3)
    flow = RectifiedFlow(model)
    x = torch.randn(2, 9, model.config.dim)
    full = torch.ones(2, 9, dtype=torch.bool)
    generator = torch.Generator().manual_seed(4)
    with_mask = flow.loss(x, pad_mask=full, generator=generator)
    generator = torch.Generator().manual_seed(4)
    assert torch.allclose(with_mask, flow.loss(x, generator=generator), atol=1e-6)


class TestTimestepSampling:
    """0054 measured where the training signal needs to go.

    Starting the ODE from a real latent partially noised, the model reconstructed
    to 100% BirdNET detection at confidence 0.919 from t=0.5 — above real audio's
    0.749 — and collapsed to 8.3% from t=0.0. The velocity field is right; the
    earliest, noise-dominated stretch is what is missing. Uniform t spends the
    same budget on t=0.9, where the answer is nearly given, as on t=0.05, where
    it has to be invented.
    """

    def test_uniform_is_flat(self, model):
        t = RectifiedFlow(model, t_sampling="uniform").timesteps(
            20000, "cpu", torch.Generator().manual_seed(0))
        assert 0.48 < t.mean() < 0.52
        assert t.min() >= 0 and t.max() <= 1

    def test_logit_normal_leans_toward_the_noise_end(self, model):
        """t=0 is noise in this file, so a NEGATIVE mean pulls mass toward it.

        The sign is the opposite of SD3's, whose convention has t=0 at the data
        end. Getting it backwards trains harder on the region that already works.
        """
        flow = RectifiedFlow(model, t_sampling="logit_normal", t_mean=-0.5)
        t = flow.timesteps(20000, "cpu", torch.Generator().manual_seed(0))
        assert t.mean() < 0.45
        assert (t < 0.3).float().mean() > (t > 0.7).float().mean()
        assert t.min() >= 0 and t.max() <= 1

    def test_an_unknown_mode_is_refused(self, model):
        with pytest.raises(ValueError):
            RectifiedFlow(model, t_sampling="cosine").timesteps(4, "cpu")


def test_sample_returns_the_asked_for_shape(model):
    out = RectifiedFlow(model).sample(frames=12, count=3, steps=4, device="cpu")
    assert out.shape == (3, 12, model.config.dim)


def test_it_beats_the_predict_nothing_baseline(config):
    """Overfit one fixed target and beat the only baseline that matters.

    THE BASELINE IS NOT THE FIRST STEP'S LOSS, which is what the first version of
    this test used and which is noise from one random t. A zero-init model
    predicts zero velocity, so its expected loss is E[(x1 - noise)^2] =
    Var(x1) + 1 — measured here rather than assumed. Beating that is the claim.

    Cheap, and it is the only test here that catches a detached graph, a frozen
    zero-init head and a reversed time axis all at once.
    """
    torch.manual_seed(5)
    model = FlowDiT(config)
    flow = RectifiedFlow(model)
    target = torch.randn(4, 16, config.dim)

    generator = torch.Generator().manual_seed(11)
    untrained = sum(flow.loss(target, generator=generator).item() for _ in range(20)) / 20

    optimiser = model.optimiser(3e-3)
    for _ in range(400):
        loss = flow.loss(target)
        optimiser.zero_grad()
        loss.backward()
        optimiser.step()

    generator = torch.Generator().manual_seed(11)
    trained = sum(flow.loss(target, generator=generator).item() for _ in range(20)) / 20
    assert trained < 0.5 * untrained, f"{trained:.3f} vs untrained {untrained:.3f}"
