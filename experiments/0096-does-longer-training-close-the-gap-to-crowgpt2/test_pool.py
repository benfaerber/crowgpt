from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "crowgpt/src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pool import Schedule


def schedule():
    arms = {name: {"rows": [{"file": f"{name}-{i}.wav", "seed": 96000 + i, "seconds": 2.0}
                            for i in range(44)]} for name in ["candidate", "crowgpt2"]}
    return Schedule(arms, [f"anchor-{i}.wav" for i in range(48)],
                    [f"real-{i}.wav" for i in range(8)]).trials()


def test_three_doses_of_eighteen():
    trials = schedule()
    assert Counter(t["block"] for t in trials) == {0: 18, 1: 18, 2: 18}
    assert Counter(t["kind"] for t in trials) == {"compare": 40, "catch": 8, "repeat": 6}


def test_fresh_trials_share_no_clip():
    fresh = [t for t in schedule() if t["kind"] != "repeat"]
    clips = [t[key] for t in fresh for key in ("first_clip", "second_clip", "anchor_clip")]
    assert len(clips) == len(set(clips))


def test_sides_are_balanced_within_a_dose():
    trials = schedule()
    for block in range(3):
        compares = [t for t in trials if t["block"] == block and t["kind"] == "compare"]
        first = sum(t["first_arm"] == "candidate" for t in compares)
        assert abs(2 * first - len(compares)) <= 1
        catches = [t for t in trials if t["block"] == block and t["kind"] == "catch"]
        assert sum(t["first_arm"] == "real" for t in catches) == len(catches) // 2


def test_a_repeat_is_an_earlier_pair_with_the_sides_swapped():
    trials = schedule()
    originals = {t["facts"]["pair"]: t for t in trials if t["kind"] == "compare"}
    repeats = [t for t in trials if t["kind"] == "repeat"]
    assert len({t["facts"]["pair"] for t in repeats}) == 6
    for repeat in repeats:
        original = originals[repeat["facts"]["pair"]]
        assert original["block"] < repeat["block"]
        assert (repeat["first_clip"], repeat["second_clip"]) == (original["second_clip"], original["first_clip"])
        assert repeat["anchor_clip"] == original["anchor_clip"]
