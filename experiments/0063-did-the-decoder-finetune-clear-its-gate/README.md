# 0063 — did the decoder finetune clear its gate?

**2026-08-09** · test split, untouched by training · **answer: yes,
decisively — the adversarial decoder lands within 3.3 FAD of the raw-vs-raw
noise floor. Ben's listen pending.**

## The gate (0058's design: FAD and unit delta vote, STFT logged only)

64 held-out TEST bouts, one per recording, grouped split — no stage of the
finetune ever read them. Same frozen encoder, bit-identical K=8 tokens,
three decoders:

| decoder | AST-FAD ↓ | unit Δ | STFT (logged, voteless) |
|---|---|---|---|
| frozen (incumbent) | 51.4 | −0.19 | 1.148 |
| spectral control (best @110k) | 44.7 | +0.08 | **1.009** |
| **adversarial (best @130k)** | **34.2** | **0.00** | 1.195 |
| *raw vs raw floor* | *30.9* | — | — |

**The adversarial arm closed ~84% of the measurable gap to the floor**
((51.4−34.2)/(51.4−30.9)) and preserves the segmenter's burst count exactly,
where the frozen decoder loses a unit every five bouts.

**The Goodhart prediction confirmed itself on cue.** The spectral control
wins the STFT number — it optimises that loss family — while sitting 10 FAD
behind the adversarial arm; and STFT ranks the adversarial decoder *below
frozen*. The gate 0058 retired would have picked the wrong winner and
rejected the right one. Metrics that are training losses do not get votes.

Val→test transfer is clean (val best 40.4 → test 34.2 on a different FAD
pool and n), so this is not val overfitting. Best checkpoints came early —
spectral 110k of 227k, adversarial 130k of 569k; the last three-quarters of
adversarial training never improved val FAD. A future finetune of this kind
can stop at ~15 passes.

## What the ear decides

`crowgpt/results/compare-decoder-finetune.html` — 8 test bouts, each RAW /
frozen K=8 / spectral K=8 / adversarial K=8, labelled. The question is
0057's: does K=8 still scratch through the new decoder? Describe, don't
rank.

**Ben's verdict, 2026-08-09, on the page above:** *"oh shit this is really
good! Still a quality degradation but no more than 10%!"*, and naming the
arm: *"K=8 · adversarial finetune — is great."* Against 0057 two days
earlier, where the same K=8 round-trip through the frozen decoder graded
"scratchy", "bad", D+ on half the rows. The scratch is functionally gone;
the adversarial finetune is confirmed as the project's vocoder.

## What it changed

- The generation stack gets a better vocoder for free: tokens are
  bit-identical, so every existing model, sampler and page can decode
  through `decoder-finetune/adversarial/best.pt` with no retraining.
  Wiring that in (Codec loading a finetuned decoder checkpoint) is the
  follow-up once Ben's listen confirms.
- 0014's ceiling number moves: the 0.81 BirdNET-retention ceiling and every
  "blame the codec" note downstream were measured against the frozen
  decoder and are now stale in the corvid band.
- The scream/scratch decomposition (0057) gets its second half tested: if
  the scratch is gone by ear here, what remains in generation is the
  model's share alone.
