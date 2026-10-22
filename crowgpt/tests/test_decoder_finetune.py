"""The decoder finetune's quiet failure modes, checked before GPU-days.

The expensive run is unattended, so what these guard is the class of bug that
trains for three days and produces a plausible-looking checkpoint: a loss that
is zero on everything, a discriminator that never sees the fake, a crop
sampler that silently reads val bouts into training, or a resume that loses
the optimizer.
"""
import json

import numpy as np
import pytest
import torch

from crowgpt.decoder_finetune import (
    CropSampler,
    MsStftDiscriminator,
    SpectralLoss,
)
from crowgpt.tokens import BoutStore

SR = 24000


def _tone(freq, seconds=1.5):
    t = np.arange(int(seconds * SR)) / SR
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


@pytest.fixture
def store(tmp_path):
    """A real BoutStore on disk: one species, twelve groups, 1.5 s bouts."""
    rows, samples = [], []
    offset = 0
    for n in range(12):
        clip = (_tone(400 + 50 * n) * 32000).astype(np.int16)
        rows.append({
            "species": "american-crow",
            "recording_id": f"rec{n}",
            "group_key": f"group{n}",
            "sample_offset": offset,
            "n_samples": clip.size,
        })
        samples.append(clip)
        offset += clip.size
    np.concatenate(samples).tofile(tmp_path / "american-crow.i16")
    (tmp_path / "index.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows))
    return BoutStore(tmp_path)


class TestSpectralLoss:
    def test_zero_on_identical(self):
        clip = torch.from_numpy(_tone(440))[None]
        assert SpectralLoss()(clip, clip).item() == pytest.approx(0.0)

    def test_positive_on_different(self):
        loss = SpectralLoss()(torch.from_numpy(_tone(440))[None],
                              torch.from_numpy(_tone(880))[None])
        assert loss.item() > 0.1

    def test_gradient_reaches_the_fake(self):
        fake = torch.from_numpy(_tone(440))[None].requires_grad_(True)
        SpectralLoss()(fake, torch.from_numpy(_tone(880))[None]).backward()
        assert fake.grad is not None and fake.grad.abs().sum() > 0


class TestDiscriminator:
    def test_one_verdict_and_feature_stack_per_scale(self):
        disc = MsStftDiscriminator()
        out = disc(torch.from_numpy(_tone(440))[None])
        assert len(out) == len(disc.scales)
        for score, features in out:
            assert score.dim() == 4
            assert len(features) == 5

    def test_real_and_fake_get_different_scores(self):
        torch.manual_seed(0)
        disc = MsStftDiscriminator()
        real = disc(torch.from_numpy(_tone(440))[None])
        noise = disc(torch.randn(1, int(SR * 1.5)))
        gap = sum((r[0].mean() - f[0].mean()).abs().item()
                  for r, f in zip(real, noise))
        assert gap > 0  # untrained nets may score close; identical means a bug


class TestCropSampler:
    def test_trains_only_on_the_train_split(self, store):
        sampler = CropSampler(store)
        splits = store.split(seed=0)
        held = set(splits["val"]) | set(splits["test"])
        assert held, "fixture must produce held-out groups"
        assert not held.intersection(sampler.rows)

    def test_crops_are_exactly_one_second(self, store):
        batch = CropSampler(store).batch(size=4)
        assert batch.shape == (4, SR)
        assert batch.dtype == torch.float32

    def test_seeded_and_deterministic(self, store):
        a = CropSampler(store, seed=0).batch(size=4)
        b = CropSampler(store, seed=0).batch(size=4)
        assert torch.equal(a, b)

    def test_corpus_seconds_counts_train_only(self, store):
        sampler = CropSampler(store)
        expected = sum(store.index[i]["n_samples"] for i in sampler.rows) / SR
        assert sampler.corpus_seconds == pytest.approx(expected)


@pytest.fixture(scope="module")
def job(tmp_path_factory):
    from crowgpt.decoder_finetune import DecoderFinetune
    return DecoderFinetune(
        "adversarial", tmp_path_factory.mktemp("out"), device="cpu")


class TestTrainStep:
    """One real step on CPU with the real EnCodec — slow-ish, and the only
    test that would catch a loss wired to the wrong tensor."""

    def test_step_moves_decoder_and_only_decoder(self, job):
        torch.manual_seed(0)
        crops = torch.from_numpy(
            np.stack([_tone(440, 1.0), _tone(660, 1.0)]))
        encoder_before = [p.clone() for p in job.model.encoder.parameters()]
        decoder_before = [p.clone() for p in job.model.decoder.parameters()]
        losses = job.train_step(crops)
        assert all(np.isfinite(v) for v in losses.values())
        assert {"spec", "adv", "feat", "disc"} == set(losses)
        assert any(not torch.equal(b, p) for b, p in
                   zip(decoder_before, job.model.decoder.parameters()))
        assert all(torch.equal(b, p) for b, p in
                   zip(encoder_before, job.model.encoder.parameters()))

    def test_checkpoint_resume_round_trip(self, job, tmp_path):
        job.checkpoint({"ast_fad": 1.0, "stft_logged": 1.0, "unit_delta": 0.0})
        from crowgpt.decoder_finetune import DecoderFinetune
        fresh = DecoderFinetune("adversarial", job.out.parent, device="cpu")
        assert fresh.resume()
        assert fresh.step == job.step
        assert fresh.best_fad == 1.0
        for a, b in zip(job.model.decoder.parameters(),
                        fresh.model.decoder.parameters()):
            assert torch.equal(a, b)
