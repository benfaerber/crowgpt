"""Export a CrowGPT release to ONNX and prove the graphs match the torch model.

Two graphs, because the browser runs two different nets:

  model.onnx    one KV-cached transformer step: (token, position, past) ->
                (logits, grown past). The written prefix is a single species
                token, so there is no priming pass to export — the loop starts
                from an empty cache and feeds one token at a time.
  decoder.onnx  EnCodec codes [1, K, T] -> waveform, through the release's
                decoder (finetuned for crowgpt2).

The position is an explicit input rather than derived from the past tensor's
shape: the TorchScript tracer bakes Python shape arithmetic into constants,
which would silently give every generated token the position of the example
input — the exact bug model.py's `offset` docstring warns about, one layer down.

Everything the JS sampler needs to rebuild the legality mask and the prefix
(vocabulary spans, sampling recipe, tensor shapes) goes into config.json;
nothing about the vocabulary is hardcoded on the JS side.

Run:  .venv/bin/python ../experiments/0080-crowgpt-in-the-browser/run.py [release]
from crowgpt/, CPU only. Writes web/models/ and prints the parity numbers.
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "crowgpt" / "src"))

from crowgpt import releases  # noqa: E402
from crowgpt.codec import CODEBOOK_SIZE  # noqa: E402
from crowgpt.sample import Sampler  # noqa: E402

OPSET = 17


class Step(nn.Module):
    """One cached generation step, functional over the trained module's weights."""

    def __init__(self, model):
        super().__init__()
        self.m = model
        self.n_head = model.config.n_head
        self.n_embd = model.config.n_embd
        self.head_dim = model.config.n_embd // model.config.n_head

    def forward(self, token, position, past_k, past_v):
        """token [1, 1] int64, position [1] int64,
        past_k/past_v [n_layer, n_head, P, head_dim] -> logits [1, vocab],
        new_k/new_v with P grown by one."""
        m = self.m
        x = m.token_embedding(token) + m.position_embedding(position)
        new_k, new_v = [], []
        for i, block in enumerate(m.blocks):
            h = block.ln1(x)
            q, k, v = block.attn.qkv(h).split(self.n_embd, dim=2)
            shape = (1, 1, self.n_head, self.head_dim)
            q, k, v = (t.view(*shape).transpose(1, 2) for t in (q, k, v))
            k = torch.cat([past_k[i].unsqueeze(0), k], dim=2)
            v = torch.cat([past_v[i].unsqueeze(0), v], dim=2)
            new_k.append(k.squeeze(0))
            new_v.append(v.squeeze(0))
            # A single new token after a full history needs no mask at all —
            # everything it can see is already in the past (see model.py).
            att = F.scaled_dot_product_attention(q, k, v)
            out = att.transpose(1, 2).reshape(1, 1, self.n_embd)
            x = x + block.attn.proj(out)
            x = x + block.mlp(block.ln2(x))
        logits = m.head(m.ln_f(x))[:, -1, :]
        return logits, torch.stack(new_k), torch.stack(new_v)


class Decode(nn.Module):
    def __init__(self, encodec):
        super().__init__()
        self.encodec = encodec

    def forward(self, codes):
        """codes [1, K, T] int64 -> waveform [1, 1, T * hop] float32."""
        return self.encodec._decode_frame(codes, None)


