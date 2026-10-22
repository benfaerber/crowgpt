"""The models that shipped, by name — everything else in results/ is an experiment.

A release is a full recipe, not a checkpoint: CrowGPT2 is model-longctx *and*
the adversarial decoder finetune *and* T 1.1 / k 200 at the 6 s window, and
dropping any leg of that silently produces different audio under the same
name. Each release lives in results/releases/<name>.json with its provenance;
this module reads them and builds ready-to-use samplers.
"""

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "results"
RELEASES = RESULTS / "releases"


class Release:
    def __init__(self, blob):
        self.name = blob["name"]
        self.title = blob["title"]
        self.model = blob["model"]
        self.decoder_state = blob["decoder_state"]
        self.temperature = blob["temperature"]
        self.top_k = blob["top_k"]
        self.max_frames = blob["max_frames"]
        self.species = blob["species"]
        self.provenance = blob["provenance"]

    @property
    def checkpoint(self):
        return RESULTS / self.model / "model.pt"

    @property
    def sampling(self):
        return {"temperature": self.temperature, "top_k": self.top_k,
                "max_frames": self.max_frames}

    def sampler(self, **kwargs):
        from .sample import Sampler

        kwargs.setdefault("decoder_state", self.decoder_state)
        return Sampler(self.checkpoint, **kwargs)


def load(name):
    path = RELEASES / f"{name}.json"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in RELEASES.glob("*.json"))) or "none"
        raise KeyError(f"no release named {name!r}; known releases: {known}")
    return Release(json.loads(path.read_text()))


def all_releases():
    return [Release(json.loads(p.read_text())) for p in sorted(RELEASES.glob("*.json"))]
