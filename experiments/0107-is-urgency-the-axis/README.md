# 0107 — Is urgency the axis the owl-versus-hawk result is really about?

**2026-11-21** · CPU · **answer: see Results**

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

_Filled in after `run.py`._
