"""Does upstream's dns48(pretrained=True) actually load the weights?

load_model_state_dict(model, state_dict) in utils.py reads:

    current_model_dict = model.state_dict()
    model.load_state_dict(current_model_dict, strict=False)

It re-loads the model's own freshly-initialised state and never touches the
state_dict argument. If that is what it looks like, two calls return two
different random networks.
"""
import sys, types
sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))
sys.path.insert(0, "vendor")
import torch
from biodenoising.denoiser.pretrained import dns48
from biodenoising.denoiser.utils import deserialize_model

def fingerprint(model):
    return {k: float(v.float().sum()) for k, v in model.state_dict().items()}

a, b = fingerprint(dns48(pretrained=True)), fingerprint(dns48(pretrained=True))
differing = [k for k in a if abs(a[k] - b[k]) > 1e-6]
print(f"dns48() called twice: {len(differing)}/{len(a)} tensors differ between calls")
print("  -> random init, weights discarded" if differing else "  -> deterministic")

pkg = torch.load("../../data/models/biodenoising/model-16kHz-dns48.th",
                 map_location="cpu", weights_only=False)
real = fingerprint(deserialize_model(pkg["model"]))
matches = sum(1 for k in real if k in a and abs(real[k] - a[k]) < 1e-6)
print(f"\ncheckpoint vs dns48() output: {matches}/{len(real)} tensors match")
print("  -> dns48 IS returning the trained weights" if matches == len(real)
      else "  -> dns48 is NOT returning the trained weights")
