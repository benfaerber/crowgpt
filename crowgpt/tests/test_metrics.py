"""The instrument, tested on distributions whose answer is known.

Built because the judge gave two readings of one model 18 points apart, so
every number this project has quoted about generation quality has error bars
nobody computed. These are the checks that the replacement can tell things
apart, and — as importantly — that it declines to when it cannot.
"""

import numpy as np
import pytest

from crowgpt.metrics import bootstrap_ci, frechet_distance, paired_difference


def gaussian(n, dim=32, shift=0.0, scale=1.0, seed=0):
    return np.random.default_rng(seed).normal(shift, scale, (n, dim))


class TestFrechetDistance:
    def test_a_set_against_itself_is_zero(self):
        a = gaussian(200)
        assert frechet_distance(a, a) == pytest.approx(0.0, abs=1e-6)

    def test_two_draws_from_one_distribution_are_close(self):
        assert frechet_distance(gaussian(400, seed=1), gaussian(400, seed=2)) < 5.0

    def test_a_shifted_distribution_is_far(self):
        near = frechet_distance(gaussian(400, seed=1), gaussian(400, seed=2))
        far = frechet_distance(gaussian(400, seed=1), gaussian(400, shift=1.5, seed=3))
        assert far > near * 10

    def test_it_notices_collapse_that_a_detection_rate_would_not(self):
        """A model emitting one perfect caw over and over.

        Every clip would pass a detector; the distribution is still wrong, and
        this is the whole reason for preferring a distributional metric.
        """
        real = gaussian(400, seed=1)
        collapsed = np.repeat(real[:1], 400, axis=0) + gaussian(400, scale=0.01, seed=4)

        assert frechet_distance(real, collapsed) > frechet_distance(real, gaussian(400, seed=2)) * 10

    def test_it_refuses_a_single_sample(self):
        with pytest.raises(ValueError, match="at least two"):
            frechet_distance(gaussian(1), gaussian(400))


class TestErrorBars:
    def test_the_interval_brackets_the_truth(self):
        values = np.random.default_rng(0).normal(0.5, 0.2, 400)
        low, high = bootstrap_ci(values)
        assert low < 0.5 < high

    def test_fewer_samples_give_a_wider_interval(self):
        rng = np.random.default_rng(0)
        wide = bootstrap_ci(rng.normal(0.5, 0.2, 20))
        tight = bootstrap_ci(rng.normal(0.5, 0.2, 2000))
        assert (wide[1] - wide[0]) > (tight[1] - tight[0]) * 3


class TestPairedComparison:
    def test_a_real_difference_is_called(self):
        rng = np.random.default_rng(0)
        conditions = rng.normal(0, 1, 200)          # the shared nuisance
        a = conditions + rng.normal(0.5, 0.2, 200)  # model A is genuinely better
        b = conditions + rng.normal(0.0, 0.2, 200)

        result = paired_difference(a, b)
        assert result["significant"] and result["mean_difference"] > 0

    def test_no_difference_is_not_called(self):
        rng = np.random.default_rng(0)
        conditions = rng.normal(0, 1, 200)
        a = conditions + rng.normal(0.0, 0.2, 200)
        b = conditions + rng.normal(0.0, 0.2, 200)

        assert not paired_difference(a, b)["significant"]

    def test_pairing_beats_not_pairing(self):
        """The point of matched conditions: the nuisance variance cancels.

        Unpaired, a large condition effect buries a small model effect. This is
        why two judgements of the SAME model landed 18 points apart.
        """
        rng = np.random.default_rng(0)
        conditions = rng.normal(0, 3, 200)          # ambience, species, seed
        a = conditions + rng.normal(0.4, 0.2, 200)
        b = conditions + rng.normal(0.0, 0.2, 200)

        paired = paired_difference(a, b)
        unpaired_spread = np.std(a) + np.std(b)

        assert paired["significant"]
        assert (paired["ci"][1] - paired["ci"][0]) < unpaired_spread

    def test_mismatched_conditions_are_refused(self):
        with pytest.raises(ValueError, match="same conditions"):
            paired_difference(np.zeros(10), np.zeros(9))
