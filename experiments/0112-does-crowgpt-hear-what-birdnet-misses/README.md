# 0112 — Does CrowGPT hear what BirdNET throws away?

**2026-11-22** · GPU for extraction, CPU for scoring · **answer: no — CrowGPT on a single caw scores 0.430 (p = 0.83), and it never beats BirdNET on meaning; where it does win is counting crows (0.845 against 0.806). Perch independently confirms the posture lead (perched against flying hawk 0.848)**

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

Run once over the full span set (`results.json`), after one fix described
under Deviations. Every one of 2,150 dev caws had audio, and no
representation dropped any. BirdNET's cached isolated-caw number reproduces
0103 exactly (0.5223), and BirdNET's 0104 cells reproduce 0104 exactly
(0.539 and 0.857). The new pipeline is reading the same audio as the old
one.

**PRIMARY: null.**

| single caw, owl vs hawk (0103 dev) | weighted per-caw AUC | permutation p |
|---|---:|---:|
| **CrowGPT block 4** | **0.430** | 0.83 |
| BirdNET isolated (0103's number) | 0.522 | — |
| Perch isolated | 0.546 | 0.17 |

Every CrowGPT block lies between 0.430 and 0.466. Density-matched (secondary
1): CrowGPT 0.546 (p = 0.27), BirdNET 0.571 (p = 0.13), Perch 0.579
(p = 0.13).

**Secondary 2: five contexts in the archive** (423 recordings, 249
recordists, macro one-vs-rest AUC):

| | macro AUC | 95% interval |
|---|---:|---:|
| BirdNET | 0.808 | 0.775 – 0.841 |
| Perch | 0.816 | 0.778 – 0.855 |
| CrowGPT block 4 | 0.785 | 0.748 – 0.821 |
| CrowGPT blocks 1–6 (exploratory) | 0.762 – 0.792 | |

CrowGPT minus BirdNET: −0.023 (−0.064 to +0.017). Perch minus BirdNET:
+0.008 (−0.025 to +0.038). Strict owl against hawk (exploratory): BirdNET
0.773, Perch 0.720, CrowGPT 0.713.

**Secondary 3: one crow against several, inside a call type** (0109's
segments, folds and head):

| | mean within-type AUC | 95% interval | begging stratum |
|---|---:|---:|---:|
| **CrowGPT block 4** | **0.845** | 0.804 – 0.875 | 0.803 |
| BirdNET (0109) | 0.806 | 0.771 – 0.837 | 0.727 |
| Perch | 0.784 | 0.746 – 0.820 | 0.610 |

**Secondary 4: posture in 0104's video set.**

| | perched owl vs perched hawk, strict (36 v 15) | perched vs flying, within hawk (27 v 21) |
|---|---:|---:|
| BirdNET | 0.539 (p = 0.40) | 0.857 (p = 0.0025) |
| Perch | 0.620 (p = 0.17) | **0.848** (p = 0.0025, Holm 0.01) |
| CrowGPT block 4 | 0.461 (p = 0.61) | 0.698 (p = 0.022, Holm 0.09) |

**Secondary 5: outside the archives, a second look** (230 recordings,
frozen archive heads, event-level AUC):

| | raptor | begging | roost | food | flight |
|---|---:|---:|---:|---:|---:|
| BirdNET (0110) | 0.731 | 1.000 | 0.776 | 0.650 | 0.634 |
| Perch | 0.745 | 0.998 | 0.811 | 0.672 | 0.636 |
| CrowGPT block 4 | 0.688 | 0.951 | 0.767 | 0.613 | 0.539 |

## Reading

- **The single-caw null holds with a second and a third representation.** A
  model trained to predict the fine structure of crow audio, and Perch, both
  find nothing in an isolated caw that says owl or hawk. CrowGPT's 0.43 is
  below chance, which in cross-validation of this size is noise, not signal.
  "No representation tried can hear the predator in one caw" is now the
  honest status.
- **CrowGPT is not a better meaning feature.** It trails BirdNET slightly on
  contexts in the archive and outside it. Perch ties BirdNET everywhere.
  BirdNET is not what has been holding the line back.
- **CrowGPT is a better crowd counter.** It is ahead in every call type, and
  most of all on begging, the stratum where 0109's head was weakest (0.80
  against 0.73). Predicting the next 13 ms has to track how many voices
  overlap. That makes it the better covariate for 0113's single-bird
  selection in future work.
- **Posture is confirmed by an independent representation.** Perch, trained
  on different data with a different objective, reproduces BirdNET's
  perched-against-flying separation within hawk (0.848 against 0.857), and
  this time the contrast was declared before the run. Owl against hawk with
  both perched stays at chance in all three. Of everything tested on this
  line, the evidence still points to what the predator is doing, not which
  predator it is.

## Deviations

- The first evaluation pass read only 229 of 0104's 310 clips. The other 81
  (the pilot clips) live under `data/experiments/0103-raptor-mobbing/audio`,
  and `sets.ClipSet` had looked only in 0104's folder. That pass gave n = 31
  and 34 in the posture cells, and BirdNET did not reproduce 0104 (0.615
  against 0.857), which is how the gap was found. The paths were fixed to come
  from 0104's manifest, the 81 clips were scanned and embedded, and the whole
  evaluation was rerun once. Only secondary 4 changed. The numbers above are
  from the rerun.
- The CrowGPT extractor was first run with raw codebook indices instead of
  per-codebook vocabulary offsets. That run was stopped and its output
  deleted before anything was scored. After the fix, the extractor's input
  gives the model 5.10 nats per token on a real window, matching its own
  loss path.
- One 3.5-hour begging recording (archive id 28465) finished scanning after
  the first extraction passes. Its spans were added by a resumed run before
  scoring.

## What it changed

- **"Is BirdNET throwing the meaning away?" is answered: no.** Neither a crow
  language model's hidden states nor Perch beat it on any meaning test. The
  bottleneck is the labels and the confounds, not the listener. Future
  context work can keep BirdNET as its feature.
- **CrowGPT block 4 replaces BirdNET as the crowd covariate where it can be
  afforded** (0.845 against 0.806, and 0.80 against 0.73 on begging). It needs
  a GPU pass, so it is for experiments, not the analyzer.
- **Posture versus flight within one predator is now the best-supported
  contrast on the line**, with two representations at 0.85. It goes to
  FUTURE.txt as the confirmatory test to pre-register: it needs fresh clips,
  and the roof-station camera is still the clean source.
- Nothing for the app.
