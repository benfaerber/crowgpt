"""The bout ledger, which is the part that was wrong on the first build.

`held_out_reals` originally took an `offset` constant. 0053 drew 132 bouts at
offset 0 and 121 of them had already been played to Ben, most through ABX
sittings that reveal the answer every trial — so its catch trials could have been
passed by recognition rather than by ear. 0039's docstring had already named the
bug class: a constant meaning "however many the last experiment happened to take"
is correct exactly once.

These pin the replacement: spending is read from disk, both ledgers count, and a
pool claims its bouts at build time rather than when it is finally graded.
"""

import json

import numpy as np
import pytest

from crowgpt.pool import (BlockedPool, ClipWriter, claim_bouts, spent_bouts,
                          spent_recordings)


@pytest.fixture
def ledgers(tmp_path):
    sessions = tmp_path / "listening"
    pools = tmp_path / "listening-pools"
    (sessions / "abx-0039").mkdir(parents=True)
    (pools / "some-pool").mkdir(parents=True)
    return sessions, pools


def write_session(sessions, name, bouts):
    (sessions / name).mkdir(parents=True, exist_ok=True)
    (sessions / name / f"session-{name}.json").write_text(json.dumps(
        {"kind": "abx", "trials": [{"bout": b} for b in bouts]}))


class TestSpentBouts:
    def test_it_reads_bouts_out_of_saved_sittings(self, ledgers):
        sessions, pools = ledgers
        write_session(sessions, "abx-0039", [1, 2, 3])
        assert spent_bouts(sessions, pools) == {1, 2, 3}

    def test_a_pool_claim_counts_before_anything_is_graded(self, ledgers):
        # The failure this prevents: a pool sits registered and unheard for two
        # weeks, a second pool is built, and both hand Ben the same references.
        sessions, pools = ledgers
        claim_bouts(pools / "some-pool", "some-pool", [7, 8])
        assert spent_bouts(sessions, pools) == {7, 8}

    def test_both_ledgers_are_unioned(self, ledgers):
        sessions, pools = ledgers
        write_session(sessions, "abx-0039", [1, 2])
        claim_bouts(pools / "some-pool", "some-pool", [2, 9])
        assert spent_bouts(sessions, pools) == {1, 2, 9}

    def test_a_half_written_file_does_not_stop_the_build(self, ledgers):
        sessions, pools = ledgers
        write_session(sessions, "abx-0039", [4])
        (sessions / "aborted").mkdir()
        (sessions / "aborted" / "session-aborted.json").write_text('{"trials": [')
        assert spent_bouts(sessions, pools) == {4}

    def test_a_trial_with_no_bout_is_skipped(self, ledgers):
        # Pairwise sittings record arms and no bout id, so most of the saved
        # corpus of trials contributes nothing here and must not crash it.
        sessions, pools = ledgers
        (sessions / "pairwise").mkdir()
        (sessions / "pairwise" / "session-pairwise.json").write_text(json.dumps(
            {"kind": "pairwise", "trials": [{"winner_arm": "a"}, {"bout": 5}]}))
        assert spent_bouts(sessions, pools) == {5}

    def test_no_ledgers_at_all_is_an_empty_set_not_an_error(self, tmp_path):
        assert spent_bouts(tmp_path / "nope", tmp_path / "also-nope") == set()


class TestClaimBouts:
    def test_the_claim_is_sorted_and_reloadable(self, tmp_path):
        path = claim_bouts(tmp_path, "p", [9, 3, 3, 5], recordings=["r2", "r1"])
        assert json.loads(path.read_text()) == {
            "pool": "p", "bouts": [3, 3, 5, 9], "recordings": ["r1", "r2"]}


