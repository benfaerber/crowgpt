# 0114 — How much do the calls say about the scene?

**2026-11-22** · GPU · **answer: null by the rule, narrowly — told the scene, CrowGPT reads it at 0.692 against a 0.70 bar; it beats the shuffled control by 0.185 and gains 0.58 bits per chunk, but with crowd removed it falls to 0.572, and most of the bits are timbre, not timing**

## The question

0110 and 0112 ask whether a classifier can read the context from an
embedding. This experiment asks the same thing the other way round, with the
generator: **if CrowGPT is told the scene, does it predict the crows' next
sound better?** The gain is measured in bits, as the log-likelihood with the
true context minus the log-likelihood with no context. That gain is the
amount of information about the scene carried in the fine structure of the
call stream, which a mean embedding pools away.

It also joins the two halves of the project. A model that predicts better
when told "begging" is a model that can be asked to *say* begging. FUTURE.txt
("Merging crowgpt with a future crow translate") calls context-conditioned
generation the intended design.

## Pre-registration (written and committed before any fine-tune runs)

**Base model.** The 0101 Dual-AR 17M, quality-conditioned
(`crowgpt/results/quality-0101/dualar-quality-240k/step-240000.pt`). It is
chosen because it already has a channel slot in its prefix
`[species, channel, unit, duration]`. Its six channel tokens are repurposed as
`raptor_mobbing, begging, roost_gathering, food_foraging, flight_contact,
none`, in that order. The fine-tune overwrites the quality meaning, and the
shuffled-label control below pays the same cost.

**Data.** The 423 witnessed archive recordings that 0110's `ArchiveHeads`
trains on (same filter). The clean crow windows come from 0112's single
BirdNET pass (crow ≥ 0.25, raptor < 0.05).

- A chunk is 6 s made of two adjacent clean windows, non-overlapping. Up to
  24 chunks are taken per recording, evenly spaced through its eligible
  chunks.
- Each chunk is encoded from 0.25 s before its start, for the LSTM lead, at
  6 kbps after peak normalisation.
- The unit bucket is the base model's argmax given `[american-crow, none]`.
  The duration bucket is the real length.
- A recording with no eligible 6 s chunk enters with its longest single clean
  window as a 3 s chunk, so no context loses its short recordings.

**Folds.** 5-fold `StratifiedGroupKFold` by recordist, seed 0, stratified on
context. The unit of evaluation is the held-out recording.

**Fine-tune, per fold, fixed now.**

- 2,000 steps, batch 8 chunks, AdamW at lr 1e-4 with 100 warmup steps and
  cosine decay to 10%, weight decay 0.1.
- Context dropout 0.2: the context token is replaced by `none`, so the same
  model also learns the unconditional distribution.
- Loss on frame tokens only. The prefix and EOS are excluded from both
  training and scoring, so the context token is never itself a target.

**Shuffled-label control, per fold.** It is the same in every respect, except
that contexts are permuted across the fold's *training* recordings (seed 1).
It measures how many "bits about context" a fine-tune finds when there are
none to find, from overfitting and from the channel token's old meaning.

**Scoring.** Each held-out chunk is scored once under each of the six prefixes.
A recording's log-likelihood `LL_c` is the sum over its chunks.

- `score_c = LL_c − LL_none` is the evidence for context `c` against no
  context.
- **Bits per chunk** = mean over held-out chunks of
  `(log p(x | true context) − log p(x | none)) / ln 2`.

**PRIMARY.** The macro one-vs-rest ROC-AUC of `score_c` over held-out
recordings, from the true-label fine-tunes. Each context's AUC uses
`score_c` for that context.

- **Passes** if macro AUC ≥ 0.70 **and** it exceeds the shuffled control's
  macro AUC by at least 0.05 **and** true-label bits per chunk exceed the
  control's, with the recordist-bootstrap 95% interval of the difference
  above zero.
- **Null** otherwise.

**Secondary, declared now.**

1. **Per-context bits and AUC**, true model against control.
2. **Crowd control.** Each `score_c` with the recording's mean 0109 count-head
   score regressed out, as in 0110.
