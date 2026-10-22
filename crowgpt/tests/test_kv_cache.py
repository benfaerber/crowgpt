"""The KV cache, held to the only standard that matters: identical output.

A cache is an optimisation, so the entire specification is "same answer,
faster". Every way of getting it wrong produces plausible audio and a plausible
loss — a mis-sized causal mask makes the model attend to almost nothing, a
forgotten position offset gives every generated token the first token's
position, and both decode fine and sound like the model got worse. So the test
is equality against the uncached path, not a property of the cached one.

CPU and tiny on purpose: this is arithmetic, and a GPU adds nondeterminism
without adding coverage.
"""

import pytest
import torch

from crowgpt.model import Config, CrowGPT

VOCAB, K = 64, 4


@pytest.fixture
def model():
    torch.manual_seed(0)
    config = Config(vocab_size=VOCAB, n_codebooks=K, block_size=64,
                    n_layer=3, n_head=2, n_embd=32, dropout=0.0)
    return CrowGPT(config).eval()


def _uncached(model, sequence):
    """Logits for the next token, the slow way: re-run the whole prefix."""
    with torch.no_grad():
        logits, _ = model(sequence)
    return logits[:, -1, :]


def _cached(model, sequence, prime):
    """Prime on the first `prime` tokens, then feed the rest one at a time."""
    cache = model.empty_cache()
    with torch.no_grad():
        logits, _ = model(sequence[:, :prime], cache=cache, offset=0)
        for position in range(prime, sequence.size(1)):
            logits, _ = model(sequence[:, position:position + 1],
                              cache=cache, offset=position)
    return logits[:, -1, :]


def test_cached_logits_match_uncached(model):
    """The whole specification."""
    torch.manual_seed(1)
    sequence = torch.randint(0, VOCAB, (1, 24))
    assert torch.allclose(_uncached(model, sequence), _cached(model, sequence, prime=8),
                          atol=1e-5)


def test_priming_length_does_not_matter(model):
    """Where the cache is started must not change what comes out."""
    torch.manual_seed(2)
    sequence = torch.randint(0, VOCAB, (1, 20))
    reference = _uncached(model, sequence)
    for prime in (1, 2, 5, 13, 19):
        assert torch.allclose(reference, _cached(model, sequence, prime=prime), atol=1e-5), (
            f"prime={prime} disagrees with the uncached path"
        )


def test_every_step_agrees_not_just_the_last(model):
    """A cache that is wrong early can still be right at the end by luck."""
    torch.manual_seed(3)
    sequence = torch.randint(0, VOCAB, (1, 16))
    cache = model.empty_cache()
    with torch.no_grad():
        model(sequence[:, :4], cache=cache, offset=0)
        for position in range(4, sequence.size(1)):
            step, _ = model(sequence[:, position:position + 1], cache=cache, offset=position)
            full, _ = model(sequence[:, :position + 1])
            assert torch.allclose(step[:, -1, :], full[:, -1, :], atol=1e-5), (
                f"diverged at position {position}"
            )


def test_the_offset_is_load_bearing(model):
    """Guard the failure that decodes fine and is silently wrong.

    Feeding every cached step offset=0 gives each new token the position
    embedding of the very first one. Nothing raises; the audio just stops
    tracking position. Assert the wrong offset really does change the answer,
    so the parameter cannot be dropped as decoration.
    """
    torch.manual_seed(4)
    sequence = torch.randint(0, VOCAB, (1, 12))
    cache = model.empty_cache()
    with torch.no_grad():
        model(sequence[:, :6], cache=cache, offset=0)
        wrong, _ = model(sequence[:, 6:7], cache=cache, offset=0)
    assert not torch.allclose(wrong[:, -1, :], _uncached(model, sequence[:, :7]), atol=1e-5)


def test_batches_are_cached_independently(model):
    """Sampling generates one bout at a time today, but nothing says it must."""
    torch.manual_seed(5)
    sequence = torch.randint(0, VOCAB, (3, 18))
    assert torch.allclose(_uncached(model, sequence), _cached(model, sequence, prime=7),
                          atol=1e-5)


def test_a_cache_is_not_reused_across_sequences(model):
    """empty_cache must hand back genuinely empty slots, not a shared list."""
    first, second = model.empty_cache(), model.empty_cache()
    assert first is not second
    assert all(a is not b for a, b in zip(first, second))
    assert all(slot == [] for slot in first)
