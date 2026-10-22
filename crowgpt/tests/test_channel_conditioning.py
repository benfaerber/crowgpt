"""The channel token: vocabulary layout, mask slots, and the batch-time splice.

0042 measured that timbre varies 6.2x more between recordings than within one,
and the generator has no token for which recording. This is the token, and it is
spliced into the prefix at BATCH time so the corpus never has to be re-encoded.

Three things here fail silently rather than loudly, which is why each has a test.

THE DURATION SLOT USED TO RUN TO THE END OF THE VOCABULARY. `LegalMask` built it
as `(duration_base, vocabulary.size)`, which was correct exactly as long as
nothing lived after the duration buckets. A channel token does, so that slot
would have admitted a channel id where a duration belongs — legal, decodable,
and wrong.

THE MASK USED TO GUESS WHAT THE MIDDLE SLOT WAS, branching on `prefix_len == 3`
to decide "call type". With two optional axes that question has no answer, and
the wrong branch puts call-type ids in a channel's slot.

AND THE SPLICE GOES BEFORE THE DURATION BUCKET, not after. Duration has to stay
the last prefix position because that is the one `Sampler.tokens` lets the model
sample; insert after it and generation samples a channel and states a duration,
which is backwards.
"""

import numpy as np
import pytest

from crowgpt.model import LegalMask
from crowgpt.train import Batcher
from crowgpt.tokens import N_BUCKETS, Vocabulary

SPECIES = ["american-crow", "rook"]
CALL_TYPES = ["alarm call", "unknown"]
CHANNELS = ["channel-000", "channel-001", "channel-002"]
K = 8


class _Records:
    """A TokenDataset stand-in: stored sequences with no channel token in them."""

    def __init__(self, vocab_without_channel, recordings):
        self.records = [
            {"length": 4 + K, "species": SPECIES[0], "recording_id": r, "canonical": i % 2 == 0}
            for i, r in enumerate(recordings)
        ]
        self.v = vocab_without_channel

    def __len__(self):
        return len(self.records)

    def sequence(self, i):
        prefix = [self.v.species_token(SPECIES[0])]
        if self.v.call_types:
            prefix.append(self.v.calltype_token("alarm call"))
        prefix.append(self.v.duration_token(1.0))
        # Legal codec ids: at stage j only that stage's 1024-wide slice is
        # reachable, so a fixture emitting range(K) would be rejected by the
        # very mask this file is testing.
        return np.array(prefix + [j * 1024 + 5 for j in range(K)], dtype=np.int64)


class _Buckets:
    def __init__(self, mapping):
        self.mapping = mapping

    def assign(self, recording_id):
        return self.mapping.get(recording_id, CHANNELS[0])


def test_channels_extend_the_prefix_and_the_vocabulary():
    plain = Vocabulary(K, SPECIES)
    with_channels = Vocabulary(K, SPECIES, channels=CHANNELS)
    assert plain.prefix_len == 2
    assert with_channels.prefix_len == 3
    assert with_channels.size == plain.size + len(CHANNELS)
    # Every other id keeps its meaning, so an existing token set still reads.
    assert with_channels.species_base == plain.species_base
    assert with_channels.duration_base == plain.duration_base


def test_the_duration_slot_no_longer_runs_to_the_end_of_the_vocabulary():
    """The bug the channel token would otherwise have walked into."""
    v = Vocabulary(K, SPECIES, channels=CHANNELS)
    start, end = v.prefix_slots()[-1]
    assert (start, end) == (v.duration_base, v.duration_base + N_BUCKETS)
    assert end <= v.channel_base


def test_each_prefix_position_admits_only_its_own_tokens():
    v = Vocabulary(K, SPECIES, CALL_TYPES, CHANNELS)
    mask = LegalMask(v, 64, "cpu").mask
    assert v.prefix_len == 4
    expected = [
        (v.species_base, len(SPECIES)),
        (v.calltype_base, len(CALL_TYPES)),
        (v.channel_base, len(CHANNELS)),
        (v.duration_base, N_BUCKETS),
    ]
    for position, (base, count) in enumerate(expected):
        legal = mask[position].nonzero().flatten().tolist()
        assert legal == list(range(base, base + count))


def test_the_codec_stream_still_starts_after_the_longer_prefix():
    """Stage phase is measured from prefix_len; a wrong one is off by a codebook."""
    v = Vocabulary(K, SPECIES, channels=CHANNELS)
    mask = LegalMask(v, 64, "cpu").mask
    first = set(mask[v.prefix_len].nonzero().flatten().tolist())
    # Stage 0's slice, plus EOS — a bout may end on a frame boundary.
    assert first == set(range(1024)) | {v.eos}


def test_the_splice_lands_immediately_before_the_duration_bucket():
    plain = Vocabulary(K, SPECIES)
    v = Vocabulary(K, SPECIES, channels=CHANNELS)
    dataset = _Records(plain, ["r0", "r1"])
    buckets = _Buckets({"r0": "channel-002", "r1": "channel-001"})
    batcher = Batcher(dataset, 2, 4096, "cpu", vocabulary=v, channels=buckets)

    out = batcher.sequence(0)
    stored = dataset.sequence(0)
    assert len(out) == len(stored) + 1
    assert out[0] == v.species_token(SPECIES[0])
    assert out[1] == v.channel_token("channel-002")
    assert out[2] == v.duration_token(1.0)
    assert list(out[v.prefix_len:]) == [j * 1024 + 5 for j in range(K)]
    # And a different recording gets a different token, or the whole thing is a
    # constant and conditions on nothing.
    assert batcher.sequence(1)[1] == v.channel_token("channel-001")


def test_the_spliced_token_is_legal_where_it_lands():
    v = Vocabulary(K, SPECIES, channels=CHANNELS)
    dataset = _Records(Vocabulary(K, SPECIES), ["r0"])
    batcher = Batcher(dataset, 1, 4096, "cpu", vocabulary=v,
                      channels=_Buckets({"r0": "channel-002"}))
    mask = LegalMask(v, 64, "cpu").mask
    for position, token in enumerate(batcher.sequence(0)):
        assert mask[position, int(token)], f"position {position} forbids {token}"


def test_without_channels_the_sequence_is_untouched():
    """An unconditioned run must read the same token set byte for byte."""
    plain = Vocabulary(K, SPECIES)
    dataset = _Records(plain, ["r0"])
    batcher = Batcher(dataset, 1, 4096, "cpu", vocabulary=plain, channels=None)
    assert np.array_equal(batcher.sequence(0), dataset.sequence(0))


def test_canonical_only_drops_the_augmented_variants():
    """The train/val gap has to compare like with like."""
    plain = Vocabulary(K, SPECIES)
    dataset = _Records(plain, [f"r{i}" for i in range(6)])
    everything = Batcher(dataset, 1, 4096, "cpu", vocabulary=plain)
    scoring = Batcher(dataset, 1, 4096, "cpu", vocabulary=plain, canonical_only=True)
    assert len(everything.usable) == 6
    assert len(scoring.usable) == 3
    assert all(dataset.records[i]["canonical"] for i in scoring.usable)


def test_an_unknown_channel_name_is_refused():
    v = Vocabulary(K, SPECIES, channels=CHANNELS)
    with pytest.raises(ValueError):
        v.channel_token("channel-999")
