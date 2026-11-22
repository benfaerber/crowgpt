# 0112 — Does CrowGPT hear what BirdNET throws away?

**2026-11-22** · GPU for extraction, CPU for scoring · **answer: see Results**

## The question

Every meaning result from 0102 to 0111 was measured through the BirdNET
embedding. BirdNET was trained to tell species apart, so the variation
*within* one species is what it is built to discard, and that is where any
meaning would live. The results that stopped the archive-remarks line are the
ones below the recording level: owl against hawk from a single caw (0103,
0.516 dev), and owl against hawk with both predators perched (0104, 0.539).

Perch 2.0 was already tried at the recording level in 0102 and tied BirdNET
on owl against hawk (0.759 against 0.774). So Perch is a second opinion here,
not the new idea. The new idea is CrowGPT. The Dual-AR 17M model
(`crowgpt/results/scaling-0100/dualar-17M-240k/step-240000.pt`) was trained
only to predict the next 13 ms of corvid audio, which forces its hidden state
to track pitch contour, timing and timbre within a call, the things BirdNET
can afford to drop. It has never been asked a question about meaning.

It was pretrained on archive audio that includes these recordings, without any
context or predator label. That is ordinary self-supervised pretraining. It
would only become a leak if the pretraining text carried the labels, and it
carried none.

## Pre-registration (written and committed before any CrowGPT or Perch feature is extracted)

**Representations.** One window of audio goes in and one vector comes out:

- `birdnet`: the 1024-d BirdNET embedding, the baseline. Where an earlier
  experiment cached it, the cached vector is reused unchanged.
- `crowgpt`: the CrowGPT Dual-AR 17M temporal backbone. The audio is
  resampled to 24 kHz, peak-normalised over the span (`crowgpt.codec.normalise`)
  and encoded with EnCodec at 6 kbps. It is fed after the prefix
  `[american-crow, unit bucket, duration bucket]`, where the unit bucket is the
  model's own argmax given the species and the duration bucket is the span's
  real length. Then the hidden state is mean-pooled over the frames of the span.
  **The primary layer is fixed now: the output of temporal block 4 of 6.**
  The other five blocks are reported and are exploratory.
- `perch`: Perch 2.0, 1536-d, on a 5 s window at 32 kHz centred on the span.
  A span shorter than 5 s is zero-padded.

**PRIMARY, the single caw.** This uses 0103's dev split unchanged: 2,150
segmented pure-crow caws from 100 strict owl or hawk recordings dated before
2023. The caw list, labels, groups and evaluator are reused as they are
(`eval_caw_cv` from 0103's `eval_dev.py`): an inverse-recording-weighted
per-caw ROC-AUC, 5-fold, recordist-grouped, `C = 0.1`, 400 group
permutations, seed 42. The caw is isolated the way 0103 isolated it for
BirdNET: the caw's own samples with a 10 ms fade at each end, after 0.25 s of
digital silence so EnCodec's causal LSTM settles. The hidden state is pooled
over the caw's frames only.

- **Passes** if `crowgpt` (block 4) reaches a weighted per-caw AUC ≥ 0.60
  with permutation p < 0.05. For comparison, 0103's isolated-caw BirdNET
  scored 0.522 and the 44 acoustic features 0.516.
- **Null** otherwise. The single-caw owl-versus-hawk null then stands for a
  second, independent representation, and that is worth recording.

**Secondary, declared now.** Each is reported for all three representations:

1. **Single caw, density-matched.** 0103's density-matched dev subset
   (1,589 caws, 76 recordings), with the same evaluator.
2. **Five contexts in the archive.** The 423 witnessed archive recordings
   that 0110's `ArchiveHeads` trains on: raptor mobbing, begging, roost, food
   and flight. The recording vector is the mean over clean crow windows
   (BirdNET crow ≥ 0.25, raptor < 0.05). The windows are recomputed once, and
   every representation uses the same ones. The score is the macro
   one-vs-rest AUC, 5-fold `StratifiedGroupKFold` by recordist,
   `StandardScaler` + `LogisticRegression(C=0.05, balanced)`, with intervals
   by recordist bootstrap.
3. **Crowd inside a call type.** 0109's task (one crow against several,
   mean within-type AUC), on the same segments, folds and head, with only the
   window representation changed. This asks whether CrowGPT is a better crowd
   covariate, which 0113 needs.
4. **Posture in 0104's video set.** The strict perched owl-versus-hawk cell
   (36 owl, 15 hawk) and perched-versus-flying within hawk, on 0104's
   recordings and evaluator. Alala's caution is on record: these cells are
   small, and a change here is probably noise either way.
5. **Outside the archives, a second look.** The five 0110 contexts, with heads
   fit on the archive set in (2) and frozen, then scored on 0110's coded
   recordings with the unit, intervals and count control 0110 used. The set
   has already been scored five ways, so this is not a sealed test. It is
   reported, and nothing is concluded from it alone.

Secondaries 2–5 are a family. They get Holm correction where a p is quoted.

## Results

_Filled in after the single run._
