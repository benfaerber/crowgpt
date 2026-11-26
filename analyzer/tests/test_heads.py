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
import sys

import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import pooling  # noqa: E402
from analyzer.birdnet import HeadMismatch, HeadRegistry, _check_bundle, head_width  # noqa: E402

MODELS = REPO / "pipelines" / "training" / "models"


def shipped_heads():
    return sorted(MODELS.glob("*/calltype_clf.joblib"))


@pytest.fixture(scope="module")
def bundles():
    return {p: joblib.load(p) for p in shipped_heads()}


def test_every_shipped_head_answers_to_birdnets_name_for_it():
    """BirdNET says "Large-billed Crow"; the folder says large-billed-crow.

    A head whose name never matches a detection is never used, and nothing
    else would notice: the calls just come back species-only.
    """
    registry = HeadRegistry()
    birdnet_names = {
        "american-crow": "American Crow",
        "carrion-crow": "Carrion Crow",
        "common-raven": "Common Raven",
        "hooded-crow": "Hooded Crow",
        "large-billed-crow": "Large-billed Crow",
        "rook": "Rook",
    }
    for path in shipped_heads():
        slug = path.parent.name
        assert slug in birdnet_names, f"add BirdNET's common name for {slug}"
        assert registry.for_species(birdnet_names[slug]) is not None, slug


def test_there_are_heads_to_check():
    """A green run over an empty glob would be worse than no test at all."""
    assert shipped_heads(), f"no call-type heads under {MODELS}"


def test_every_shipped_head_matches_its_declared_birdnet_feature(bundles):
    for path, bundle in bundles.items():
        feature = bundle.get("feature")
        assert feature in pooling.FEATURES, path
        expected_dim, _ = pooling.FEATURES[feature]
        assert _check_bundle(bundle, path) == expected_dim, path


def test_american_crow_uses_window_mean_and_emits_rattle_not_call(bundles):
    """Experiment 0012 + 0121: American Crow runs on 1024-d window-mean and
    names crow-tools' rattle detector `rattle` rather than `call`."""
    crow_path = MODELS / "american-crow" / "calltype_clf.joblib"
    bundle = bundles[crow_path]
    assert bundle.get("feature") == pooling.MEAN_FEATURE
    assert _check_bundle(bundle, crow_path) == pooling.MEAN_DIM
    classes = set(bundle["classes"])
    assert "rattle" in classes
    assert "call" not in classes
    assert "none" not in classes

    registry = HeadRegistry()
    head = registry.for_species("American Crow")
    probs = head.probabilities([np.zeros(pooling.SEGMENT_DIM), np.ones(pooling.SEGMENT_DIM)])
    assert set(probs) == classes


def test_width_is_recoverable_without_the_dim_key():
    """The width check falls back to the pipeline's own n_features_in_."""
    assert head_width(_head(pooling.POOLED_DIM)) == pooling.POOLED_DIM
    assert head_width(_head(pooling.MEAN_DIM)) == pooling.MEAN_DIM


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


def test_a_3072_head_claiming_window_mean_is_refused():
    with pytest.raises(HeadMismatch, match="3072"):
        _check_bundle(_head(pooling.POOLED_DIM, feature=pooling.MEAN_FEATURE), "mismatch.joblib")


def test_a_head_with_no_recorded_feature_is_refused():
    """Absence is not a legacy head any more — it is unknown provenance."""
    with pytest.raises(HeadMismatch, match="does not say"):
        _check_bundle(_head(pooling.POOLED_DIM), "anonymous.joblib")


def test_a_head_from_another_backbone_is_refused_even_at_the_right_width():
    """Same width, different meaning — the silent case, and the dangerous one."""
    bundle = _head(pooling.POOLED_DIM, feature="perch_pooled_mean_std_max")
    with pytest.raises(HeadMismatch, match="perch_pooled_mean_std_max"):
        _check_bundle(bundle, "impostor.joblib")


def test_matching_heads_pass():
    assert _check_bundle(_head(pooling.POOLED_DIM, feature=pooling.FEATURE),
                         "pooled.joblib") == pooling.POOLED_DIM
    assert _check_bundle(_head(pooling.MEAN_DIM, feature=pooling.MEAN_FEATURE),
                         "mean.joblib") == pooling.MEAN_DIM
