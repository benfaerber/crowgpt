# 0106 — Does the owl-versus-hawk difference replicate outside the two archives?

**2026-11-21** · CPU · **answer: yes — the model frozen on the archives scores 0.753 (p = 0.0024, 95% interval 0.61 to 0.88) on 20 owl and 32 hawk events it had never seen, from other people's phones**

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

**Amendment made after reading the text and before any audio was touched
(same night).** The screen returned 191 descriptions; 90 recordings were coded
(33 owl, 57 hawk). Reading them showed something the plan had not allowed for:
one upload can carry several recordings of the same mob with one shared
description. Counting those as separate recordings would count one event up to
five times. So the unit of analysis is the **event**: a recording's score is
averaged within its event, the 15-per-class floor counts events, and the
bootstrap resamples events. `labels.json` is frozen with this amendment.
Nothing else in the plan changes.

## Results

One run. 90 labelled recordings, all extracted; 61 pass the strict filter,
from 52 separate events.

| | Recordings | Owl / hawk events | AUC | 95% interval | p (two-sided) |
|---|---:|---:|---:|---|---:|
| **Primary: frozen archive model, strict** | 61 | 20 / 32 | **0.753** | 0.61 – 0.88 | **0.0024** |
| Secondary: duty cycle `U` alone, strict | 61 | 20 / 32 | 0.639 | 0.47 – 0.79 | 0.096 |
| Secondary: frozen archive model, non-strict | 82 | 23 / 45 | 0.745 | 0.62 – 0.85 | 0.001 |
| Secondary: in-domain cross-validation | — | — | skipped | needs 30 events a class | — |

Both classes clear the 15-event floor and the interval excludes 0.5, so by the
reading fixed beforehand **the recording-level difference replicates**. A
model that has only ever heard the archive recordings ranks an unseen owl mob
above an unseen hawk mob three times in four, on recordings made by different
people, mostly on phones, with a median length of 24 s against 14 s.

It lands almost exactly where 0102 put it (0.769 cross-validated there, 0.753
transferred here), which is what a real effect does and what an artefact of
one archive's recordists or equipment does not.

Duty cycle alone points the same way (median 0.45 for owl, 0.37 for hawk) but
does not reach significance at this size and sits well below the embedding.
In 0107 the gap between the two was 0.07; here it is 0.11.

## What this does and does not establish

- **Established:** crows mobbing owls *sound different, as a recording,* from
  crows mobbing hawks, and that holds outside the data it was found in. This
  is the first result on this question that was predicted in advance and then
  came out.
- **Not established:** why. 0104 found that with both predators perched the
  difference is at chance on video clips (underpowered), and that perched
  against flying within hawks is the largest contrast in that study. 0107
  found a crowd measure recovers most of it. Posture and crowd size were not
  controlled here, and the descriptions rarely state either. This result is
  fully consistent with "owls sit still and draw a bigger, longer mob".
- **Not established:** anything at the level of a single call. 0103's
  caw-level cross-validation was null.

## Limits

- I coded the labels knowing the hypothesis. They were coded from text alone,
  frozen and committed before any audio was read, and the rule excluded every
  guess ("possibly", "probably", "unseen"), which removed 30-odd candidate
  recordings that might have been real.
- 52 events. The interval is wide: anything from a weak effect to a strong
  one.
- `hawk_mobbing` includes two bald eagle events and one falcon, as it does in
  0102.
- One event can still be one observer's repeated encounters with the same
  birds on different days; events were grouped by upload, not by observer.

## What it changed

- **The owl-versus-hawk recording-level difference is now a replicated
  finding, not a one-archive observation.** That is worth saying plainly,
  because three of tonight's five follow-ups were nulls.
- **The open question is narrowed to one thing: is it the predator, or what
  the predator is doing?** Every remaining confound (recordist, equipment,
  archive, bystander species) has now been tested and has not removed it.
  Posture and crowd size are what is left, and 0104's perched-against-flying
  test within one predator is the experiment that decides it.
- **Corpus rows outside the archives are usable for context work.** 2,475
  American Crow recordings have a description. Only the owl and hawk rows
  have been read; the rest are still unread and can serve as a sealed set for
  the next question (begging, roost, food) if that is declared before anyone
  looks.
- Still nothing for the app. A 0.75 ranking of whole recordings is a research
  result; 0102's verdict table showed what that level of separation does when
  it is asked to label one clip.
