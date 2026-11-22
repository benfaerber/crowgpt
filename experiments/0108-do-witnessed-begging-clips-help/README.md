# 0108 — Do the witnessed archive begging clips improve the begging class of the shipped American Crow head?

> **Pre-registration (written before any feature was extracted or any model
> fitted for this experiment).** Everything in "Protocol" was fixed first.
> Anything reported that is not named there is labelled **exploratory**.

## The question

Experiment 0102 found 77 American Crow recordings in the Xeno-canto and
Macaulay Library remarks where the recordist says they *witnessed* begging, and
its README called them "immediately usable to bolster the weak begging class".
`FUTURE.txt` carries that as a to-do. Nobody has tested it.

The shipped head (`pipelines/training/models/american-crow/`, a one-vs-rest
`MultiLabelHead` on `birdnet_pooled_mean_std_max`) was trained on 2,654 rows:
2,494 hand-reviewed crow-tools segments and 160 archive clips. 311 of those
rows are begging (307 crow-tools, from 129 recordings, and 4 archive), scored
at **0.914** grouped one-vs-rest AUC in its own `metrics.json`.

Two things make the 77 clips less of a free lunch than they look:

- **They are labelled per recording, not per span, and nobody has listened.**
  A remark that says "fledgling begging from parents" covers minutes of audio in
  which an adult also calls. Every window taken from such a clip is a guess.
- **Many are not new.** crow-tools was labelled from the same two archives, so a
  clip can already be in the training set under its reviewed labels.

## Protocol

**Evaluation rows.** The 2,654 rows the shipped head was trained on, and only
those. The weakly labelled additions are never scored, in any fold.

**Primary metric.** Begging one-vs-rest ROC-AUC, recording-grouped 5-fold
(`StratifiedGroupKFold(shuffle=True, random_state=0)`, `StandardScaler` +
balanced `LogisticRegression(max_iter=5000)`) — the shipped head's own metric
and the protocol of `experiments/lib/probe.py`. The baseline arm must reproduce
0.914 before anything else is believed.

**Comparison.** Same folds, same test rows. The candidate arm adds the weak
begging rows to each fold's *training* side only.

**Decision rule.** The clips "help" if the primary rule's begging AUC rises by
at least **+0.005** at seed 0 **and** the paired difference is positive in at
least 8 of 10 seeds (0–9). Anything else is recorded as a null.

**Guard.** Added rows are labelled `{begging}` and so are negatives for the
other four classes, exactly as `MultiLabelHead.fit` would treat them. The mean
one-vs-rest AUC over `alarm call`, `call`, `song`, `flight call` must not fall
by more than **0.005**, and no single class by more than **0.010**, at seed 0.
A candidate that helps begging and fails the guard does not pass.

**Secondary (reported, not decisive).** Begging average precision under the
same folds.

**Which clips.** Witnessed American Crow `begging` rows in
`experiments/0102-archive-remarks-semantics/labels.json`. A clip whose
recording is already a crow-tools recording is **excluded** from the additions
— its reviewed segments are in the baseline already. The overlap is reported.

**Leak control.** Within a fold, an added clip is dropped from training when
its recordist also recorded any test-fold recording (recordist read from
`data/corvid.db`). The 160 archive rows carry no recording id in their cache,
so they cannot be matched; that gap is stated in the results.

**How a clip becomes rows.** crow-tools rows are a single 3 s BirdNET window
run through `pooling.pool` (std block 0). Added rows are built the same way so
the feature is the same kind: one row per window, at most **8 windows per
recording**, evenly spaced in time among the eligible windows, so one long
recording cannot swamp the class.

**Selection rules — two, fixed here.**

1. **PRIMARY — all crow windows.** Eligible = any 3 s window where BirdNET
   (`min_conf=0.05`) hears a corvid at ≥ 0.25, the same gate 0102 used.
2. **Secondary — crow windows the head already calls begging.** Eligible =
   rule 1 **and** P(begging) ≥ 0.5 from the *fold's own* baseline model, fitted
   on that fold's training rows only, so the filter never sees a test label.

**Field check (exploratory, by construction tiny).** Human `begging` rows in
the `labels` table of the field database, against the other human call-type
labels there, scored by a baseline head and a candidate head each fitted on all
their rows. Counts are reported with the number.

