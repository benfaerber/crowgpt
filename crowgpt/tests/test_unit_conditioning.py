"""The unit-bucket token: counted at tokenize time, sampled at generation.

Exists because 0024 measured generated bouts at 1.37 caws against real
audio's 3.37, and the fix threads through the project's most bitten seam —
the prefix whose stated part is shorter than prefix_len. Every failure here
is silent: a wrong slot order shifts every codebook by one and the audio
still decodes; a legality mask that admits a duration where a unit count
belongs trains fine and samples garbage.
"""
import json

import numpy as np
import pytest

from crowgpt.model import LegalMask
from crowgpt.tokens import (
    N_BUCKETS,
    N_UNIT_BUCKETS,
    BoutStore,
    TokenWriter,
    Vocabulary,
)

SR = 24000


class TestVocabulary:
    def test_zero_buckets_is_the_old_vocabulary_bit_for_bit(self):
        old = Vocabulary(8, ["american-crow"])
        assert old.n_unit_buckets == 0
        assert old.prefix_len == 2
        assert old.sampled_slots == 1
        assert old.size == old.channel_base  # nothing above channels

    def test_units_extend_the_prefix_and_id_space(self):
        vocab = Vocabulary(8, ["american-crow"], n_unit_buckets=N_UNIT_BUCKETS)
        assert vocab.prefix_len == 3
        assert vocab.sampled_slots == 2
        assert vocab.size == vocab.unit_base + N_UNIT_BUCKETS

    def test_slot_order_units_then_duration_last(self):
        vocab = Vocabulary(8, ["american-crow"], n_unit_buckets=N_UNIT_BUCKETS)
        slots = vocab.prefix_slots()
        assert slots[-2] == (vocab.unit_base, vocab.unit_base + N_UNIT_BUCKETS)
        assert slots[-1] == (vocab.duration_base, vocab.duration_base + N_BUCKETS)

    def test_bucketing_matches_its_documented_edges(self):
        vocab = Vocabulary(8, ["american-crow"], n_unit_buckets=N_UNIT_BUCKETS)
        buckets = [vocab.unit_token(n) - vocab.unit_base for n in (1, 2, 3, 4, 5, 6, 40)]
        assert buckets == [0, 1, 2, 3, 3, 4, 4]

    def test_old_vocabulary_refuses_unit_tokens(self):
        with pytest.raises(ValueError):
            Vocabulary(8, ["american-crow"]).unit_token(3)


class TestLegalMask:
    def test_the_sampled_tail_is_walked_slot_by_slot(self):
        vocab = Vocabulary(8, ["american-crow"], n_unit_buckets=N_UNIT_BUCKETS)
        mask = LegalMask(vocab, 32)
        unit_pos, dur_pos = 1, 2   # species stated at 0
        legal_units = ~mask.forbidden[unit_pos]
        legal_dur = ~mask.forbidden[dur_pos]
        assert legal_units[vocab.unit_base : vocab.unit_base + N_UNIT_BUCKETS].all()
        assert not legal_units[vocab.duration_base : vocab.duration_base + N_BUCKETS].any()
        assert legal_dur[vocab.duration_base : vocab.duration_base + N_BUCKETS].all()
        assert not legal_dur[vocab.unit_base : vocab.unit_base + N_UNIT_BUCKETS].any()


def _bout(n_caws, seconds=2.5):
    t = np.arange(int(seconds * SR)) / SR
    y = np.random.default_rng(0).normal(0, 0.001, t.size).astype(np.float32)
    for k in range(n_caws):
        lo = int((0.2 + 0.5 * k) * SR)
        hi = lo + int(0.25 * SR)
        y[lo:hi] += (0.6 * np.sin(2 * np.pi * 2000 * t[: hi - lo])).astype(np.float32)
    return y


@pytest.fixture
def store(tmp_path):
    rows, shards = [], []
    offset = 0
    for n, caws in enumerate([1, 3, 4]):
        clip = (_bout(caws) * 32000).astype(np.int16)
        rows.append({"species": "american-crow", "recording_id": f"r{n}",
                     "group_key": f"g{n}", "sample_offset": offset,
                     "n_samples": clip.size})
        shards.append(clip)
        offset += clip.size
    np.concatenate(shards).tofile(tmp_path / "american-crow.i16")
    (tmp_path / "index.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return BoutStore(tmp_path)


class TestTokenWriter:
    def test_units_are_counted_and_written_into_the_prefix(self, store, tmp_path):
        writer = TokenWriter(store, tmp_path / "tokens", bandwidth=6.0,
                             device="cpu", augment=False, unit_buckets=True)
        splits = {"train": [0, 1, 2]}
        manifest = writer.run(splits)
        assert manifest["n_unit_buckets"] == N_UNIT_BUCKETS
        assert manifest["prefix_len"] == 3

        records = [json.loads(l) for l in
                   (tmp_path / "tokens" / "train.jsonl").read_text().splitlines()]
        counts = {r["recording_id"]: r["units"] for r in records}
        assert counts["r0"] == 1 and counts["r1"] == 3 and counts["r2"] == 4

        stream = np.fromfile(tmp_path / "tokens" / "train.u16", dtype=np.uint16)
        first = stream[records[0]["start"] : records[0]["start"] + 3]
        vocab = writer.vocab
        assert first[0] == vocab.species_token("american-crow")
        assert first[1] == vocab.unit_token(records[0]["units"])
        assert vocab.duration_base <= first[2] < vocab.duration_base + N_BUCKETS

    def test_default_writer_is_unchanged(self, store, tmp_path):
        writer = TokenWriter(store, tmp_path / "tokens", bandwidth=6.0,
                             device="cpu", augment=False)
        manifest = writer.run({"train": [0]})
        assert manifest["n_unit_buckets"] == 0
        assert manifest["prefix_len"] == 2
