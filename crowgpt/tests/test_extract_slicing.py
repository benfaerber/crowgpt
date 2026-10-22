"""Slice ownership in extraction: every bout lands exactly once.

The slicing exists because whole-file loading OOM-killed the pool on the
2026-08 scrape's multi-hour recordings. Its quiet failure mode is at the
edges: a bout in the overlap belongs to two loaded spans, and either both
keep it (a duplicate in the corpus, invisible) or neither does (a lost call,
also invisible). Ownership is by global midpoint against `own_until`; these
pin that rule and the global/local time split.
"""
import numpy as np
import pytest

from crowgpt import extract
from crowgpt.extract import _keepable
from crowgpt.segment import ANALYSIS_SR

META = {"species": "american-crow", "recording_id": "r1",
        "group_key": "g1", "quality": None}


@pytest.fixture(autouse=True)
def conf():
    old = dict(extract.CONF)
    extract.CONF.update({"CROW_MIN_CONF": 0.1})
    yield
    extract.CONF.clear()
    extract.CONF.update(old)


def _span_with_burst(at_sec, seconds=6.0, burst=0.4):
    t = np.arange(int(seconds * ANALYSIS_SR)) / ANALYSIS_SR
    y = np.random.default_rng(0).normal(0, 0.001, t.size).astype(np.float32)
    lo = int(at_sec * ANALYSIS_SR)
    hi = lo + int(burst * ANALYSIS_SR)
    y[lo:hi] += (0.6 * np.sin(2 * np.pi * 2000 * t[: hi - lo])).astype(np.float32)
    return y


def _grid(seconds, window=3.0):
    return np.ones(max(1, int(seconds // window))), window


def test_bout_times_are_global(conf):
    y = _span_with_burst(2.0)
    grid, window = _grid(6.0)
    part = _keepable(y, ANALYSIS_SR, grid, window, META, offset=900.0)
    assert len(part["kept"]) == 1
    assert 901.5 < part["kept"][0]["start_sec"] < 902.5


def test_a_bout_past_own_until_is_left_for_the_next_slice(conf):
    y = _span_with_burst(4.0)          # global midpoint ~904.2
    grid, window = _grid(6.0)
    part = _keepable(y, ANALYSIS_SR, grid, window, META,
                     offset=900.0, own_until=904.0)
    assert part["kept"] == []
    # and it was not counted as dropped — the next slice owns it whole
    assert part["dropped_conf"] == 0 and part["dropped_tail"] == 0


def test_the_owning_slice_keeps_that_same_bout(conf):
    # The next slice starts at 904 with 5 s of lead-in overlap from 899.
    y = _span_with_burst(5.0)          # local 5.0 = global 904.2 from offset 899.2
    grid, window = _grid(6.0)
    part = _keepable(y, ANALYSIS_SR, grid, window, META,
                     offset=899.2, own_until=float("inf"))
    assert len(part["kept"]) == 1
    assert 904.0 < part["kept"][0]["start_sec"] < 905.0


def test_tail_trim_judges_global_time(conf):
    y = _span_with_burst(2.0)
    grid, window = _grid(6.0)
    part = _keepable(y, ANALYSIS_SR, grid, window, META,
                     offset=900.0, tail_cut=901.0)
    assert part["kept"] == [] and part["dropped_tail"] == 1
