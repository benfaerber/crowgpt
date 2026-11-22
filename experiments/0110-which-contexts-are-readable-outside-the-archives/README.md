# 0110 — Which contexts are readable outside the archives?

**2026-11-22** · CPU · **answer: all five clear the bar set in advance, very unequally — begging is near-perfect (0.9996, 11 observers), roost 0.78 and raptor mobbing 0.73 are solid, food 0.65 and flight 0.63 are weak; roost is mostly crowd, the others are not**

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

One run. 1,428 descriptions passed the screens and were coded by a second
agent that was given the codebook and the text and nothing else; 73 rows were
audited against the text and none changed. 264 recordings got a context (the
90 from 0106 and 174 new), and 230 of them have a raptor-free crow window:
204 events from 137 observers.

### Which contexts are readable

| Context | Archive recordings trained on | Sealed events (observers) | AUC | 95% interval | Holm p |
|---|---:|---:|---:|---|---:|
| `begging` | 66 | 33 (11) | **0.9996** | 0.999 – 1.0 | < 0.00001 |
| `roost_gathering` | 49 | 47 (44) | **0.776** | 0.69 – 0.86 | < 0.00001 |
| `raptor_mobbing` | 253 | 67 (47) | **0.731** | 0.62 – 0.83 | < 0.00001 |
| `food_foraging` | 36 | 22 (20) | 0.650 | 0.52 – 0.77 | 0.026 |
| `flight_contact` | 19 | 35 (31) | 0.634 | 0.53 – 0.74 | 0.026 |

Every context clears the 15-event floor, every Holm-corrected p is below
0.05 and every interval is above 0.5. By the reading fixed beforehand, **all
five are readable from a whole recording outside the archives.** They are not
equally readable, and the table should not be flattened into "five yeses":

- **Begging transfers almost perfectly.** One begging event of 33 is outranked
  by anything else. Twenty of the 37 begging recordings are one observer's,
  so the honest sample is 11 observers; with one value per observer (checked
  after the run, not declared) it is 1.0, p = 4 × 10⁻⁸.
- **Roost and raptor mobbing are solid, mid-0.7s**, each from more than 40
  observers.
- **Food and flight pass and are weak.** Lower bounds of 0.52 and 0.53.
- Without the raptor-free-window requirement (declared secondary) nothing
  moves except flight, which rises to 0.694.

### How much of each is crowd

| Context | Count head alone | Duty cycle alone | Context head | Context head, count removed |
|---|---:|---:|---:|---|
| `begging` | 0.184 | 0.347 | 0.9996 | 0.992 (0.98 – 1.0) |
| `roost_gathering` | **0.789** | 0.681 | 0.776 | 0.699 (0.61 – 0.79) |
| `raptor_mobbing` | 0.603 | 0.635 | 0.731 | 0.703 (0.60 – 0.80) |
| `food_foraging` | 0.308 | 0.399 | 0.650 | 0.619 (0.49 – 0.74) |
| `flight_contact` | 0.411 | 0.280 | 0.634 | 0.622 (0.51 – 0.73) |

- **Roost is mostly a crowd.** The count head alone finds roosts as well as
  the roost head does. Something is left when the count is removed (0.70),
  but "roost" as read here is largely "many crows".
- **Raptor mobbing is not mostly a crowd.** The count head alone manages
  0.60, and removing it costs the mobbing head 0.03. Against other things
  crows do, a mob sounds like a mob for some reason other than head count.
  (This is mobbing against other contexts. It says nothing new about owl
  against hawk, where 0107 found crowd explains most of it.)
- **Begging, food and flight are the few-bird contexts** (count head well
  below 0.5), and removing the count does not help or hurt begging.
- **Food does not survive.** With the count removed its interval includes
  0.5.

### Does the count head transfer to whole recordings?

260 events state how many crows there were (23 one, 31 two, 206 three or
more). The count head's score rises with the stated number: Spearman 0.348
(0.25 – 0.44), p < 0.00001. One against more: 0.733 (0.64 – 0.82), on only 23
single-crow events. Duty cycle: 0.297. **It transfers, weakly** — to other
people's phones, to whole recordings, against a number an observer typed.

## Limits

- **"Other" here means the other four contexts, not ordinary calling.** A
  head that separates begging from mobs, roosts, food and flight has not been
  shown to separate it from a crow cawing on a wire. No false-alarm rate on
  everyday recordings follows from any number above.
- Removing the count means regressing out a score that itself only
  correlates 0.35 with the stated number. It removes some of the crowd, not
  all of it; "not mostly crowd" is as far as that licenses.
- Begging is 11 observers. Food is 22 events.
- The coder's settled conventions are in `labels.json`. One matters: a bare
  "large flock" or "hundreds" was coded `roost_gathering`, which builds
  crowd size into that label by definition.
- Mobbing of anything but a raptor, and everything territorial or social,
  was not coded.

## What it changed

- **Recording-level context is real outside the archives for three things:
  begging young, a mob on a raptor, and a large gathering.** That is the
  first evidence in the project that a description of the scene, as opposed
  to a call-type label on a window, can be backed with numbers from
  equipment and people the model never saw.
- **Begging is the one to act on first, and the next test is already
  defined:** the same frozen begging head against recordings whose
  descriptions state nothing in particular — everyday calling — to get a
  false-alarm rate. Until that exists it is not an app feature. (0108 found
  these same archive clips do not improve the shipped window-level head;
  that still stands. This is a different, recording-level reading.)
- **Roost should be reported as "many crows", not as a context**, unless a
  later test separates the two.
- **Food and flight are dropped as candidates** for now: weak, and food does
  not survive the crowd control.
- **The count head is carried forward as the crowd covariate** (0109), with
  its transfer measured at ρ = 0.35 rather than assumed.
- **The descriptions are spent as a sealed set for these five contexts.**
  About 1,050 that matched no screen remain unread, and are by construction
  the ones that say little.
