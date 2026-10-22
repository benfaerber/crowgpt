"""Promoting a model is the only destructive thing the overnight run does.

It deletes whatever the published demo is currently playing, unattended, in the
middle of the night. These are the checks that it never does so for nothing, and
never leaves the live slot empty if the copy fails.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overnight import promote  # noqa: E402


def model_at(path, marker):
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.pt").write_text(marker)
    return path


class TestPromoting:
    def test_the_candidate_becomes_live(self, tmp_path):
        live = model_at(tmp_path / "model", "old")
        candidate = model_at(tmp_path / "model-d384", "new")

        promote(candidate, live)

        assert (live / "model.pt").read_text() == "new"

    def test_the_old_model_is_kept(self, tmp_path):
        """A worse model can win on the metric and lose by ear."""
        live = model_at(tmp_path / "model", "old")
        candidate = model_at(tmp_path / "model-d384", "new")

        backup = promote(candidate, live)

        assert (backup / "model.pt").read_text() == "old"

    def test_an_unreadable_candidate_leaves_the_live_model_alone(self, tmp_path):
        """Delete-then-copy would lose the working model to a typo'd path."""
        live = model_at(tmp_path / "model", "old")
        empty = tmp_path / "model-broken"
        empty.mkdir()

        with pytest.raises(FileNotFoundError):
            promote(empty, live)

        assert (live / "model.pt").read_text() == "old"

    def test_promoting_into_an_empty_slot_works(self, tmp_path):
        """First run: there is no live model to back up."""
        candidate = model_at(tmp_path / "model-d384", "new")

        promote(candidate, tmp_path / "model")

        assert (tmp_path / "model" / "model.pt").read_text() == "new"

    def test_nothing_is_left_staged(self, tmp_path):
        live = model_at(tmp_path / "model", "old")
        candidate = model_at(tmp_path / "model-d384", "new")

        promote(candidate, live)

        assert not (tmp_path / "model-incoming").exists()
