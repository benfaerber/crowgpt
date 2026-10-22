"""Vocabulary legality and the group split.

Both are silent failures. An unmasked vocabulary still trains — it just wastes
most of the output layer and can emit a token that will not decode. A leaky
split still reports a validation loss — it is just measuring the same bird
twice.
"""

import json

import numpy as np
import pytest

from crowgpt.codec import CODEBOOK_SIZE
from crowgpt.tokens import N_BUCKETS, BoutStore, Vocabulary

SPECIES = ["american-crow", "rook"]


@pytest.fixture
def vocab():
    return Vocabulary(n_codebooks=4, species=SPECIES)


def test_special_tokens_sit_above_the_codec_range(vocab):
    assert vocab.codec_size == CODEBOOK_SIZE * 4
    assert vocab.eos == vocab.codec_size
    assert vocab.size == vocab.codec_size + 1 + len(SPECIES) + N_BUCKETS
    assert vocab.species_token("rook") != vocab.species_token("american-crow")


def test_only_the_next_codebook_is_legal(vocab):
    """At offset j the next token belongs to codebook j % K and nothing else."""
    for offset in range(8):
        spans, _ = vocab.allowed(offset)
        stage = offset % 4
        assert spans == [(stage * CODEBOOK_SIZE, (stage + 1) * CODEBOOK_SIZE)]


def test_eos_is_legal_only_on_a_frame_boundary(vocab):
    """A partial frame cannot be decoded, so it must not be reachable."""
    assert vocab.allowed(0)[1] is True
    assert vocab.allowed(4)[1] is True
    for mid_frame in (1, 2, 3, 5, 6, 7):
        assert vocab.allowed(mid_frame)[1] is False


def test_mask_forbids_seven_eighths_of_the_vocabulary(vocab):
    mask = vocab.mask(8)
    assert mask[0].sum() == CODEBOOK_SIZE + 1  # codebook 0 plus EOS
    assert mask[1].sum() == CODEBOOK_SIZE
    assert not mask[1, vocab.eos]
    assert mask[0, :CODEBOOK_SIZE].all()
    assert not mask[0, CODEBOOK_SIZE : 2 * CODEBOOK_SIZE].any()


def test_duration_buckets_are_ordered_and_bounded(vocab):
    tokens = [vocab.duration_token(s) for s in (0.06, 0.3, 1.0, 2.9)]
    assert tokens == sorted(tokens)
    assert min(tokens) >= vocab.duration_base
    assert max(tokens) < vocab.size


def build_store(tmp_path, groups_per_species=25, bouts_per_group=3):
    """A store where every bout's group is known, so leaks are detectable."""
    rows = []
    offsets = {slug: 0 for slug in SPECIES}
    for slug in SPECIES:
        for group in range(groups_per_species):
            for bout in range(bouts_per_group):
                n = 2400
                rows.append(
                    {
                        "species": slug,
                        "recording_id": f"{group}",
                        "group_key": f"{slug}:g{group}",
                        "start_sec": 0.0,
                        "dur_sec": 0.1,
                        "crow_conf": 0.9,
                        "sample_offset": offsets[slug],
                        "n_samples": n,
                    }
                )
                offsets[slug] += n
        (tmp_path / f"{slug}.i16").write_bytes(
            np.zeros(offsets[slug], dtype=np.int16).tobytes()
        )
    (tmp_path / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return BoutStore(tmp_path)


def test_split_never_puts_a_group_on_two_sides(tmp_path):
    store = build_store(tmp_path)
    splits = store.split(seed=3)

    seen = {
        name: {store.index[i]["group_key"] for i in indices}
        for name, indices in splits.items()
    }
    assert seen["train"] & seen["val"] == set()
    assert seen["train"] & seen["test"] == set()
    assert seen["val"] & seen["test"] == set()


def test_split_covers_every_bout_exactly_once(tmp_path):
    store = build_store(tmp_path)
    splits = store.split(seed=1)
    allocated = [i for indices in splits.values() for i in indices]
    assert sorted(allocated) == list(range(len(store)))


def test_every_species_appears_in_every_split(tmp_path):
    """A grouped split can otherwise starve a species of validation data."""
    store = build_store(tmp_path)
    splits = store.split(seed=7)
    for name, indices in splits.items():
        present = {store.index[i]["species"] for i in indices}
        assert present == set(SPECIES), f"{name} is missing a species"


def test_ngram_index_finds_a_planted_copy_and_not_a_stranger():
    """The memorisation check must separate a copied span from fresh audio.

    Sequences here are random codes, so a shared n-gram cannot happen by
    accident — which is exactly why the planted one has to be found.
    """
    from crowgpt.judge import NgramIndex

    rng = np.random.default_rng(0)
    training = [rng.integers(0, 1024, size=4 * 200).astype(np.int64) for _ in range(20)]
    index = NgramIndex(n_codebooks=4)
    index.build(training)

    copied = training[3][: 4 * 60]
    fresh = rng.integers(0, 1024, size=4 * 60).astype(np.int64)

    assert index.hit_rate([copied])["32_frames"] == 1.0
    assert index.hit_rate([fresh])["32_frames"] == 0.0
