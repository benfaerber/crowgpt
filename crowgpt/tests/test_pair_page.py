"""PairPage, and the three ways a forced choice quietly stops being one.

The page exists because absolute rating turned out to be contrast-sensitive
(0038: identical weights, 0.21 then 0.54). Its value depends entirely on three
properties, each of which fails silently:

  - the side an arm lands on must be random, or a preference for the left button
    reads as a preference for a model;
  - the answer must resolve to the ARM, not the side, or every flipped trial is
    scored backwards and the result comes out mirrored but plausible;
  - nothing identifying an arm may appear before the answer.

None of these throws when broken, and all three produce a page that looks right.
"""

import json
import re
from collections import Counter

import numpy as np
import pytest

from crowgpt.demo import PairPage

SR = 24000


def _clip(arm, seed):
    rng = np.random.default_rng(seed)
    return {"audio": rng.normal(0, 0.1, SR).astype(np.float32), "sr": SR, "arm": arm}


@pytest.fixture
def pairs():
    return [{"a": _clip("model_a", i), "b": _clip("model_b", 100 + i)} for i in range(40)]


def _trials(page):
    return page.trials


def test_sides_are_randomised(pairs):
    """If every A landed left, left-button bias would be model bias."""
    flips = [t["hidden"]["flipped"] for t in _trials(PairPage(pairs, {}, seed=0))]
    assert 0 < sum(flips) < len(flips), "sides are not being shuffled at all"
    # Loose bound: 40 fair coins land outside 10..30 about 0.2% of the time.
    assert 10 <= sum(flips) <= 30


def test_the_arm_follows_the_side_it_was_placed_on(pairs):
    """The mirror bug: scoring the side instead of the arm.

    Every trial must report which arm is on which side, and a flipped trial must
    say b is on the left. Nothing else lets the analysis recover the winner.
    """
    for trial in _trials(PairPage(pairs, {}, seed=0)):
        hidden = trial["hidden"]
        if hidden["flipped"]:
            assert hidden["left_arm"] == "model_b" and hidden["right_arm"] == "model_a"
        else:
            assert hidden["left_arm"] == "model_a" and hidden["right_arm"] == "model_b"


def test_both_arms_appear_on_both_sides_across_the_sitting(pairs):
    """The property that makes side bias cancel rather than accumulate."""
    trials = _trials(PairPage(pairs, {}, seed=0))
    left = {t["hidden"]["left_arm"] for t in trials}
    right = {t["hidden"]["right_arm"] for t in trials}
    assert left == right == {"model_a", "model_b"}


def test_catch_trials_are_marked(pairs):
    marked = PairPage(pairs[:5] + [{"a": _clip("real", 1), "b": _clip("model_a", 2),
                                    "catch": True}], {}, seed=0)
    assert sum(t["hidden"]["catch"] for t in _trials(marked)) == 1


def test_the_rendered_page_does_not_leak_the_arm_before_the_answer(pairs):
    """Arm names may exist in the payload; they must not be visible markup.

    The waveform is already hidden until answered. A label rendered into the
    row would give the same thing away in plain text.
    """
    html = PairPage(pairs, {"Question": "which is less robotic"}, seed=0).render()
    body = html[: html.index("<script>")]
    assert "model_a" not in body and "model_b" not in body


def test_every_trial_carries_two_distinct_clips(pairs):
    for trial in _trials(PairPage(pairs, {}, seed=0)):
        assert trial["left"]["audio"] != trial["right"]["audio"]
        assert trial["left"]["audio"].startswith("data:audio/wav;base64,")


def test_the_page_is_deterministic_for_a_seed(pairs):
    first = [t["hidden"]["flipped"] for t in _trials(PairPage(pairs, {}, seed=7))]
    second = [t["hidden"]["flipped"] for t in _trials(PairPage(pairs, {}, seed=7))]
    assert first == second


def test_trials_json_is_embedded_and_parses(pairs):
    html = PairPage(pairs[:3], {}, seed=0).render()
    blob = re.search(r"const TRIALS = (\[.*?\]);\n", html, re.S).group(1)
    assert len(json.loads(blob)) == 3


def test_sides_are_balanced_within_each_pairing(pairs):
    """0041 measured a 65% left bias — as large as the effect under test.

    Random flipping only cancels that in expectation, and over 32 trials it put
    one arm left 14 times and right 18. Balancing makes the cancellation exact.
    """
    trials = PairPage(pairs, {}, seed=3).trials
    flips = [t["hidden"]["flipped"] for t in trials]
    assert abs(sum(flips) - len(flips) / 2) <= 0.5, "flips are not evenly split"
    left = [t["hidden"]["left_arm"] for t in trials]
    assert abs(left.count("model_a") - left.count("model_b")) <= 1


