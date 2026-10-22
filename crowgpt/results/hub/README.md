---
license: other
license_name: private-pre-release
license_link: https://huggingface.co/faerber/crowgpt#license
tags:
- audio
- bioacoustics
- corvids
- generative
---

# CrowGPT

Generative models of crow calls — small transformers trained from scratch on
call bouts of wild corvids, with no human labelling anywhere in the loop. Audio
is tokenized through EnCodec at 24 kHz / 8 codebooks; the model writes token
streams, and a decoder turns them back into sound.

**Status: private pre-release.** This repo is the eventual public home of the
CrowGPT releases, populated and versioned now so the release is a flip of a
visibility switch rather than a scramble. It stays private until the weights
are retrained on cleanly-licensed audio — see [License](#license).

## The releases

Each release is a **full recipe, not a checkpoint** — weights *and* decoder
state *and* sampling — because dropping any leg produces different audio under
the same name. Each lives in its own self-contained directory:

| | CrowGPT1 | CrowGPT2 |
|---|---|---|
| directory | `crowgpt1/` | `crowgpt2/` |
| decoder | frozen EnCodec | `crowgpt2/decoder.safetensors` (adversarial finetune) |
| sampling | T 1.0 / top-k 200 | T 1.1 / top-k 200 |
| window | 3 s (225 frames) | 6 s (460 frames) |
| species | American Crow | American Crow |
| architecture | 8 layers, d 384, ctx 1811 | 8 layers, d 384, ctx 3612 |

CrowGPT2 decoded through the frozen decoder **is not CrowGPT2** — the finetuned
decoder is part of the name, which is why its weights travel in the folder.

## Files

Every file opens as plain data — no pickle anywhere:

- `model.safetensors` — the transformer weights (`head.weight` and
  `token_embedding.weight` are tied; stored once, restored on load)
- `config.json` — architecture, the tokenizer manifest the model was trained
  against, and training provenance (`format: 1`)
- `generation_config.json` — the release sampling: temperature, top-k,
  max_frames, species, and which decoder to use
- `decoder.safetensors` — CrowGPT2 only: the finetuned EnCodec decoder's
  weights, nothing else

## Running

The loader currently lives in the CrowGPT repo's `crowgpt` package (a
pip-installable package is the planned next step):

```python
from huggingface_hub import snapshot_download
from crowgpt import hub

path = snapshot_download("faerber/crowgpt", allow_patterns="crowgpt2/*")
release = hub.load(f"{path}/crowgpt2")
sampler = release.sampler()          # CPU works; CUDA if available
audio = sampler.audio(release.species, seed=30071, **release.sampling)
# 24 kHz float waveform
```

Fidelity: both exports are verified against the internal checkpoints — state
dicts identical, sampled token streams bit-identical at a fixed seed.

## License

The training corpus includes recordings from
[Xeno-canto](https://xeno-canto.org), the community archive of wildlife sound,
whose recordings are shared under Creative Commons licenses — naming it here is
the attribution those licenses ask for. These weights are research artifacts,
not yet licensed for redistribution or any other use, and the repo stays
private until the public release can be built on cleanly-licensed audio alone.
The shape you see here is that release, minus the rights.
