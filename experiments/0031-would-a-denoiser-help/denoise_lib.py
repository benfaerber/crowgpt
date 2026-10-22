"""Load the biodenoising DNS48 model from the local archive, not the network.

Upstream is a research repo with no commits since October 2024 and no forks, and
it fetches its weights from a Google Cloud Storage bucket rather than a release
asset. The code is 300 KB of MIT and is vendored beside this file; the weights
are 75 MB of CC-BY-NC that nobody can reproduce without the training corpus, so
they are archived under DATA_DIR and checked by hash on every load.

Nothing here touches the network or the GPU.
"""
import hashlib
import os
import sys
import types
from pathlib import Path

MODEL_RATE = 16000
MODEL_SHA256 = "e1f0da9dcecbba5c7fe497daa6e2e35d9f55af895ff893d56ff93409ce7bd24a"
MODEL_NAME = "model-16kHz-dns48.th"
UPSTREAM_URL = (
    "https://storage.googleapis.com/esp-public-files/biodenoising/" + MODEL_NAME
)

_REPO = Path(__file__).resolve().parents[2]

# The package __init__ imports live.py, which imports sounddevice at module
# scope and raises OSError when the system PortAudio library is absent. Live
# microphone denoising is not wanted here, so the module is stubbed rather than
# installing a system package.
if "sounddevice" not in sys.modules:
    sys.modules["sounddevice"] = types.ModuleType("sounddevice")

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

import torch  # noqa: E402
from biodenoising.denoiser.utils import deserialize_model  # noqa: E402


def model_path():
    data_dir = Path(os.environ.get("DATA_DIR", _REPO / "data"))
    return data_dir / "models" / "biodenoising" / MODEL_NAME


def _verify(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise ValueError(
            f"{path} hashes to {digest}, expected {MODEL_SHA256}. Refusing to "
            f"run — a silently different checkpoint would invalidate every "
            f"number this experiment has already recorded."
        )


def load_model(device="cpu"):
    path = model_path()
    if not path.exists():
        raise FileNotFoundError(
            f"No archived checkpoint at {path}. Fetch it once from "
            f"{UPSTREAM_URL} and verify it hashes to {MODEL_SHA256}. It is "
            f"CC-BY-NC 4.0, so it stays under DATA_DIR and out of git."
        )
    _verify(path)
    # The checkpoint is a pickled object graph rather than a bare state dict, so
    # it needs weights_only=False. That is only safe because _verify has already
    # matched the file against a known hash — keep the two calls in this order.
    model = deserialize_model(torch.load(path, map_location="cpu",
                                         weights_only=False)["model"])
    if model.sample_rate != MODEL_RATE:
        raise ValueError(
            f"checkpoint reports {model.sample_rate} Hz, expected {MODEL_RATE}"
        )
    return model.to(device).eval()


@torch.no_grad()
def denoise(model, signal, device="cpu"):
    x = torch.from_numpy(signal).float().to(device)[None, None]
    return model(x)[0, 0].cpu().numpy()