**Audit list.** The 20 added clips with the lowest mean P(begging) from a
candidate head that was not trained on that clip (5-fold over added clips), by
corpus recording id, so a by-ear audit can start with the likeliest mislabels.

**What this experiment will not do.** It does not replace or modify the shipped
`calltype_clf.joblib`. The candidate head is written under
`data/experiments/0108-begging/` only.

## Results

**Verdict: neither rule passes. The clips nudge begging up and cost the alarm
class more than they give.** The shipped head stays as it is.

### What the 77 clips actually are

| | Clips |
|---|---:|
| Witnessed begging clips in 0102's labels | 77 (74 Macaulay Library, 3 Xeno-canto) |
| Already a crow-tools recording, so excluded | 22 |
| New | 55, from 49 recordists |
| New with at least one crow window (≥ 0.25) | 46 |

- **Over a quarter were never new.** 22 of 77 are recordings crow-tools has
  already reviewed segment by segment.
- **"451 minutes" is mostly two recordings.** Recordings 28465 and 28466 run
  213 and 116 minutes, 73% of all the audio. The per-recording cap of 8 windows
  is what stops them being the whole class.
- **Recordist leak control was possible for crow-tools only.** 1,187 of its
  1,195 recordings resolve to a recordist in `data/corvid.db`. The 160 archive
  rows carry no recording id and could not be matched (4 begging rows among
  them).
- After the cap the full fit adds 296 rows from 46 clips under rule 1 and 226
  rows from 44 clips under rule 2, against 311 reviewed begging rows.

### Primary metric and guard (seed 0, 2,654 evaluation rows, 311 begging)

The baseline arm scores 0.9131, against 0.914 in the shipped `metrics.json`.

| Rule | Begging AUC | Gain | Seeds positive (of 10) | Mean gain, 10 seeds | Begging AP | Helps? | Guard |
|---|---:|---:|---:|---:|---:|---|---|
| Baseline | 0.9131 | — | — | — | 0.778 | — | — |
| **1. all crow windows (PRIMARY)** | 0.9195 | +0.0065 | 9 | +0.0047 | 0.784 | yes | **fails** |
| 2. head says begging (secondary) | 0.9173 | +0.0042 | 10 | +0.0025 | 0.790 | no (< 0.005) | **fails** |

Guard, drop in one-vs-rest AUC at seed 0 (limits: mean 0.005, any class 0.010):

| Rule | alarm call | call | song | flight call | Mean |
|---|---:|---:|---:|---:|---:|
| 1. all crow windows | **0.0146** | −0.0003 | −0.0014 | **0.0189** | **0.0079** |
| 2. head says begging | 0.0037 | −0.0005 | −0.0006 | **0.0173** | 0.0050 |

- **Rule 1 clears the begging bar and fails the guard**, on alarm call, flight
  call and the mean. By the pre-declared rule it does not pass.
- **Rule 2 is a null on its own terms**: +0.0042 is under the +0.005 bar, and it
  fails the guard on flight call.

### Exploratory: which guard failures are real (`guard_seeds.py`, seeds 0–9)

Not part of the protocol; the verdict above does not depend on it.

| Rule | alarm call drop (mean, range) | flight call drop (mean, range) |
|---|---|---|
| 1. all crow windows | 0.0149 (0.0116 to 0.0181), all 10 seeds | 0.0011 (−0.0316 to 0.0358), 5 seeds |
| 2. head says begging | 0.0031 (0.0014 to 0.0044), all 10 seeds | −0.0032 (−0.0488 to 0.0324), 4 seeds |

- **The alarm-call cost of rule 1 is real.** It is there in every seed and is
  over twice the begging gain. The plain reading is the one the protocol
  warned about: crow windows in a "begging" recording are often the adult, and
  labelling them not-alarm teaches the alarm model something false.
- **The flight-call failure is seed noise.** With 40 positives the class swings
  by ±0.03 between seeds with no change in the data, so a seed-0 guard on it
  measures the seed. A future guard should average seeds for that class.
- **Filtering removes most of the alarm cost and most of the gain with it.**

### Exploratory: the field check has nothing left to give

68 human-labelled field spans across 20 captures scored (77 spans in the
table; `not_a_crow` and `unsure` are not call types and were left out). 11 are
begging, all from **two captures (104 and 116)**.

