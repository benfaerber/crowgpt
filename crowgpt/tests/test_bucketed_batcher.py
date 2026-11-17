from collections import Counter

import numpy as np

from crowgpt.train import Batcher, BucketedBatcher


class Sequences:
    def __init__(self, lengths):
        self.records = [{"length": int(n), "species": "american-crow", "group_key": str(i)}
                        for i, n in enumerate(lengths)]

    def __len__(self):
        return len(self.records)

    def sequence(self, i):
        return np.full(self.records[i]["length"], i % 1000, dtype=np.int64)


def padding(batcher, batches=200):
    shapes = [tuple(batcher.batch()[0].shape) for _ in range(batches)]
    return sum(rows * time for rows, time in shapes)


def dataset():
    return Sequences(np.random.default_rng(1).integers(20, 400, size=500))


def test_bucketing_pads_far_less():
    plain = padding(Batcher(dataset(), 8, 400, "cpu", seed=0))
    bucketed = padding(BucketedBatcher(dataset(), 8, 400, "cpu", seed=0))
    assert bucketed < 0.7 * plain


def test_every_sequence_is_still_drawn_as_often():
    batcher = BucketedBatcher(dataset(), 8, 400, "cpu", seed=0, window=16)
    drawn = Counter(int(p) for _ in range(4000) for p in batcher.picks())
    counts = np.array([drawn[i] for i in range(500)])
    assert counts.min() > 0
    assert abs(counts.mean() - 64) < 1e-9
    assert counts.std() < 12


def test_a_batch_holds_similar_lengths():
    data = dataset()
    batcher = BucketedBatcher(data, 8, 400, "cpu", seed=0)
    spreads = []
    for _ in range(64):
        lengths = [data.records[batcher.usable[p]]["length"] for p in batcher.picks()]
        spreads.append(max(lengths) - min(lengths))
    assert np.median(spreads) < 20


def test_a_token_budget_evens_out_the_tokens_per_step():
    data = dataset()
    batcher = BucketedBatcher(data, 8, 400, "cpu", seed=0, token_budget=1600)
    cells, drawn = [], 0
    for _ in range(300):
        picks = batcher.picks()
        lengths = [data.records[batcher.usable[p]]["length"] for p in picks]
        cells.append(len(lengths) * max(lengths))
        drawn += len(picks)
    assert max(cells) <= 1600
    assert np.mean(cells) > 0.85 * 1600


def test_a_token_budget_loses_no_draw():
    batcher = BucketedBatcher(dataset(), 8, 400, "cpu", seed=0, window=16, token_budget=1600)
    first = batcher.picks()
    assert len(first) + sum(map(len, batcher.queue)) == 8 * 16
