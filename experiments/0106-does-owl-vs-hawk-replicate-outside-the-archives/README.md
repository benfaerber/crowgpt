# 0106 — Does the owl-versus-hawk difference replicate outside the two archives?

**2026-11-21** · CPU · **answer: see Results**

## The question

0102's recording-level result (0.769 on strict owl versus hawk) was found,
controlled and re-tested entirely inside the Xeno-canto and Macaulay Library
recordings, and 0103 spent the only sealed part of them. The corpus holds
another 8,986 American Crow recordings that arrived through the corpus
tooling, made by different people on different equipment — mostly phones.
Until tonight they carried no free text. Descriptions for them now sit in
`data/cache/descriptions/descriptions.jsonl`; 2,475 are non-empty. Nobody
working on this question has read them. That makes them a test set of a kind
the archives can no longer supply.

## Pre-registration (written and committed before any description was read)

**Sealed set.** Every American Crow recording outside the two archives. No
model, threshold or feature choice below may change after labelling starts.

**Labels, from text alone.** A keyword screen over the observer's own
description for owl, hawk, eagle, falcon, raptor and the four-letter banding
codes, then each hit read and coded with 0102's rule: `owl_mobbing` or
`hawk_mobbing` only when the observer says they saw the predator or the
mobbing, and `pred_vocal` when the text says the predator called. Coding is
done blind to audio and to any model score, and `labels.json` is frozen
before a feature is extracted. Comments by other people are not used to
assign a label. The label file in this folder carries the corpus recording
id and the code only; the text stays under `data/`.

**Strict filter, as 0102.** `pred_vocal` false, BirdNET raptor confidence
below 0.05 everywhere, and at least one crow window (≥ 0.25) free of raptor
detections. Features come from 0102's own `process_one`, unchanged.

**The model is frozen.** Fit once on all 146 strict archive recordings
(79 owl, 67 hawk): BirdNET mean embedding over clean crow windows (1024-d),
`StandardScaler` + `LogisticRegression(C=0.05, class_weight="balanced")` —
0102's mean-only arm, the one 0103 and 0104 also carried forward.

**Primary number.** ROC-AUC of that frozen model on the sealed strict set,
computed once, with a two-sided Mann–Whitney p and a 95% bootstrap interval
over recordings.

**Reading, fixed now.**
- Fewer than 15 strict recordings in either class: uninterpretable, and
  reported as such.
- Interval excludes 0.5: the recording-level difference replicates on
  different recordists and equipment.
- Interval includes 0.5: it does not replicate at this n.
- Either way this says nothing about *why*. 0104 and 0107 found posture and
  crowd size are enough to produce the difference, and neither is controlled
  here.

**Secondary, declared now.** (1) Duty cycle `U` from 0107 alone, same
direction (owl higher). (2) The same frozen model on the non-strict set.
(3) A model fit on the sealed set under five-fold observer-grouped
cross-validation, if both classes reach 30, to compare an in-domain score
with the transferred one.

## Results

_Filled in after the single run._
