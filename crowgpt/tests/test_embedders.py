"""The embedder interface 0040 needed: joins go through embed_indexed.

BirdNET silently drops clips it finds no segment in, AST never does — a
caller written against AST looks correct until BirdNET is swapped in.
Both embedders therefore expose `embed_indexed`, and BirdNetEmbedder's
`embed` is the same call with the indices thrown away, kept only for
distribution work.
"""
import numpy as np

from crowgpt.embed import BirdNetEmbedder


class _FakeBirdNet:
    """Drops the middle clip, as BirdNET does to quiet audio."""

    def embed_indexed(self, clips):
        kept = [i for i in range(len(clips)) if i != 1]
        return np.ones((len(kept), 1024)), kept


def test_embed_indexed_reports_which_rows_survived():
    vectors, kept = BirdNetEmbedder(_FakeBirdNet()).embed_indexed(
        [np.zeros(24000)] * 3, 24000)
    assert kept == [0, 2]
    assert vectors.shape == (2, 1024)


def test_embed_is_the_indexless_view_of_the_same_call():
    embedder = BirdNetEmbedder(_FakeBirdNet())
    assert embedder.embed([np.zeros(24000)] * 3, 24000).shape == (2, 1024)
