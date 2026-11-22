# 0110 — Which contexts are readable outside the archives?

**2026-11-22** · CPU · **answer: see Results**

## The question

0106 showed one archive-trained contrast (owl against hawk mobbing) holds on
recordings from the rest of the corpus. The archive remarks label more than
mobbing — begging, roosts, food, flight — and nobody knows which of those a
model can read from a whole recording once it leaves the two archives it was
trained on. The rest of the corpus has 2,475 American Crow recordings with an
observer's description. 191 were read for 0106 (the raptor screen). The
others are unread, and this experiment spends them once, on a set of
questions declared here.

## Pre-registration (written and committed before any further description is read)

**Contexts.** Five, each as 0102 coded it: `raptor_mobbing` (0102's
`owl_mobbing` and `hawk_mobbing` together), `begging`, `roost_gathering`,
`food_foraging`, `flight_contact`.

**Frozen models.** Fit once on the Xeno-canto and Macaulay Library
recordings: American Crow, witnessed, context as committed in 0102's
`labels.json`, with at least one crow window free of raptor detections. One
head per context, that context against the other four. Feature and model as
0106: BirdNET mean embedding over clean crow windows (1024-d),
`StandardScaler` + `LogisticRegression(C=0.05, class_weight="balanced")`.
Nothing is tuned on the sealed set.

**Labels, from text alone.** Keyword screens over the observer's
description, then every hit read and coded blind to audio and to any score:

- begging: `beg|juvenile|fledg|young|chick|nestling|baby|immature|fed\b|feeding`
- roost: `roost|flock|murder|hundreds|thousands|dozens|gather|congregat|large group`
- food: `eat|food|forag|feed|carcass|carrion|scaveng|garbage|trash|peanut|roadkill|dump`
- flight: `fly|flew|flying|flight|overhead|fly-?over|flyby`
- number of birds: a digit or number word, `pair|single|lone|alone|several|many|few|group`

A recording gets a context only where the observer states it as something
they saw or heard happening during the recording. Guesses, habits ("they
usually feed here") and app boilerplate are left out. A recording that fits
two contexts is left out. The 90 recordings coded for 0106 enter as
`raptor_mobbing` unchanged; their text has been read, their scores under
these new heads have not been computed. Separately, wherever the text states
how many crows were present or calling, `count_stated` is coded 1, 2 or 3+.
`labels.json` is frozen and committed before any feature is extracted, and
carries ids and codes only.

**Unit.** The event (one upload), as in 0106. Bootstrap intervals resample
observers, not events, so one prolific observer cannot carry a result.

**Primary numbers.** For each context with at least 15 sealed events (and at
least 15 events of other contexts), the ROC-AUC of its frozen head, that
context against all other coded contexts, with a two-sided Mann–Whitney p.
The p-values of the contexts that clear the floor are Holm-corrected as one
family. A context below the floor is reported as uninterpretable and leaves
the family.

**Reading, fixed now.** Holm-corrected p below 0.05 and interval above 0.5:
that context is readable from a whole recording outside the archives.
Otherwise it is not shown to be. No context is "nearly" readable.

**The crowd question, declared now.** If 0109's count head exists:
1. *Does it transfer?* Spearman correlation between the count head's
   recording score and `count_stated` (1, 2, 3+), over events. This is the
   only test of the count head on whole recordings and on other equipment.
2. *How much of each context is crowd?* For each context in the family, the
   AUC of the count score alone, and the AUC of the context head's score
   after the count score is regressed out of it. A context whose head falls
   to chance when crowd is removed was a crowd detector.
3. Duty cycle `U` alone per context, as in 0107.

**Also declared.** The same primary numbers without the raptor-free-window
requirement (all crow windows), as a secondary.

## Results

_Filled in after the single run._