def test_each_pairing_is_balanced_separately():
    """A sitting mixing comparisons must balance each one, not just the total.

    Balancing only in aggregate lets one pairing sit left-heavy while another
    compensates, which cancels nothing for either.
    """
    mixed = ([{"a": _clip("a", i), "b": _clip("b", i)} for i in range(10)]
             + [{"a": _clip("a", 50 + i), "b": _clip("c", i)} for i in range(6)])
    trials = PairPage(mixed, {}, seed=1).trials
    for arms in ({"a", "b"}, {"a", "c"}):
        rows = [t for t in trials
                if {t["hidden"]["left_arm"], t["hidden"]["right_arm"]} == arms]
        flips = [t["hidden"]["flipped"] for t in rows]
        assert abs(sum(flips) - len(flips) / 2) <= 0.5, f"{arms} not balanced"


def test_each_side_records_its_duration():
    """0044: "too short clips instantly loose. 0.1 second is always worse."

    A pairing that puts a fragment against a full bout is answered on length,
    not timbre. Without the duration in the payload that cannot be detected
    after the fact — the same hole the side bias would have fallen into had the
    side not been recorded.
    """
    short = {"audio": np.zeros(2400, dtype=np.float32), "sr": SR, "arm": "short"}
    long = {"audio": np.zeros(int(2.5 * SR), dtype=np.float32), "sr": SR, "arm": "long"}
    # min_seconds=0 on purpose: this test's whole subject is a fragment, and the
    # gradeability guard added alongside it would otherwise refuse the fixture.
    trial = PairPage([{"a": short, "b": long}], {}, seed=0, min_seconds=0).trials[0]
    seconds = {trial["hidden"]["left_arm"]: trial["hidden"]["left_seconds"],
               trial["hidden"]["right_arm"]: trial["hidden"]["right_seconds"]}
    assert seconds["short"] == pytest.approx(0.1, abs=0.02)
    assert seconds["long"] == pytest.approx(2.5, abs=0.02)


def test_side_and_play_order_are_balanced_as_a_2x2(pairs):
    """Ben's fix: play a random side first, so the two biases separate.

    The left clip used to be heard first every time, which made "left bias" and
    "first-heard bias" the same measurement under two names — balancing which
    ARM sits left cannot tell them apart. Both are balanced independently now,
    so each is estimable from the same sitting.
    """
    trials = PairPage(pairs, {}, seed=0).trials
    cells = Counter((t["hidden"]["flipped"], t["hidden"]["played_first"])
                    for t in trials)
    assert set(cells) == {(False, "left"), (False, "right"),
                          (True, "left"), (True, "right")}
    assert max(cells.values()) - min(cells.values()) <= 1


def test_play_order_is_recorded_for_every_trial(pairs):
    """Unrecorded, the effect is unmeasurable however well it is balanced."""
    for trial in PairPage(pairs, {}, seed=0).trials:
        assert trial["first"] in ("left", "right")
        assert trial["hidden"]["played_first"] == trial["first"]


def test_order_does_not_track_the_side_an_arm_landed_on(pairs):
    """If they correlated, the 2x2 would collapse back to one variable."""
    trials = PairPage(pairs, {}, seed=0).trials
    agree = sum(1 for t in trials
                if (t["hidden"]["played_first"] == "left") == t["hidden"]["flipped"])
    assert abs(agree - len(trials) / 2) <= 1


def test_each_pairing_gets_its_own_2x2():
    mixed = ([{"a": _clip("a", i), "b": _clip("b", i)} for i in range(12)]
             + [{"a": _clip("a", 50 + i), "b": _clip("c", i)} for i in range(8)])
    trials = PairPage(mixed, {}, seed=2).trials
    for arms in ({"a", "b"}, {"a", "c"}):
        rows = [t for t in trials
                if {t["hidden"]["left_arm"], t["hidden"]["right_arm"]} == arms]
        cells = Counter((t["hidden"]["flipped"], t["hidden"]["played_first"])
                        for t in rows)
        assert max(cells.values()) - min(cells.values()) <= 1, f"{arms} unbalanced"


def test_a_short_clip_is_refused():
    """0044: short clips lose on sight, and every sitting before it let them in.

    The rule had been written down since PLAN-TIMBRE and applied only to the real
    bout store, so the arm that actually produces short clips went unfiltered.
    Raising rather than dropping is deliberate: silently discarding would change
    an arm's n without saying so.
    """
    import numpy as np
    import pytest

    from crowgpt.demo import PairPage

    short = {"audio": np.zeros(int(24000 * 0.4), dtype=np.float32), "sr": 24000,
             "arm": "generated"}
    fine = {"audio": np.zeros(int(24000 * 2.0), dtype=np.float32), "sr": 24000,
            "arm": "real"}
    with pytest.raises(ValueError, match="ungradeable"):
        PairPage([{"a": short, "b": fine}], {})
    # And it can be waived deliberately, which is the only way past it.
    assert PairPage([{"a": short, "b": fine}], {}, min_seconds=0).trials