def empty_past(config):
    return torch.zeros(config.n_layer, config.n_head, 0,
                       config.n_embd // config.n_head)


def export_step(sampler, out):
    config = sampler.config
    step = Step(sampler.model).eval()
    token = torch.tensor([[int(sampler.vocabulary.species_base)]])
    position = torch.tensor([0])
    torch.onnx.export(
        step, (token, position, empty_past(config), empty_past(config)),
        str(out), dynamo=False, opset_version=OPSET,
        input_names=["token", "position", "past_k", "past_v"],
        output_names=["logits", "new_k", "new_v"],
        dynamic_axes={"past_k": {2: "past"}, "past_v": {2: "past"},
                      "new_k": {2: "grown"}, "new_v": {2: "grown"}},
    )
    return step


def verify_step(sampler, onnx_path, n_positions=200, seed=7):
    """Torch full-context logits vs ONNX incremental logits, same sequence."""
    import onnxruntime as ort

    rng = np.random.default_rng(seed)
    vocab = sampler.vocabulary
    tokens = [int(vocab.species_base)]
    for position in range(1, n_positions):
        if position == 1 and vocab.n_unit_buckets:
            tokens.append(int(vocab.unit_base))
        elif position == 2:
            tokens.append(int(vocab.duration_base + 3))
        else:
            stage = (position - vocab.prefix_len) % vocab.n_codebooks
            tokens.append(int(stage * CODEBOOK_SIZE + rng.integers(CODEBOOK_SIZE)))

    with torch.no_grad():
        reference, _ = sampler.model(torch.tensor([tokens]))
    reference = reference[0].numpy()

    session = ort.InferenceSession(str(onnx_path),
                                   providers=["CPUExecutionProvider"])
    config = sampler.config
    head_dim = config.n_embd // config.n_head
    past_k = np.zeros((config.n_layer, config.n_head, 0, head_dim), np.float32)
    past_v = past_k.copy()
    worst = 0.0
    for position, token in enumerate(tokens):
        logits, past_k, past_v = session.run(None, {
            "token": np.array([[token]], np.int64),
            "position": np.array([position], np.int64),
            "past_k": past_k, "past_v": past_v,
        })
        worst = max(worst, float(np.abs(logits[0] - reference[position]).max()))
    return worst


def export_decoder(sampler, out):
    decode = Decode(sampler.codec.model).eval()
    codes = torch.randint(0, CODEBOOK_SIZE, (1, sampler.vocabulary.n_codebooks, 75))
    torch.onnx.export(
        decode, (codes,), str(out), dynamo=False, opset_version=OPSET,
        input_names=["codes"], output_names=["audio"],
        dynamic_axes={"codes": {2: "frames"}, "audio": {2: "samples"}},
    )
    return decode


def verify_decoder(sampler, onnx_path, frames=150, seed=11):
    import onnxruntime as ort

    rng = np.random.default_rng(seed)
    codes = rng.integers(0, CODEBOOK_SIZE,
                         (1, sampler.vocabulary.n_codebooks, frames))
    with torch.no_grad():
        reference = Decode(sampler.codec.model)(torch.tensor(codes)).numpy()
    session = ort.InferenceSession(str(onnx_path),
                                   providers=["CPUExecutionProvider"])
    audio = session.run(None, {"codes": codes.astype(np.int64)})[0]
    return float(np.abs(audio - reference).max()), float(np.abs(reference).max())


def write_config(release, sampler, out):
    vocab = sampler.vocabulary
    config = sampler.config
    out.write_text(json.dumps({
        "release": release.name,
        "title": release.title,
        "n_codebooks": vocab.n_codebooks,
        "codebook_size": CODEBOOK_SIZE,
        "vocab_size": vocab.size,
        "eos": vocab.eos,
        "prefix_len": vocab.prefix_len,
        "prefix_slots": vocab.prefix_slots(),
        "species": vocab.species,
        "species_base": vocab.species_base,
        "block_size": config.block_size,
        "n_layer": config.n_layer,
        "n_head": config.n_head,
        "head_dim": config.n_embd // config.n_head,
        "sample_rate": 24000,
        "frame_rate": 75,
        "sampling": release.sampling,
        "default_species": release.species,
    }, indent=2) + "\n")


def main(name="crowgpt2"):
    release = releases.load(name)
    sampler = release.sampler(device="cpu")
    models = HERE / "web" / "models"
    models.mkdir(parents=True, exist_ok=True)

    step_path = models / "model.onnx"
    export_step(sampler, step_path)
    step_diff = verify_step(sampler, step_path)
    print(f"model.onnx   {step_path.stat().st_size / 1e6:.1f} MB, "
          f"max |logit diff| over 200 cached steps: {step_diff:.2e}")

    decoder_path = models / "decoder.onnx"
    export_decoder(sampler, decoder_path)
    audio_diff, audio_peak = verify_decoder(sampler, decoder_path)
    print(f"decoder.onnx {decoder_path.stat().st_size / 1e6:.1f} MB "
          f"({'finetuned' if sampler.codec.decoder_state else 'frozen'}), "
          f"max |sample diff|: {audio_diff:.2e} against peak {audio_peak:.2f}")

    write_config(release, sampler, models / "config.json")
    if step_diff > 2e-3:
        raise SystemExit("transformer parity failed")
    if audio_diff > 2e-3 * max(audio_peak, 1.0):
        raise SystemExit("decoder parity failed")
    print("parity ok")


if __name__ == "__main__":
    main(*sys.argv[1:])