3. **Where the bits live.** Bits split by codec stage (`stage_0` against
   stages 1–7). Coarse-stage bits mean structure (timing, contour). Fine-stage
   bits mean timbre and channel, which is the less interesting and more
   confound-prone reading.
4. **Beside the discriminative reading.** The macro AUC set next to 0112's
   secondary 2 for the same recordings (BirdNET and CrowGPT block 4 with a
   linear head). No threshold. This says whether the generative route reads
   more or less than a classifier.

**Not done here.** Generating audio under a context token. That waits for this
to pass and for a listening pool.

## Results

Run once, `results.json`. 423 recordings, 2,718 chunks, 249 recordists, five
recordist-grouped folds, each fine-tuned twice (true labels, shuffled labels).

**Primary: null.** Two of the three clauses passed. The AUC clause missed by
0.008.

| | true labels | shuffled control |
|---|---:|---:|
| macro AUC of `LL_c − LL_none` | **0.692** (0.654 – 0.729) | 0.507 (0.471 – 0.545) |
| bits per chunk, true context against `none` | 0.492 | −0.115 |

The margin over the control is 0.185 (the rule asked for 0.05). The bits
difference is 0.575 per chunk, with a recordist-bootstrap interval of 0.27 to
0.88, above zero.

Per context, AUC: roost 0.803, begging 0.750, flight 0.671, food 0.654,
raptor mobbing 0.582.

**Secondary.**

1. Bits per chunk by context, true against shuffled:

   | context | true | shuffled |
   |---|---:|---:|
   | begging | 2.37 | 0.25 |
   | roost | 2.36 | −0.48 |
   | food | 0.77 | 0.88 |
   | raptor mobbing | −0.40 | −0.20 |
   | flight | −1.27 | −0.69 |

2. With the 0109 count score regressed out, the macro AUC is **0.572** (0.528 –
   0.619): roost 0.672, begging 0.631, the other three at chance.
3. By codec stage: true-label bits are 0.12 in stage 0 (coarse: timing and
   contour) and 0.37 in stages 1–7 (fine: timbre and channel). The control is
   −0.04 and −0.08.
4. Beside the discriminative reading on the same recordings (0112 secondary
   2): BirdNET with a linear head reaches 0.808, and CrowGPT block 4 with a
   linear head 0.785. The generative route reads less than either.

## Reading

- There is real information about the scene in the call stream. The
  shuffled control finds none, as it should, and the true-label model finds
  half a bit per 6 s chunk. But it is concentrated where 0110 and 0113 already
  pointed: begging and roost carry all of it, and a roost is mostly crowd.
- **Most of what a context token buys is the crowd.** Removing the count score
  takes the generative reading from 0.69 to 0.57. That matches 0110 (roost is
  crowd) and contrasts with 0113, where a single bird's graded features held
  up at 0.64 after the same removal. Fed whole chunks, the generator learns
  "many crows" rather than how a crow calls.
- **The bits are mostly timbre.** Three quarters of the gain is in the fine
  codec stages, which carry the recording channel and the texture of a chorus
  more than the timing and contour of a call. That is the confound-prone half.
- Raptor mobbing and flight have *negative* bits. Telling the model "raptor"
  makes held-out raptor chunks less likely than saying nothing. The
  fine-tune learned something about its training recordists' mobbing
  recordings that does not transfer to new recordists.

## Limits

- One fine-tune recipe, fixed in advance (2,000 steps, lr 1e-4). A different
  schedule could land on either side of 0.70. That is exactly why it was
  fixed beforehand.
- The base model's channel tokens previously meant recording quality. The
  shuffled control pays the same cost, but the meaning carried over is not
  zero.
- Archive only. No sealed set.

## What it changed

- **Context-conditioned generation is not ready, and this says why.** A
  context token today mostly encodes crowd size and recording texture. The
  "Two-way semantic generation" entry in FUTURE.txt stays blocked. If it is
  revisited, the conditioning should be on crowd explicitly (the 0109 count
  score as its own token), with context on single-bird chunks.
- **Bits per chunk is a usable instrument**, and its shuffled control behaves
  (−0.1 bits, AUC 0.51). It can be rerun unchanged on roof-station audio,
  where context is known by construction rather than read from remarks.
- Nothing ships. No audio was generated under a context token.
