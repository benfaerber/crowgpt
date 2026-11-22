"""Tests for analyzer.threat: shipped threat head provenance, DSP features, and region prediction."""

from pathlib import Path
import sys

import joblib
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import pooling  # noqa: E402
from analyzer.threat import (  # noqa: E402
    AUX_DIM,
    THREAT_CLASSES,
    THREAT_FEATURE,
    ThreatMismatch,
    ThreatRegistry,
    check_threat_bundle,
    extract_prosody,
    extract_speed,
)

MODELS = REPO / "pipelines" / "training" / "models"


def test_shipped_american_crow_threat_head_loads():
    reg = ThreatRegistry(MODELS)
    head = reg.for_species("American Crow")
    assert head is not None
    assert tuple(head.classes) == THREAT_CLASSES
    assert reg.for_species("Common Raven") is None


def test_mismatched_threat_bundle_refused():
    with pytest.raises(ThreatMismatch):
        check_threat_bundle({"feature": "wrong", "bn_dim": pooling.POOLED_DIM, "aux_dim": AUX_DIM}, "bad.joblib")
    with pytest.raises(ThreatMismatch):
        check_threat_bundle({"feature": THREAT_FEATURE, "bn_dim": 1024, "aux_dim": AUX_DIM}, "bad.joblib")


def test_extract_prosody_and_speed_on_synthetic_caws():
    sr = 22050
    t = np.linspace(0, 6.0, int(sr * 6.0), endpoint=False, dtype=np.float32)
    # 3 Hz pulsed 1500 Hz tone mimicking fast caw bursts
    env = (np.sin(2 * np.pi * 3.0 * t) > 0.3).astype(np.float32)
    y = env * np.sin(2 * np.pi * 1500.0 * t).astype(np.float32) * 0.5
    pros = extract_prosody(y, sr, [(0.0, 6.0)])
    spd = extract_speed(y, sr, [(0.0, 6.0)])
    assert pros.shape == (41,)
    assert spd.shape == (11,)
    assert np.isfinite(pros).all() and np.isfinite(spd).all()
    # Peak rate should be close to 3.0 caws/s
    assert 2.0 <= spd[0] <= 4.0


def test_predict_region_returns_calibrated_payload():
    reg = ThreatRegistry(MODELS)
    head = reg.for_species("American Crow")
    rng = np.random.default_rng(0)
    embs = [rng.normal(size=1024).astype(np.float32) for _ in range(3)]
    aux = np.zeros(AUX_DIM, dtype=np.float32)
    out = head.predict_region(embs, aux=aux)
    assert out["label"] in THREAT_CLASSES
    assert set(out["probs"].keys()) == set(THREAT_CLASSES)
    assert set(out["lift"].keys()) == set(THREAT_CLASSES)
    assert all(0.0 <= p <= 1.0 for p in out["probs"].values())
    assert out["model"].startswith("threat@")
