"""A runner-up call type gets located inside the region that swallowed it.

Capture 104 is the case these are written from: an 18-second `begging` region
that also holds a caw, which the one-vs-rest head reports as `call` 0.998 and
which nothing could place. `SpeciesHead.localise` slides a shorter span across
the region's windows and says where each alternate peaks.

No BirdNET and no audio — a stub classifier over synthetic embeddings, so these
run in a second and on every change to the pooling definition:

    pipelines/representation/.venv-birdnet/bin/python -m pytest analyzer/tests -q
"""

from pathlib import Path
import sys

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines" / "training"))

import pooling  # noqa: E402
from analyzer.birdnet import LOCALISE_WINDOWS, SpeciesHead  # noqa: E402


class StubClassifier:
    """Says `call` wherever the embedding is hot, `begging` everywhere else.

    Reads only the mean block, so it is indifferent to the std/max degeneracy
    that makes a one-window pool untrustworthy — that is deliberate. These tests
    are about the sliding and the reporting, not about the feature.
    """

    def __init__(self, classes):
        self.classes = classes

    def predict_proba(self, X):
        mean_block = X[:, :pooling.SEGMENT_DIM].mean(axis=1)
        call = np.clip(mean_block, 0.0, 1.0)
        return np.column_stack([1.0 - call, call])


def head(classes=("begging", "call")):
    h = SpeciesHead.__new__(SpeciesHead)          # no joblib, no model file
    h.classes = list(classes)
    h.classifier = StubClassifier(list(classes))
    h.multi_label = True
    return h


def windows(hot_at, n=6):
    """n contiguous 3s windows; `hot_at` indices carry the caw."""
    out = []
    for i in range(n):
        value = 0.9 if i in hot_at else 0.0
        out.append({"start": float(i * 3), "end": float(i * 3 + 3),
                    "emb": np.full(pooling.SEGMENT_DIM, value)})
    return out


def test_it_finds_the_caw_at_the_end_of_the_region():
    """Capture 104's shape: a long beg with the caw in its last windows."""
    found = head().localise(windows(hot_at={4, 5}), ["call"])
    assert "call" in found
    assert found["call"]["end"] == 18.0
    assert found["call"]["start"] >= 6.0     # not the whole region
    assert found["call"]["peak"] > 0.5


def test_it_finds_the_caw_at_the_start_too():
    found = head().localise(windows(hot_at={0, 1}), ["call"])
    assert found["call"]["start"] == 0.0
    assert found["call"]["end"] <= 12.0


def test_the_span_is_narrower_than_the_region():
    region = windows(hot_at={6, 7}, n=10)
    found = head().localise(region, ["call"])
    span = found["call"]["end"] - found["call"]["start"]
    assert span >= LOCALISE_WINDOWS * 3
    assert span < region[-1]["end"] - region[0]["start"]


def test_near_tied_neighbours_are_folded_into_one_span():
    """Adjacent slides overlap, so the argmax alone would be over-precise."""
    region = windows(hot_at=set(), n=8)
    for i in (3, 4, 5):
        region[i]["emb"] = np.full(pooling.SEGMENT_DIM, 0.9)
    found = head().localise(region, ["call"])
    # Several sub-spans sit within tolerance of the peak, so the reported span
    # is wider than one slide and still short of the whole region.
    assert found["call"]["end"] - found["call"]["start"] > LOCALISE_WINDOWS * 3
    assert found["call"]["start"] > 0.0


def test_a_lone_peak_is_not_widened():
    """Folding only happens when the neighbours actually agree."""
    region = windows(hot_at=set(), n=8)
    region[3]["emb"] = np.full(pooling.SEGMENT_DIM, 0.95)
    found = head().localise(region, ["call"])
    assert found["call"]["end"] - found["call"]["start"] <= LOCALISE_WINDOWS * 3 + 3


def test_a_region_too_short_to_slide_is_not_localised():
    """Better to say nothing than to hand back a span equal to the region."""
    assert head().localise(windows(hot_at={0}, n=LOCALISE_WINDOWS), ["call"]) == {}
    assert head().localise(windows(hot_at={0}, n=1), ["call"]) == {}


def test_it_localises_only_what_it_was_asked_for():
    found = head().localise(windows(hot_at={4, 5}), ["call"])
    assert set(found) == {"call"}


def test_an_unknown_class_is_skipped_rather_than_raising():
    found = head().localise(windows(hot_at={4, 5}), ["call", "no such class"])
    assert set(found) == {"call"}


def test_the_peak_is_the_best_sub_span_not_the_first():
    """Two hot patches: the reported one must be the stronger."""
    region = windows(hot_at=set(), n=8)
    for i in (1,):
        region[i]["emb"] = np.full(pooling.SEGMENT_DIM, 0.4)
    for i in (5, 6):
        region[i]["emb"] = np.full(pooling.SEGMENT_DIM, 0.95)
    found = head().localise(region, ["call"])
    assert found["call"]["start"] >= 9.0


def test_predict_still_scores_the_whole_region():
    """Localisation must not change the headline answer — that is the contract."""
    h = head()
    region = windows(hot_at={4, 5})
    top, conf, alternates = h.predict([w["emb"] for w in region])
    whole = h.probabilities([w["emb"] for w in region])
    assert conf == pytest.approx(round(max(whole.values()), 3))
    assert top == max(whole, key=whole.get)
