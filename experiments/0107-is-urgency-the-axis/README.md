# 0107 — Is urgency the axis the owl-versus-hawk result is really about?

**2026-11-21** · CPU · **answer: not with this measure — duty cycle orders human-sorted calls and scores 0.71 on owl versus hawk by itself, but a roost scores as high as an owl mob, so it measures how much crow sound there is, not how urgent it is**

## The question

0102 found that recordings of crows mobbing owls can be told from recordings
of crows mobbing hawks (0.769). 0103 could not show that the difference lives
in the individual caw, and found owls are nearly always perched and hawks
mostly flying. Everything so far fits "how hard are they mobbing" at least as
well as "which predator". If that is the right reading, a single graded
measure of urgency should (a) order calls that people have already sorted by
arousal, (b) carry most of the owl-versus-hawk separation on its own, and
(c) not simply be a count of how many crows are calling.

## Pre-registration (written before any of this was measured)

**The measure.** `U` = duty cycle of the 700–4500 Hz envelope: the fraction of
10 ms frames above 0.25 of the range between the whole file's 10th and 98th
percentiles (`CallingIntensity` from 0105, unchanged). One number, no labels,
no BirdNET. 0105 is the reason it is duty cycle and not a caw count: a peak
counter saturates when birds overlap.

**A. Human-sorted segments (primary).** The crow-tools labels are one-second
segments a person reviewed and flagged. Take segments carrying exactly one of
`softSong`, `alert`, `mob` and none of the other call flags (1,505 segments,
884 files). Predicted order of arousal, fixed now: **softSong < alert < mob**.
Primary number: Spearman ρ between that rank (0, 1, 2) and `U` over the
segment's own second, with a 95% interval from 2,000 bootstrap resamples of
whole files. It passes if the interval excludes zero **and** the three medians
are in the predicted order.

**A-control (declared now).** The same on segments flagged `crowCount = 1`
only (417 / 424 / 323). If the order holds across all segments and vanishes
for single birds, `U` is counting crows, not urgency.

**B. How much of owl versus hawk is `U`?** On 0102's strict set (144
recordings, recordist-grouped five-fold, the 0102 splits): the AUC of `U`
alone, computed over the whole recording, and the AUC of the BirdNET mean
embedding after `U` is regressed out of every dimension inside each fold.
Reading fixed now: `U` alone ≥ 0.70 and residual ≤ 0.60 means urgency carries
the result; residual ≥ 0.65 means something this measure does not capture
remains. Between the two is undecided.

**C. The counterexample (declared now).** A roost has hundreds of crows and no
threat. If the median `U` of witnessed `roost_gathering` recordings is at or
above that of `owl_mobbing`, `U` is a measure of crowd, not urgency, whatever
A says.

**Not tested, and why.** Ben's kept field captures carry `crows_agitated` on
two recordings; that is not a sample. The 2023+ holdout from 0103 is spent and
is not used here.

## Results

### A. Human-sorted segments — passes

| | softSong | alert | mob | Spearman ρ (95% interval) | In predicted order? |
|---|---:|---:|---:|---:|---|
| All segments (1,505 in 884 files), median `U` | 0.19 | 0.26 | 0.43 | **0.29** (0.22 to 0.35) | yes |
| Single-crow segments (1,164 in 663 files), median `U` | 0.19 | 0.25 | 0.32 | **0.17** (0.09 to 0.25) | yes |

The interval excludes zero and the medians are in the predicted order, so the
primary test passes. It is a weak ordering, not a classifier: as a
two-way split `U` gives 0.58 for alert against softSong and 0.64 for mob
against alert.

**The control cuts it nearly in half.** With one crow in the segment ρ falls
from 0.29 to 0.17 and mob against alert falls from 0.64 to 0.57. A good part
of what `U` sees in a mob is that there are more birds in it.

### B. Owl versus hawk — undecided by the rule, and informative anyway

146 strict recordings (79 owl, 67 hawk, 116 recordists), 0102's splits.

| | AUC |
|---|---:|
| `U` alone (median 0.45 owl, 0.29 hawk) | **0.709** |
| BirdNET mean embedding | 0.778 |
| BirdNET mean embedding with `U` regressed out in-fold | **0.723** |

`U` alone clears the 0.70 line, and the residual stays above 0.65. By the
reading fixed beforehand that is "something this measure does not capture
remains": one number recovers most of the separation, yet taking it away
costs the embedding only 0.055. The two are largely redundant routes to the
same answer rather than one explaining the other.

### C. The counterexample — fails

| Witnessed context | n | Median `U` | Middle half |
|---|---:|---:|---|
| roost_gathering | 49 | **0.46** | 0.25 – 0.61 |
| owl_mobbing | 120 | **0.42** | 0.25 – 0.57 |
| mammal_scold | 9 | 0.41 | 0.28 – 0.54 |
| hawk_mobbing | 133 | 0.28 | 0.21 – 0.40 |
| begging | 66 | 0.19 | 0.14 – 0.27 |
| territorial_agonistic | 44 | 0.19 | 0.11 – 0.35 |
| human_disturbance | 17 | 0.15 | 0.11 – 0.32 |
| rattle_social | 36 | 0.14 | 0.09 – 0.23 |
| food_foraging | 36 | 0.13 | 0.09 – 0.22 |
| flight_contact | 19 | 0.13 | 0.10 – 0.21 |

A roost — hundreds of birds, no threat — has a median `U` at or above an owl
mob. By the rule set beforehand, **`U` is a measure of crowd, not urgency.**
Human disturbance, which the recordists described as alarm, sits with the
quiet social contexts.

(The table counts only rows whose context is in the committed
`labels.json`. The shared 0102 cache had grown rows that the label file does
not carry — 125 extra `food_foraging` among them — and the first run of this
script counted those. Parts A and B were unaffected.)

## What this says about the reframing

The idea was to stop claiming "which predator" and report "how urgent"
instead. This experiment says that is the right direction and the wrong
instrument:

- A single label-free number does carry most of what the owl-versus-hawk
  classifier found (0.71 against 0.78). The predator result is, to a first
  approximation, an amount-of-calling result.
- That number cannot tell an owl mob from a roost, and loses about half its
  grip when only one bird is calling. It is measuring how much crow sound
  fills the recording — birds times calling — and urgency is at most one
  factor in that product.
- So "urgency" is not yet something this project can measure, and it should
  not be shown to anyone under that name. "Calling density" is what it is.

## Limits

- `U` scales with the file's own loudness range, so a recording that is
  uniformly dense reads lower than it should. That works against roosts, and
  they still came out on top.
- The arousal order softSong < alert < mob is my reading of the flag names,
  fixed beforehand; nobody ranked those segments for arousal.
- B's thresholds were set before looking but are arbitrary, and the result
  landed in a region the rule had to call by its second clause.

## What it changed

- **The owl-versus-hawk finding is restated**: recordings of owl mobs hold
  more crow sound than recordings of hawk mobs, and a duty-cycle number
  recovers most of the classifier's separation. Nothing here supports calling
  it a different call.
- **No urgency readout goes into the app or the analyzer.** The measure that
  was the obvious candidate fails its own counterexample.
- **What an urgency measure would need** is to hold the number of birds
  fixed. The crow-tools labels carry a human `crowCount` on every segment
  (1,909 single-bird, 329 two, 248 four-or-more), which is enough to train a
  per-segment crow-count estimate and then ask whether anything about
  *single-bird* calling still orders alert below mob. That is the next
  experiment on this line, and it needs no new data.
- 0105's hint is borne out in one respect: duty cycle is the more usable of
  the two envelope measures. It is still not urgency.
