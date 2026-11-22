# 0114 — How much do the calls say about the scene?

**2026-11-22** · GPU · **answer: see Results**

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

_Filled in after the single run._
