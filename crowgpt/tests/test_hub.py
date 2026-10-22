"""The export round-trip: what leaves as safetensors + JSON comes back whole."""

import json

import pytest
import torch

from crowgpt import hub, releases
from crowgpt.model import Config, CrowGPT

CONFIG = dict(vocab_size=64, n_codebooks=2, block_size=32, n_layer=1,
              n_head=2, n_embd=8, dropout=0.0, prefix_len=2)
MANIFEST = {"bandwidth": 6.0, "n_codebooks": 2, "codec": "encodec-24khz",
            "vocab_size": 64, "species": ["american-crow"]}


@pytest.fixture
def tiny(tmp_path, monkeypatch):
    model = CrowGPT(Config(**CONFIG))
    results = tmp_path / "results"
    (results / "model-tiny").mkdir(parents=True)
    torch.save({"config": CONFIG, "manifest": MANIFEST,
                "model": model.state_dict(), "step": 7, "val_loss": 1.25},
               results / "model-tiny" / "model.pt")

    decoder = {"conv.weight": torch.randn(4, 3), "conv.bias": torch.randn(4)}
    torch.save({"decoder": decoder, "step": 3}, results / "decoder.pt")

    releases_dir = results / "releases"
    releases_dir.mkdir()
    recipe = {"name": "tiny", "title": "Tiny", "model": "model-tiny",
              "decoder_state": None, "temperature": 1.0, "top_k": 50,
              "max_frames": 10, "species": "american-crow", "provenance": {}}
    (releases_dir / "tiny.json").write_text(json.dumps(recipe))
    (releases_dir / "tinydec.json").write_text(json.dumps(
        {**recipe, "name": "tinydec",
         "decoder_state": str(results / "decoder.pt")}))

    monkeypatch.setattr(releases, "RESULTS", results)
    monkeypatch.setattr(releases, "RELEASES", releases_dir)
    return {"model": model, "decoder": decoder}


class TestExport:
    def test_round_trips_weights_and_recipe(self, tmp_path, tiny):
        loaded = hub.load(hub.export("tiny", tmp_path / "out"))
        assert loaded.config == CONFIG
        assert loaded.manifest == MANIFEST
        assert loaded.species == "american-crow"
        assert loaded.sampling == {"temperature": 1.0, "top_k": 50,
                                   "max_frames": 10}
        assert loaded.trained == {"step": 7, "val_loss": 1.25}
        original = tiny["model"].state_dict()
        state = loaded.state()
        assert set(state) == set(original)
        assert all(torch.equal(state[k], original[k]) for k in original)

    def test_head_stays_tied_after_reload(self, tmp_path, tiny):
        loaded = hub.load(hub.export("tiny", tmp_path / "out"))
        rebuilt = CrowGPT(Config(**loaded.config))
        rebuilt.load_state_dict(loaded.state())
        assert (rebuilt.head.weight.data_ptr()
                == rebuilt.token_embedding.weight.data_ptr())

    def test_frozen_decoder_release_ships_none(self, tmp_path, tiny):
        loaded = hub.load(hub.export("tiny", tmp_path / "out"))
        assert loaded.generation["decoder"] is None
        assert not (loaded.path / "decoder.safetensors").exists()

    def test_decoder_travels_with_the_export(self, tmp_path, tiny):
        from safetensors.torch import load_file

        loaded = hub.load(hub.export("tinydec", tmp_path / "out"))
        assert loaded.generation["decoder"] == "decoder.safetensors"
        shipped = load_file(str(loaded.path / "decoder.safetensors"))
        assert set(shipped) == set(tiny["decoder"])
        assert all(torch.equal(shipped[k], tiny["decoder"][k])
                   for k in shipped)

    def test_refuses_a_format_it_cannot_read(self, tmp_path, tiny):
        out = hub.export("tiny", tmp_path / "out")
        spec = json.loads((out / "config.json").read_text())
        spec["format"] = FORMAT_FROM_THE_FUTURE = hub.FORMAT + 1
        (out / "config.json").write_text(json.dumps(spec))
        with pytest.raises(ValueError, match=f"format {FORMAT_FROM_THE_FUTURE}"):
            hub.load(out)
