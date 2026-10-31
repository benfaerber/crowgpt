---
license: cc-by-nc-sa-4.0
library_name: pytorch
tags:
  - audio
  - audio-generation
  - bioacoustics
  - animal-vocalizations
  - corvids
  - encodec
extra_gated_prompt: >-
  These weights were trained on sound-archive recordings that are not uniformly
  licensed for redistribution (see the model card for the exact mix). Access is
  granted for research and evaluation. By requesting access you agree that you
  will not play generated audio to wild birds, and that you will not
  redistribute the weights outside the terms below.
extra_gated_fields:
  Name: text
  Affiliation: text
  Intended use: text
  I will not use these models for playback to wild birds: checkbox
  I will not redistribute the weights: checkbox
---

# CrowGPT — generative models for American Crow calls

Small autoregressive transformers that generate American Crow
(*Corvus brachyrhynchos*) call bouts as raw audio, trained from scratch on
archive recordings with **no human labelling anywhere in the loop**. They are
the generative half of [CrowGPT](https://crowgpt.org), an open-source project
decoding crow vocalizations from field recordings. Code, experiments and the
loader live at [github.com/benfaerber/crowgpt](https://github.com/benfaerber/crowgpt);
the project's own account of how far it has got is on
[crowgpt.org](https://crowgpt.org), including real recordings next to
generated ones so you can judge the gap yourself.

Audio is tokenized through EnCodec at 24 kHz with 8 codebooks; the model
writes token streams, and a decoder turns them back into sound.

## The releases

A release here is a **recipe, not a checkpoint**: model weights, a decoder
state and fixed sampling settings together, because dropping any leg produces
different audio under the same name. Each lives in its own self-contained
directory.

| | CrowGPT1 | CrowGPT2 |
|---|---|---|
| directory | `crowgpt1/` | `crowgpt2/` |
| params | 21.2 M (d384, 8 layers, 6 heads) | 21.9 M (d384, 8 layers, 4 heads) |
| window | 3 s (225 codec frames, ctx 1811) | 6 s (460 codec frames, ctx 3612) |
| decoder | stock EnCodec | `crowgpt2/decoder.safetensors`, an adversarially finetuned EnCodec decoder |
| sampling | T 1.0, top-k 200 | T 1.1, top-k 200 |
| conditioning prefix | species | species + duration bucket + units bucket |
| training corpus | American-Crow-only bouts, 3 s cap | 68-species bouts, 6 s cap (~114 h) |
| published | 2026-08-07 | 2026-08-13 |

CrowGPT2 decoded through the stock decoder **is not CrowGPT2**. The finetuned
decoder is part of the name, which is why its weights travel in the folder.

## How they work

Audio is tokenized with **EnCodec 24 kHz at 6.0 kbps (K = 8 residual
codebooks)**, the codebooks flattened into one stream with each codebook
owning its own vocabulary slice (75 frames/s). A causal transformer is trained
on token sequences of whole call *bouts*, bursts merged within 1.5 s, so
inter-call timing is learned rather than assembled by hand. Species
conditioning is a prefix token; it costs nothing and is trustworthy because a
species detector selected the training windows in the first place.

CrowGPT2 additionally decodes through a finetuned EnCodec decoder (encoder and
quantizer frozen, so tokens are bit-identical to stock EnCodec): on held-out
real audio the finetune closes ~84 % of the measurable round-trip gap
(AST-FAD 51.4 → 34.2 against a 30.9 raw-vs-raw floor) and removes the
"scratchy" codec signature confirmed in blinded listening.

## Files

Every file opens as plain data, with no pickle anywhere:

- `model.safetensors`: the transformer weights (`head.weight` and
  `token_embedding.weight` are tied; stored once, restored on load)
- `config.json`: architecture, the tokenizer manifest the model was trained
  against, and training provenance (`format: 1`)
- `generation_config.json`: the release sampling (temperature, top-k,
  max_frames, species) and which decoder to use
- `decoder.safetensors`: CrowGPT2 only, the finetuned EnCodec decoder's weights

Both exports are verified against the internal checkpoints: state dicts
identical, sampled token streams bit-identical at a fixed seed.

## Running

The loader is the `crowgpt` package in the
[project repository](https://github.com/benfaerber/crowgpt) (`crowgpt/`, its
own venv with torch and EnCodec). A pip-installable package is the planned
next step and does not exist yet.

```python
from huggingface_hub import snapshot_download
from crowgpt import hub

path = snapshot_download("faerber/crowgpt", allow_patterns="crowgpt2/*")
release = hub.load(f"{path}/crowgpt2")
sampler = release.sampler()          # CPU works; CUDA if available
audio = sampler.audio(release.species, seed=30071, **release.sampling)
# 24 kHz float waveform
```

On CPU a bout takes ten to twenty seconds; on a consumer GPU, a few.

## Evaluation, honestly

- **Blinded human discrimination** (the project's primary instrument): a
  practiced listener separates generated from real bouts at **75 % correct
  (d′ ≈ 1.34)** over 60 trials, better than chance and far from trivial. In
  the most recent sittings, typical CrowGPT2 clips through the finetuned
  decoder were frequently judged "the same" as real audio, while catch trials
  stayed near-perfect.
- **Structure:** CrowGPT2 produces 4.1 call units per 6 s clip against 5.1 in
  real bouts, with inter-call gap timing within 30 ms of real medians.
- **Known defects**, in the project's own vocabulary: an occasional harsh
  "scream" artifact; a low-periodicity "hoarse" texture on some draws; and no
  within-clip crescendo. Real bouts rise in pitch strength across the clip,
  generated ones stay flat.
- **Circularity caveat:** the same species detector that selected the training
  windows scores generated audio *above* real field recordings, so detector
  confidences are not evidence of realism here. Blinded listening is the
  unbiased instrument, which is why it is the one reported first.

## Training data and licensing

The corpus is call bouts extracted from publicly available bioacoustic archive
recordings and community uploads, including
[Xeno-canto](https://xeno-canto.org), the community archive of wildlife sound,
whose recordings are shared under Creative Commons licenses; naming it here is
the attribution those licenses ask for. **The corpus is not uniformly
licensed:** by extracted bout-hours, roughly 45 % is all-rights-reserved
archive material, 45 % CC BY-NC-SA, and 9 % CC BY-NC-ND. The weights are
published under **CC BY-NC-SA 4.0** to honour the most restrictive share that
any license covers at all; the all-rights-reserved share is the reason access
is gated and commercial use is not offered under any terms. No training audio
is redistributed in this repository.

## Intended use and restrictions

Research and evaluation of generative bioacoustics: studying what a small
model learns of vocal structure, benchmarking codecs and detectors on
synthetic vocalizations, and demos.

**Do not play generated calls to wild birds.** Playback to wild corvids can
constitute harassment, distorts the behaviour of habituated populations, and
destroys the observational baseline this project depends on. The models are
instruments for studying crows, not for talking to them.

Not for: commercial use, playback experiments without an ethics review,
hunting or pest-control lures, or passing generated audio off as field
recordings.
