# 0058 — what would the decoder finetune cost?

## Overview

The to-do list called for a costing, not a build, of a decoder finetune: freeze the EnCodec audio codec's encoder and quantizer, and retrain only its decoder on the project's crow corpus so that round-tripped audio loses the "scratchy" artefact — with tokens staying bit-identical so the existing generator keeps working untouched. This experiment benchmarked the actual training step on the real hardware (a 4070 Ti SUPER) without training anything, and found the full adversarial recipe costs 1–3 GPU-days and the spectral-only variant mere hours. That is cheap enough that the go/no-go decision rests entirely on experiment 0057's listening result, not on cost. The costing's real finding is that the originally proposed acceptance gate would be Goodharted by the training itself and had to be redesigned.

## In depth

### What was measured (`run.py`, `results.json`)

**Where the parameters are.** facebook/encodec_24khz is 14.85M parameters split almost exactly in half: encoder 7.43M, decoder 7.43M, quantizer 0 (codebooks are buffers). The trainable half is 7.4M — small. A representative MS-STFT discriminator at the paper's shape (5 scales, 32-filter stacks) adds 0.47M.

**What a step costs**, batch 16 × 1 s excerpts at 24 kHz on the 4070 Ti SUPER:

| | ms/step | peak VRAM |
|---|---|---|
| spectral-only (frozen encode → decoder fwd → MS-STFT loss → bwd) | 41 | 1.3 GB |
| + adversarial (gen adv + feature match through decoder, disc update) | 368 | 7.0 GB |

Batch 32 OOMs on the adversarial step — the discriminator holds five full-resolution STFTs of the whole batch — so batch 16 is the operating point. The benchmarked adversarial step decodes twice (once for the generator update, once detached for the discriminator's); an implementation that reuses the fake saves one decode, so 368 ms is mildly conservative.

**How big an epoch is.** The bout store today holds 64.3 h total across 127,553 bouts and 46 species, 30.8 h of it American Crow (the TODO's "41.7 h" predates the v2 corpus). At 1 s crops and batch 16, one full-corpus pass is 14,467 steps:

| | one pass | 20 passes | 50 passes |
|---|---|---|---|
| spectral-only | 0.17 h | 3.4 h | 8.5 h |
| full adversarial | 1.48 h | 1.2 days | 3.1 days |

EnCodec pretrained from scratch on orders of magnitude more audio; a domain finetune of a 7.4M-parameter decoder should land in the 20–50-pass range. So: an overnight-to-weekend job on hardware already in the house, reportable through `crowgpt.progress.Run` like any other overnight.

### Engineering cost, estimated not measured

About a day of code: an MS-STFT discriminator with hinge/feature-matching losses (vendor audiocraft's, MIT, or write about 150 lines against this benchmark), a 1 s crop loader over `BoutStore` (exists in parts), checkpointing, and `Run` progress with an eval callback. No new venv — torch and transformers are already in crowgpt's.

One line to verify before any *published* audio depends on the result: the encodec_24khz weights license (the code is MIT; the weights historically were not). Same class of flag as experiment 0055's ND note, and it binds the promo page, not the research.

### The gate has to change — the real finding of the costing

The TODO entry's pre-gate — beat K=8's 1.165 on the experiment 0028 STFT instrument, head toward K=32's 1.035 — is Goodharted by this training by construction: `multi_res_stft_distance` is the same loss family the finetune optimises. A spectral-only decoder will improve that number whether or not it sounds better; over-smoothing lowers STFT distance while making a worse crow. The replacement gate, in order:

1. **AST-FAD** (experiment 0028 already computes it; an independent embedder the training never sees): the finetuned round-trip must move toward raw against the frozen decoder's FAD, at matched n per 0028's own bias note.
2. **Experiment 0024's segmenter density and stage-0 churn on decoded output** — cheap, orthogonal, and the defect vocabulary Ben's ears already validated.
3. **A 0057-style labelled listen**, about 8 rows: raw / frozen-decoder K=8 / finetuned-decoder K=8. Describe, don't rank. Five minutes, and it is the only judge of "scream" there is.

The STFT number can still be logged — it is the training loss — it just no longer gets a vote.

### Risks, priced

- **The experiment 0037 null**: a better round-trip may again buy nothing audible in generation. The cost of finding out is GPU-days, not a tokenizer migration, and it stacks with any later model-side work.
- **Adversarial finetuning on 64 h of one domain can collapse** (artifacts, discriminator winning). The spectral-only arm at 0.17 h/pass is the control that costs nothing to run alongside.
- **Train on all 46 species, not American Crow alone.** The decoder serves every bout the store feeds any model; experiment 0049 says the species mix is neutral for generation, and halving the audio to 30.8 h buys back only hours.

### What this changed

The decision is no longer about cost — 1–3 GPU-days is below the threshold where a costing could refuse it. What it now waits on is experiment 0057's listen: if the scream lives in the K=8 round-trip, build it (full adversarial, spectral control arm, the three-part gate above); if the scream is the model's, the finetune only fixes the scratch and should queue behind whatever the scream experiment finds. The gate redesign stands either way.
