"""A release in a form that leaves this repo: safetensors + JSON, no pickle.

`releases.py` names what shipped; this module makes a named release portable.
An export directory is self-contained — model weights as safetensors, the
architecture and tokenizer manifest as explicit JSON, the release sampling in
`generation_config.json`, and the finetuned decoder's weights alongside when
the recipe uses them. Nothing in it reaches back into `results/`, and nothing
in it needs `torch.load` with `weights_only=False`, which is the property that
makes it publishable: a stranger can open every file in it as data.

The model ties `head.weight` to `token_embedding.weight`, so the weights go
out through `save_model`, which stores shared tensors once; `load` restores
the alias before the state dict is handed on.

    hub.export("crowgpt2", "build/crowgpt2")
    sampler = hub.load("build/crowgpt2").sampler(device="cpu")
"""

import json
from pathlib import Path

FORMAT = 1


def export(name, out_dir):
    """Write the named release as a self-contained directory, and return it."""
    import torch
    from safetensors.torch import save_file, save_model

    from crowgpt import releases
    from crowgpt.model import Config, CrowGPT

    release = releases.load(name)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    blob = torch.load(release.checkpoint, map_location="cpu", weights_only=False)
    model = CrowGPT(Config(**blob["config"]))
    model.load_state_dict(blob["model"])
    save_model(model, str(out / "model.safetensors"))
    (out / "config.json").write_text(json.dumps({
        "format": FORMAT,
        "architecture": "crowgpt",
        "config": blob["config"],
        "manifest": blob["manifest"],
        "trained": {"step": blob.get("step"), "val_loss": blob.get("val_loss")},
    }, indent=2) + "\n")

    generation = {"species": release.species, **release.sampling, "decoder": None}
    if release.decoder_state is not None:
        from crowgpt.codec import FINETUNED_DECODER

        source = FINETUNED_DECODER if release.decoder_state == "finetuned" \
            else Path(release.decoder_state)
        state = torch.load(source, map_location="cpu",
                           weights_only=True)["decoder"]
        save_file({k: v.contiguous() for k, v in state.items()},
                  str(out / "decoder.safetensors"))
        generation["decoder"] = "decoder.safetensors"
    (out / "generation_config.json").write_text(
        json.dumps(generation, indent=2) + "\n")
    return out


class Export:
    """A loaded export directory — the same face `releases.Release` shows.

    Construction only reads the JSON; weights and the codec load when
    `sampler()` is called, so inspecting an export costs nothing.
    """

    def __init__(self, path):
        self.path = Path(path)
        spec = json.loads((self.path / "config.json").read_text())
        if spec.get("format") != FORMAT:
            raise ValueError(
                f"{self.path} is format {spec.get('format')!r}; "
                f"this code reads format {FORMAT}")
        self.config = spec["config"]
        self.manifest = spec["manifest"]
        self.trained = spec.get("trained", {})
        self.generation = json.loads(
            (self.path / "generation_config.json").read_text())
        self.species = self.generation["species"]

    @property
    def sampling(self):
        return {key: self.generation[key]
                for key in ("temperature", "top_k", "max_frames")}

    def state(self):
        """The model weights with the head/embedding alias restored."""
        from safetensors.torch import load_file

        state = load_file(str(self.path / "model.safetensors"))
        # save_model stores a tied pair once, under whichever name survives
        # its dedup — restore the other, direction unassumed.
        survivor = "head.weight" if "head.weight" in state \
            else "token_embedding.weight"
        other = ("token_embedding.weight" if survivor == "head.weight"
                 else "head.weight")
        state.setdefault(other, state[survivor])
        return state

    def sampler(self, **kwargs):
        from .sample import Sampler

        if self.generation["decoder"] is not None:
            kwargs.setdefault("decoder_state",
                              str(self.path / self.generation["decoder"]))
        blob = {"config": self.config, "manifest": self.manifest,
                "model": self.state()}
        return Sampler(blob, **kwargs)


def load(export_dir) -> Export:
    return Export(export_dir)
