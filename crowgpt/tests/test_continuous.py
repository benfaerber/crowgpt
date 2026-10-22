"""The continuous latent path: the cascade, the store, and the layout.

The store tests use a fake codec, because what they check is cursor arithmetic
and memmap layout, and those are exactly the things a real codec would make slow
without making truer. THE LAYOUT TEST IS THE POINT: the first version of
`LatentWriter` wrote each bout as [dim, frames] in C order and read the split
back with a Fortran-order reshape, which cannot work the moment two bouts have
different lengths — every bout after the first would be silently misaligned and
would still decode.
"""
import json

import numpy as np
import pytest
import torch

from crowgpt.continuous import (STAGE_DIM, ContinuousCodec, LatentDataset,
                                LatentWriter, check_precision)

HAS_CUDA = torch.cuda.is_available()


class FakeCodec:
    """Encodes to a per-bout constant, so misalignment is visible by value."""

    kind = "fake-continuous"
    n_stages = 2

    @property
    def dim(self):
        return self.n_stages * STAGE_DIM

    def frames(self, n_samples):
        return max(1, int(np.ceil(n_samples / 320)))

    def encode(self, batch):
        out = torch.zeros(len(batch), self.dim, batch.shape[1] // 320 + 1)
        for i, row in enumerate(batch):
            out[i] = float(np.round(np.abs(row).max() * 1000))
        return out


class FakeStore:
    def __init__(self, lengths):
        self.index = [
            {"species": "american-crow", "group_key": f"g{i}", "recording_id": f"r{i}",
             "n_samples": n, "sample_offset": 0}
            for i, n in enumerate(lengths)
        ]

    def audio(self, row):
        marker = (self.index.index(row) + 1) / 1000.0
        return np.full(row["n_samples"], marker, dtype=np.float32)


@pytest.fixture
def written(tmp_path, monkeypatch):
    monkeypatch.setattr("crowgpt.codec.normalise", lambda x: x, raising=False)
    lengths = [700, 1600, 400, 3000, 900, 320]
    store = FakeStore(lengths)
    splits = {"train": [0, 1, 2, 3], "val": [4], "test": [5]}
    writer = LatentWriter(store, tmp_path, FakeCodec())
    manifest = writer.run(splits, batch_size=2)
    return tmp_path, manifest, store, lengths


def test_every_bout_reads_back_at_its_own_length(written):
    out_dir, _, store, lengths = written
    data = LatentDataset(out_dir, "train")
    codec = FakeCodec()
    for i, record in enumerate(data.records):
        expected = codec.frames(store.index[record["bout"]]["n_samples"])
        assert record["frames"] == expected
        assert data.latent(i).shape == (expected, codec.dim)


def test_bouts_do_not_bleed_into_each_other(written):
    """Each bout encoded to its own constant, so a shifted cursor shows up."""
    out_dir, _, _, _ = written
    data = LatentDataset(out_dir, "train")
    for i in range(len(data)):
        block = np.asarray(data.latent(i), dtype=np.float32)
        assert len(np.unique(block)) == 1, "bout overlaps its neighbour"


def test_cursors_tile_the_split_without_gaps(written):
    out_dir, manifest, _, _ = written
    data = LatentDataset(out_dir, "train")
    cursor = 0
    for record in data.records:
        assert record["start"] == cursor
        cursor += record["frames"]
    assert cursor == manifest["splits"]["train"]["frames"]
    assert data.stream.shape == (cursor, manifest["dim"])


def test_statistics_are_train_only_and_broadcast(written):
    out_dir, manifest, _, _ = written
    mean, std = LatentDataset(out_dir, "train").statistics()
    assert mean.shape == (1, manifest["dim"]) and std.shape == (1, manifest["dim"])
    train = np.asarray(LatentDataset(out_dir, "train").stream, dtype=np.float32)
    assert np.allclose(mean[0], train.mean(axis=0), atol=1e-3)


def test_species_filter_excludes_and_keeps_splits(tmp_path):
    store = FakeStore([700, 800])
    store.index[1]["species"] = "common-raven"
    writer = LatentWriter(store, tmp_path, FakeCodec(), species=["american-crow"])
    manifest = writer.run({"train": [0, 1]}, batch_size=4)
    assert manifest["splits"]["train"]["bouts"] == 1


@pytest.fixture(scope="module")
def codec():
    return ContinuousCodec(n_stages=32)


@pytest.fixture(scope="module")
def audio():
    rng = np.random.default_rng(0)
    t = np.arange(24000) / 24000.0
    tone = 0.3 * np.sin(2 * np.pi * 900 * t) * np.exp(-3 * t)
    return (tone + 0.01 * rng.standard_normal(t.size)).astype(np.float32)


def log_mel_distance(a, b):
    """Spectral, NEVER sample-wise.

    0039 recorded that a sample-wise RMS comparison ranks DAC's arms BACKWARDS,
    because its round-trip carries a median five-sample offset — "would have sent
    someone hunting a nonexistent DAC bug". The first version of the round-trip
    test below did exactly that and failed on a perfectly good codec.
    """
    import librosa

    n = min(len(a), len(b))
    mel = lambda x: np.log(librosa.feature.melspectrogram(
        y=np.asarray(x[:n], dtype=np.float64), sr=24000,
        n_fft=1024, hop_length=256, n_mels=80) + 1e-7)
    A, B = mel(a), mel(b)
    w = min(A.shape[1], B.shape[1])
    return float(np.mean(np.abs(A[:, :w] - B[:, :w])))


@pytest.mark.skipif(not HAS_CUDA, reason="needs the GPU and DAC weights")
class TestAgainstRealDac:
    def test_dim_and_frames(self, codec, audio):
        latent = codec.encode(audio)
        assert latent.shape[1] == codec.dim == 256
        assert latent.shape[2] >= codec.frames(audio.size)

    def test_it_is_not_the_quantized_path(self, codec, audio):
        """The cascade must differ from `model.encode`'s latents.

        Those follow the QUANTIZED trajectory — each stage sees a residual that
        earlier codebook errors have shifted. If these ever match, the codebook
        lookup is back in and every 0052 conclusion is being measured on the
        discrete path under a continuous name.
        """
        mine = codec.encode(audio)
        with torch.no_grad():
            batch = torch.from_numpy(audio)[None, None].to(codec.device)
            _, _, theirs, _, _ = codec.model.encode(codec.model.preprocess(batch, 24000))
        width = min(mine.shape[2], theirs.shape[2])
        assert not torch.allclose(mine[..., :width], theirs[:, :256, :width], atol=1e-4)

    def test_roundtrip_beats_the_transparent_codec(self, codec, audio):
        """The core 0052 claim, as a regression test.

        cont32 measured 0.2588 log-mel against quantized-24cb's 0.3686 — and 24cb
        is the setting 0039 cleared by ABX at chance. If this ever inverts, the
        cascade has drifted back toward the quantized path.
        """
        mine = codec.roundtrip(audio)[0]
        with torch.no_grad():
            batch = torch.from_numpy(audio)[None, None].to(codec.device)
            z = codec.model.encoder(codec.model.preprocess(batch, 24000))
            z_q, _, _, _, _ = codec.model.quantizer(z, n_quantizers=24)
            quantized = codec.model.decode(z_q).squeeze(1).squeeze(0).cpu().numpy()
        assert log_mel_distance(audio, mine) < log_mel_distance(audio, quantized)

    def test_padding_does_not_leak_between_batch_rows(self, codec, audio):
        """Batched convolution is not bit-identical to unbatched, so the bar is
        the 0052 budget rather than equality: a real leak would be enormous
        against a channel's spread, and kernel-order noise is ~1e-3 of it."""
        short = audio[:8000]
        alone = codec.encode(short)[0, :, : codec.frames(short.size)]
        together = codec.encode(np.stack([short, np.zeros_like(short)]))[0][
            :, : codec.frames(short.size)]
        spread = alone.std(dim=1, keepdim=True).clamp_min(1e-8)
        assert float(((alone - together).abs() / spread).max()) < 0.02

    def test_float16_storage_is_far_inside_the_0052_budget(self, codec, audio):
        """0052 measured 20% of a channel's spread as inaudible (10/25, below chance)."""
        assert check_precision(codec, audio) < 0.02
