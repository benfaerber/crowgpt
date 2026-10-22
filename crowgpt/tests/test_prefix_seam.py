"""The seam that shifted every codebook twice, now owned by one object.

`Sampler._prefix` writes fewer tokens than `prefix_len` claims because the
model samples the trailing slots (duration, unit bucket). Both historical
bugs were a caller measuring the written list where it meant the stated
length. `Prefix` makes that mistake unrepresentable: `stated_len` is
constant whether a slot is sampled or stated, and it must always equal the
vocabulary's `prefix_len`.
"""
import pytest

from crowgpt.sample import Prefix
from crowgpt.tokens import Vocabulary


@pytest.mark.parametrize("call_types,channels,units", [
    ((), (), 0),
    (("caw", "rattle"), (), 0),
    ((), ("ch0", "ch1"), 0),
    (("caw",), ("ch0",), 8),
])
def test_stated_len_always_matches_the_vocabulary(call_types, channels, units):
    vocab = Vocabulary(8, ("american-crow",), call_types, channels,
                       n_unit_buckets=units)
    written = [vocab.species_token("american-crow")]
    if call_types:
        written.append(vocab.calltype_token(call_types[0]))
    if channels:
        written.append(vocab.channel_token(channels[0]))
    prefix = Prefix(written, vocab.sampled_slots)
    assert prefix.stated_len == vocab.prefix_len


def test_stating_a_slot_moves_it_without_changing_the_length():
    prefix = Prefix([7], sampled=2)
    before = prefix.stated_len
    prefix.state(41)
    assert prefix.written == [7, 41]
    assert prefix.sampled == 1
    assert prefix.stated_len == before


def test_stating_more_slots_than_exist_refuses():
    prefix = Prefix([7], sampled=1).state(41)
    with pytest.raises(ValueError):
        prefix.state(42)
