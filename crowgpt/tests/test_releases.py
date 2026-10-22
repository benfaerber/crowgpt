import pytest

from crowgpt import releases


def test_both_releases_load():
    names = [r.name for r in releases.all_releases()]
    assert names == ["crowgpt1", "crowgpt2"]


def test_crowgpt1_is_the_frozen_decoder_recipe():
    r = releases.load("crowgpt1")
    assert r.model == "model-mono-v2"
    assert r.decoder_state is None
    assert r.sampling == {"temperature": 1.0, "top_k": 200, "max_frames": 225}


def test_crowgpt2_is_the_full_recipe():
    r = releases.load("crowgpt2")
    assert r.model == "model-longctx"
    assert r.decoder_state == "finetuned"
    assert r.sampling == {"temperature": 1.1, "top_k": 200, "max_frames": 460}


def test_release_checkpoints_exist():
    for r in releases.all_releases():
        assert r.checkpoint.is_file(), r.checkpoint


def test_unknown_release_names_the_known_ones():
    with pytest.raises(KeyError, match="crowgpt1.*crowgpt2"):
        releases.load("crowgpt3")