class TestSpentRecordings:
    """The durable key: recordings survive a re-extract, indices do not."""

    def test_a_pool_claim_retires_its_recordings(self, ledgers):
        sessions, pools = ledgers
        claim_bouts(pools / "some-pool", "some-pool", [7], recordings=["164831"])
        assert spent_recordings(sessions, pools) == {"164831"}

    def test_the_migration_sidecar_is_read_from_either_root(self, ledgers):
        # The 822 pre-migration session records only exist as recordings via
        # the sidecar the migration wrote while the index join still existed.
        sessions, pools = ledgers
        (sessions / "spent-recordings.json").write_text(json.dumps(
            {"recordings": ["a", "b"]}))
        claim_bouts(pools / "some-pool", "some-pool", [], recordings=["c"])
        assert spent_recordings(sessions, pools) == {"a", "b", "c"}

    def test_an_index_only_claim_contributes_nothing_durable(self, ledgers):
        # Pre-migration bouts.json shape: indices, no recordings. It must not
        # crash, and it cannot be resolved here — the migration owns the join.
        sessions, pools = ledgers
        (pools / "some-pool" / "bouts.json").write_text(json.dumps(
            {"pool": "some-pool", "bouts": [1, 2]}))
        assert spent_recordings(sessions, pools) == set()

    def test_malformed_files_are_skipped(self, ledgers):
        sessions, pools = ledgers
        (sessions / "spent-recordings.json").write_text('{"recordings": [')
        claim_bouts(pools / "some-pool", "some-pool", [], recordings=["ok"])
        assert spent_recordings(sessions, pools) == {"ok"}


class TestClipWriter:
    def test_a_short_clip_is_refused_rather_than_dropped(self, tmp_path):
        # 0044: filtering short clips out of one arm and not the other is what
        # biased six experiments, so this raises and the caller over-draws.
        writer = ClipWriter(tmp_path)
        with pytest.raises(ValueError, match="under 1.0s"):
            writer.add("tiny", np.zeros(12000, dtype=np.float32))

    def test_a_gradeable_clip_is_written_and_measured(self, tmp_path):
        writer = ClipWriter(tmp_path)
        name = writer.add("fine", np.zeros(48000, dtype=np.float32))
        assert (tmp_path / name).exists()
        assert writer.seconds[name] == pytest.approx(2.0)


class TestBlockedPool:
    def build(self, blocks=3):
        pairs = [("a", "b", 2), ("a", "c", 2)]
        builder = BlockedPool(pairs, catch_per_block=1, seed=0)
        per_arm = {"a": blocks * 4, "b": blocks * 2, "c": blocks * 2}
        per_arm["a"] += blocks  # the catch arm draws one more per block
        clips = {arm: [f"{arm}-{i}" for i in range(n)] for arm, n in per_arm.items()}
        anchors = [f"anchor-{i}" for i in range(blocks * builder.dose_size)]
        catch = [f"real-{i}" for i in range(blocks)]
        return builder, builder.build(blocks, clips, anchors, catch)

    def test_every_block_holds_the_same_mixture(self):
        builder, trials = self.build()
        by_block = {}
        for trial in trials:
            key = tuple(sorted((trial["first_arm"], trial["second_arm"])))
            by_block.setdefault(trial["block"], []).append(key)
        counts = {b: sorted(v) for b, v in by_block.items()}
        assert len(set(map(str, counts.values()))) == 1, counts

    def test_a_dose_is_the_block_size(self):
        builder, trials = self.build()
        assert builder.dose_size == 5
        assert len(trials) == 15

    def test_no_generated_clip_is_used_twice(self):
        _, trials = self.build()
        generated = [c for t in trials for c in (t["first_clip"], t["second_clip"])
                     if not c.startswith("real-")]
        assert len(generated) == len(set(generated))

    def test_every_anchor_is_a_different_bout(self):
        _, trials = self.build()
        anchors = [t["anchor_clip"] for t in trials]
        assert len(anchors) == len(set(anchors))

    def test_running_out_of_clips_raises_rather_than_recycling(self):
        builder = BlockedPool([("a", "b", 2)], catch_per_block=0, seed=0)
        with pytest.raises(ValueError, match="ran out of"):
            builder.build(2, {"a": ["a-0"], "b": ["b-0", "b-1"]},
                          [f"anchor-{i}" for i in range(4)], [])

    def test_presentation_order_is_randomised_within_a_trial(self):
        _, trials = self.build(blocks=12)
        firsts = {t["first_arm"] for t in trials if
                  tuple(sorted((t["first_arm"], t["second_arm"]))) == ("a", "b")}
        assert firsts == {"a", "b"}