| Head (fitted on all its rows) | Begging vs other AUC | Begging spans ≥ 0.5 | Other spans ≥ 0.5 |
|---|---:|---:|---:|
| Baseline | 1.000 | 10 of 11 | 0 of 57 |
| Rule 1 | 0.998 | 11 of 11 | 1 of 57 |
| Rule 2 | 1.000 | 10 of 11 | 0 of 57 |

The baseline already ranks every field begging span above every other span.
Two captures cannot show an improvement and do not show a problem.

### Exploratory: where the head hears begging in the new clips

Of 7,495 windows in the 55 new clips, 1,279 pass the crow gate. The baseline
head calls 486 of those begging — and also calls **280 windows begging that
BirdNET does not hear as a crow at all**. That fits the note in `FUTURE.txt`
that BirdNET under-detects fledglings, and it means the crow gate both rules
share may be discarding the very windows that hold the begging. Not tested
here: the protocol fixed the gate.

### Audit list — the 20 added clips the candidate is least sure about

Mean P(begging) over a clip's added windows, from a rule-1 head that never saw
that clip. Ids are `recordings.id` in `data/corvid.db`. Start at the top.

| Recording id | Archive ref | Mean P(begging) | Windows |
|---:|---|---:|---:|
| 27016 | Macaulay 637282113 | 0.001 | 4 |
| 26888 | Macaulay 161788611 | 0.087 | 6 |
| 25568 | Macaulay 320277101 | 0.089 | 8 |
| 27337 | Macaulay 637883814 | 0.136 | 8 |
| 26887 | Macaulay 163795651 | 0.259 | 5 |
| 27534 | Macaulay 619230987 | 0.301 | 8 |
| 28361 | Macaulay 165316211 | 0.437 | 8 |
| 23644 | Macaulay 64132831 | 0.499 | 8 |
| 27083 | Macaulay 106330461 | 0.520 | 6 |
| 28466 | Macaulay 236291 | 0.542 | 8 |
| 29697 | Macaulay 322204051 | 0.571 | 8 |
| 258 | Xeno-canto 109698 | 0.624 | 7 |
| 22816 | Macaulay 660247361 | 0.669 | 8 |
| 28465 | Macaulay 236292 | 0.689 | 8 |
| 27129 | Macaulay 659770283 | 0.693 | 8 |
| 22594 | Macaulay 203928771 | 0.729 | 3 |
| 28450 | Macaulay 32684721 | 0.731 | 7 |
| 23794 | Macaulay 643967334 | 0.749 | 8 |
| 30367 | Macaulay 246445461 | 0.761 | 8 |
| 29681 | Macaulay 345628801 | 0.847 | 3 |

## Not verified

- Nobody has listened to any added window. Every statement about what the
  windows contain is inferred from scores.
- The 0.9131 against 0.914 baseline difference was not traced. This script
  holds features as float32; that is the likely cause and it was not checked.
- Whether the 22 excluded clips' *unreviewed* windows would add anything.
- The two candidate heads in `data/experiments/0108-begging/` were written and
  never loaded through `analyzer/birdnet.py`.

## What it changed

- **Nothing ships.** `calltype_clf.joblib` is untouched, and the to-do in
  `FUTURE.txt` to fold these clips into the head should not be done as written:
  used as recording-level labels they buy +0.006 begging AUC for −0.015 on
  alarm call, the class the app reports most.
- **0102's "77 clips, 451 minutes, immediately usable" needs three
  corrections**: 22 are already in the training set, two recordings hold 73% of
  the minutes, and the usable new material is 46 clips.
- **The route that could still work is span-level labels, not more windows.**
  The audit list above is where a by-ear sitting should start, through the
  listening-pool system. Reviewed begging spans from the 46 new clips could go
  through `pipelines/ingest/` like any crow-tools segment, with no guard cost.
- **A cheaper engineering option exists and was not tested**: `MultiLabelHead`
  fits each class separately, so weak begging rows could be given to the
  begging model alone and withheld from the others. That removes the alarm
  cost by construction; it needs a trainer that accepts "unknown" for a class.
- **The seed-0 guard is too noisy for flight call** (40 positives). Later
  experiments on this head should average the guard over seeds.
