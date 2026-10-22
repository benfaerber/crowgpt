"""Every shipped call-type head loads, and a mismatched one refuses to.

Nothing in this repo tested `analyzer/` before. That gap has a specific cost:
`HEADS = HeadRegistry()` runs at import, so a head the analyzer cannot use is
discovered by the inference worker, one failed capture at a time, in a
truncated sklearn message inside `analysis_jobs.error`.

Runs in the BirdNET venv, which is where the analyzer itself runs:

    pipelines/representation/.venv-birdnet/bin/python -m pytest analyzer/tests -q

No audio and no BirdNET model — these are joblib and numpy only, so they are
fast enough to run on every change to the pooling definition.
"""

from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import pooling  # noqa: E402
from analyzer.birdnet import HeadMismatch, _check_bundle, head_width  # noqa: E402

MODELS = REPO / "pipelines" / "training" / "models"


def shipped_heads():
    return sorted(MODELS.glob("*/calltype_clf.joblib"))


@pytest.fixture(scope="module")
def bundles():
    return {p: joblib.load(p) for p in shipped_heads()}


def test_there_are_heads_to_check():
    """A green run over an empty glob would be worse than no test at all."""
    assert shipped_heads(), f"no call-type heads under {MODELS}"


def test_every_shipped_head_matches_the_pooled_feature(bundles):
    for path, bundle in bundles.items():
        assert _check_bundle(bundle, path) == pooling.POOLED_DIM, path


def test_every_shipped_head_records_its_provenance(bundles):
    """`feature` is required since 2026-08-09; a bundle without it is refused.

    The four heads that predated the metadata were stamped once their width
    proved the space, so absence now means an unknown head, not an old one.
    """
    for path, bundle in bundles.items():
        assert bundle.get("feature") == pooling.FEATURE, path


def test_width_is_recoverable_without_the_dim_key():
    """The width check falls back to the pipeline's own n_features_in_."""
    assert head_width(_head(pooling.POOLED_DIM)) == pooling.POOLED_DIM


def _head(dim, feature=None):
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=50))
    rng = np.random.default_rng(0)
    model.fit(rng.normal(size=(20, dim)), ["a"] * 10 + ["b"] * 10)
    bundle = {"model": model, "classes": ["a", "b"]}
    if feature:
        bundle["feature"] = feature
    return bundle


def test_a_wider_head_is_refused():
    """The failure a backbone swap would otherwise produce 400 captures late."""
    with pytest.raises(HeadMismatch, match="4608"):
        _check_bundle(_head(4608, feature=pooling.FEATURE), "perch-head.joblib")


def test_a_head_with_no_recorded_feature_is_refused():
    """Absence is not a legacy head any more — it is unknown provenance."""
    with pytest.raises(HeadMismatch, match="does not say"):
        _check_bundle(_head(pooling.POOLED_DIM), "anonymous.joblib")


def test_a_head_from_another_backbone_is_refused_even_at_the_right_width():
    """Same width, different meaning — the silent case, and the dangerous one."""
    bundle = _head(pooling.POOLED_DIM, feature="perch_pooled_mean_std_max")
    with pytest.raises(HeadMismatch, match="perch_pooled_mean_std_max"):
        _check_bundle(bundle, "impostor.joblib")


def test_a_matching_head_passes():
    assert _check_bundle(_head(pooling.POOLED_DIM, feature=pooling.FEATURE),
                         "fine.joblib") == pooling.POOLED_DIM
