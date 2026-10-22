"""The segmenter's two order-dependent behaviours.

Both of these are silent when wrong: you get a plausible number of plausible
looking bouts, just not the ones you meant.
"""

import numpy as np
import pytest

from crowgpt.segment import Segmenter

FPS = 125.0  # ANALYSIS_SR 32000 with a 256-sample hop


def envelope_with(hot_spans, n_frames=400, floor=-60.0, peak=-20.0):
    db = np.full(n_frames, floor)
    for start, end in hot_spans:
        db[start:end] = peak
    return db


@pytest.fixture
def seg():
    return Segmenter()


def test_merges_before_dropping_short_bursts(seg):
    """Two 40 ms bursts 48 ms apart are one call, not two rejects.

    Filtering by duration first would drop both (each is under the 60 ms
    minimum) and lose a real 128 ms call. This is the ordering experiment 0013
    relies on and the reason a caw is not counted three times.
    """
    db = envelope_with([(100, 105), (111, 116)])
    units = seg.bursts(db, FPS, floor_db=-60.0)

    assert len(units) == 1
    start, end = units[0]
    assert (end - start) / FPS == pytest.approx(0.128, abs=0.01)


def test_bursts_further_apart_than_the_gap_stay_separate(seg):
    """A 120 ms gap exceeds the 80 ms merge, so these are two calls."""
    db = envelope_with([(100, 115), (130, 145)])
    assert len(seg.bursts(db, FPS, floor_db=-60.0)) == 2


def test_isolated_short_burst_is_dropped(seg):
    """A lone 40 ms blip is a click, not a caw."""
    db = envelope_with([(100, 105)])
    assert seg.bursts(db, FPS, floor_db=-60.0) == []


def test_threshold_is_twelve_db_not_eight(seg):
    """0013 section E: 6 dB goes flat against the confidence gradient.

    A burst 9 dB above the floor is background at the threshold this project
    settled on, and would have been a call at the value 0013's run.py defaults
    to. Guards against the default silently coming back.
    """
    assert seg.burst_db == 12.0
    db = envelope_with([(100, 130)], floor=-60.0, peak=-51.0)
    assert seg.bursts(db, FPS, floor_db=-60.0) == []


def test_bouts_group_calls_within_the_gap(seg):
    """Calls 0.5 s apart are one bout; 2 s apart are two."""
    close = [(0, 20), (85, 105)]
    apart = [(0, 20), (270, 290)]

    assert len(seg.bouts(close, FPS)) == 1
    assert len(seg.bouts(apart, FPS)) == 2


def test_bouts_split_rather_than_truncate_at_the_cap(seg):
    """A long run becomes several bouts, all of them whole.

    Truncating would teach the model that caw sequences stop abruptly at
    exactly 3.0 s, which is an artefact of BirdNET's window, not of crows.
    """
    units = [(i * 50, i * 50 + 20) for i in range(12)]
    bouts = seg.bouts(units, FPS)

    assert len(bouts) > 1
    for start, end in bouts:
        assert (end - start) / FPS <= seg.bout_max_sec + 1e-6
    assert bouts[-1][1] == units[-1][1]


def test_segment_returns_seconds_not_frames(seg):
    sr = 32000
    y = np.random.default_rng(0).normal(0, 0.001, sr * 2)
    y[sr // 2 : sr // 2 + 4000] += np.random.default_rng(1).normal(0, 0.5, 4000)

    bouts, units = seg.segment(y, sr)
    assert bouts and units
    for start, end in bouts:
        assert 0.0 <= start < end <= 2.0


def test_silence_yields_nothing(seg):
    assert seg.segment(np.zeros(32000), 32000) == ([], [])


def test_a_single_over_long_burst_is_split(seg):
    """Continuous energy for 23 s is one unit, and must not survive as one bout.

    Left whole these are long enough to fall outside any fixed context window
    and be dropped without a word — 3% of the corpus, holding 8% of its audio.
    """
    long_run = [(0, int(23 * FPS))]
    bouts = seg.bouts(long_run, FPS)

    assert len(bouts) >= 8
    for start, end in bouts:
        assert (end - start) / FPS <= seg.bout_max_sec + 1e-6
    assert sum(end - start for start, end in bouts) == pytest.approx(23 * FPS, abs=FPS * 0.1)


def test_capping_does_not_leave_slivers(seg):
    """A remainder shorter than one call is dropped, not kept as a bout."""
    just_over = [(0, int(seg.bout_max_sec * FPS) + 2)]
    for start, end in seg.bouts(just_over, FPS):
        assert (end - start) / FPS >= seg.unit_min_sec
