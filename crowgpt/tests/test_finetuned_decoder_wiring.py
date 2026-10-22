"""The finetuned-decoder wiring must be opt-in, loud on a bad path, and
change only what audio comes OUT — never what tokens go in.

The silent failure this guards: a decoder_state that quietly failed to load
would leave every "through the finetuned decoder" result actually measuring
the frozen one, which is 0063's improvement evaporating without anyone
noticing. So loading records the resolved path, and a missing file raises.
"""
import numpy as np
import pytest
import torch

from crowgpt.codec import Codec


@pytest.fixture(scope="module")
def frozen():
    return Codec(bandwidth=6.0, device="cpu")


def _checkpoint(tmp_path, decoder, nudge=0.0):
    state = {k: v.clone() + nudge for k, v in decoder.state_dict().items()}
    path = tmp_path / "best.pt"
    torch.save({"decoder": state, "step": 1}, path)
    return path


def test_default_is_the_shipped_decoder(frozen):
    assert frozen.decoder_state is None


def test_loading_records_the_resolved_path(frozen, tmp_path):
    path = _checkpoint(tmp_path, frozen.model.decoder)
    codec = Codec(bandwidth=6.0, device="cpu", decoder_state=path)
    assert codec.decoder_state == str(path)


def test_missing_checkpoint_raises_rather_than_falling_back(tmp_path):
    with pytest.raises((FileNotFoundError, OSError)):
        Codec(bandwidth=6.0, device="cpu", decoder_state=tmp_path / "absent.pt")


def test_tokens_are_bit_identical_but_audio_moves(frozen, tmp_path):
    path = _checkpoint(tmp_path, frozen.model.decoder, nudge=0.01)
    nudged = Codec(bandwidth=6.0, device="cpu", decoder_state=path)
    t = np.arange(24000) / 24000
    clip = (0.5 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
    a, b = frozen.encode(clip), nudged.encode(clip)
    assert torch.equal(a, b)
    assert not np.allclose(frozen.decode(a)[0], nudged.decode(b)[0])
