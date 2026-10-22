"""The listening instrument, tested against answers whose truth is known.

The target here is chance, not accuracy, so the checks that matter are the ones
proving it can distinguish "could not tell" from "did not look" — a short
sitting and a shrug must not read as success.
"""

import json

import numpy as np
import pytest

from crowgpt.listen import Checkpoint, Discrimination, ListeningLog, Session


def trials(answers, truths, species=None, start=0):
    return [
        {
            "condition_index": start + i,
            "species": (species or ["american-crow"] * len(answers))[i],
            "truth": truth,
            "answer": answer,
            "correct": answer == truth,
            "decision_ms": 4000,
        }
        for i, (answer, truth) in enumerate(zip(answers, truths))
    ]


def alternating(n):
    return ["generated" if i % 2 else "real" for i in range(n)]


class TestTheVerdict:
    def test_a_listener_who_always_knows_is_caught(self):
        truths = alternating(60)
        result = Discrimination(trials(truths, truths))

        assert result.rate == 1.0
        assert result.ci[0] > 0.5
        assert result.verdict == "can tell"

    def test_a_coin_flip_over_enough_trials_reads_as_chance(self):
        truths = alternating(400)
        rng = np.random.default_rng(0)
        guesses = [rng.choice(["real", "generated"]) for _ in truths]
        result = Discrimination(trials(guesses, truths))

        low, high = result.ci
        assert low < 0.5 < high
        assert result.verdict == "cannot tell"

    def test_a_short_sitting_is_underpowered_not_a_win(self):
        """Twelve trials and a shrug is not evidence the model succeeded."""
        truths = alternating(12)
        rng = np.random.default_rng(1)
        guesses = [rng.choice(["real", "generated"]) for _ in truths]
        result = Discrimination(trials(guesses, truths))

        low, high = result.ci
        assert low < 0.5 < high
        assert result.width > 0.20
        assert result.verdict == "underpowered"

    def test_the_interval_narrows_as_trials_accumulate(self):
        truths = alternating(400)
        rng = np.random.default_rng(2)
        guesses = [rng.choice(["real", "generated"]) for _ in truths]

        short = Discrimination(trials(guesses[:40], truths[:40]))
        long = Discrimination(trials(guesses, truths))
        assert long.width < short.width


class TestBiasThatPercentCorrectHides:
    def test_answering_generated_every_time_scores_chance(self):
        """Rate alone calls this a success. Criterion is what exposes it."""
        truths = alternating(120)
        result = Discrimination(trials(["generated"] * 120, truths))

        assert result.rate == pytest.approx(0.5, abs=0.01)
        assert result.dprime == pytest.approx(0.0, abs=0.1)
        assert result.criterion < -0.5

    def test_an_unbiased_listener_sits_near_zero_criterion(self):
        truths = alternating(200)
        rng = np.random.default_rng(3)
        guesses = [rng.choice(["real", "generated"]) for _ in truths]
        result = Discrimination(trials(guesses, truths))

        assert abs(result.criterion) < 0.3

    def test_perfect_discrimination_has_a_finite_dprime(self):
        """Without the log-linear correction this is infinity."""
        truths = alternating(60)
        result = Discrimination(trials(truths, truths))

        assert np.isfinite(result.dprime)
        assert result.dprime > 2.0


class TestSlicing:
    def test_species_split_keeps_every_trial(self):
        truths = alternating(40)
        names = ["american-crow" if i % 2 else "rook" for i in range(40)]
        result = Discrimination(trials(truths, truths, species=names))

        buckets = result.by_species()
        assert set(buckets) == {"american-crow", "rook"}
        assert sum(b.n for b in buckets.values()) == 40

    def test_pairing_needs_shared_conditions(self):
        truths = alternating(40)
        a = Discrimination(trials(truths, truths))
        b = Discrimination(trials(["real"] * 40, truths))

        difference = a.versus(b)
        assert difference["n_pairs"] == 40
        assert difference["mean_difference"] > 0

    def test_pairing_declines_without_overlap(self):
        truths = alternating(40)
        a = Discrimination(trials(truths, truths, start=0))
        b = Discrimination(trials(truths, truths, start=1000))

        assert a.versus(b) is None


class TestPoolingByFingerprint:
    def _write(self, folder, fingerprint, name, answers, truths):
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "checkpoint": {"fingerprint": fingerprint, "name": name},
            "trials": trials(answers, truths),
        }
        (folder / f"{fingerprint}-{len(list(folder.glob('*.json')))}.json").write_text(
            json.dumps(payload)
        )

    def test_sittings_on_the_same_weights_pool(self, tmp_path):
        truths = alternating(30)
        self._write(tmp_path / "m", "abc123", "model-a", truths, truths)
        self._write(tmp_path / "m", "abc123", "model-a", truths, truths)

        report = ListeningLog(tmp_path).report()
        assert len(report) == 1
        assert report[0]["sessions"] == 2
        assert report[0]["discrimination"].n == 60

    def test_different_weights_never_pool(self, tmp_path):
        truths = alternating(30)
        self._write(tmp_path / "a", "aaa111", "model-a", truths, truths)
        self._write(tmp_path / "b", "bbb222", "model-b", truths, truths)

        assert len(ListeningLog(tmp_path).report()) == 2

    def test_an_empty_log_is_not_an_error(self, tmp_path):
        assert ListeningLog(tmp_path / "nothing").report() == []

    def test_unanswered_trials_are_dropped(self):
        payload = {
            "checkpoint": {"fingerprint": "abc"},
            "trials": [
                {"truth": "real", "answer": "real", "correct": True},
                {"truth": "real", "answer": None},
            ],
        }
        assert len(Session(payload)) == 1


class TestFingerprinting:
    def test_identical_weights_hash_alike(self, tmp_path):
        for name in ("one", "two"):
            folder = tmp_path / name
            folder.mkdir()
            (folder / "model.pt").write_bytes(b"same weights")

        assert (Checkpoint.load(tmp_path / "one").fingerprint
                == Checkpoint.load(tmp_path / "two").fingerprint)

    def test_a_changed_checkpoint_gets_a_new_identity(self, tmp_path):
        """results/model/ is overwritten in place, so the name is not the id."""
        folder = tmp_path / "model"
        folder.mkdir()
        (folder / "model.pt").write_bytes(b"first")
        before = Checkpoint.load(folder).fingerprint
        (folder / "model.pt").write_bytes(b"second")

        assert Checkpoint.load(folder).fingerprint != before

    def test_a_missing_checkpoint_says_so(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Checkpoint.load(tmp_path)
