# 0111 — How often does the begging head cry wolf?

**2026-11-22** · CPU · **answer: see Results**

## The question

0110's recording-level begging head — fit on 66 witnessed Xeno-canto and
Macaulay Library recordings, then frozen — ranked 33 begging events from the
rest of the corpus above almost everything else (0.9996). But "everything
else" was mobs, roosts, food and flight. It has never been shown a crow
simply calling. Before "begging young present" can be said to anyone, the
head needs a threshold and a false-alarm rate against ordinary recordings.

## Pre-registration (written and committed before any score below exists)

**The head.** 0110's `ArchiveHeads("emb_clean", "has_clean")`, begging
against the other four contexts, used as it is. Nothing is refit.

**The threshold, from the archive alone.** Five-fold cross-validation of the
same model on its own training recordings, grouped by recordist; `T` is the
out-of-fold score that 90% of the archive's begging recordings exceed. `T` is
then applied to the frozen head's score everywhere. The model's own boundary
(score 0) is reported beside it as a secondary.

**Three test sets.**

*A — hand-labelled, same kind of audio.* The hand-reviewed American Crow
segments (0109's cache). Per file, the mean embedding of the windows that
hold a labelled segment. A file is begging if any segment carries the
`begging` flag, and non-begging if none does. Files that are among the
head's training recordings are removed. This is a human-truth false-alarm
rate against alert, mob, rattle and soft-song calling, and a recall.

*B — winter, other people's phones.* 400 recordings drawn at random
(seed 0) from American Crow recordings in the rest of the corpus dated
November to February, when there are no begging young; and 400 from June and
July for comparison. Anything coded in 0110 is excluded from the draw. The
winter firing rate is a false-alarm rate with the calendar as ground truth.
The summer rate is not a false-alarm rate — some of those recordings will
hold begging nobody described — and is reported only to see whether the head
fires more when young are about.

*C — Ben's kept captures.* All 29, with the human call-type labels they
carry. Described, not tested: two of them are labelled begging, which is too
few for a rate. Every one is from late July or August with young present, so
this is the hardest and most relevant set, and the smallest.

**Primary numbers.** At `T`: the false-alarm rate in A, the false-alarm rate
in winter B, and the recall in A. Each with a 95% Wilson interval. Recall on
0110's 33 begging events at `T` is reported too; those events have been
scored before but `T` has not.

**Reading, fixed now.**
- False alarms at or below 5% in both A and winter B, recall 70% or more in
  A and on 0110's events: a candidate for a trial behind a flag, with C
  looked at by ear first.
- False alarms above 15% in either: not usable as it stands.
- In between: the threshold needs calibrating on ordinary recordings, which
  this experiment then supplies at the cost of needing a fresh test set.

**Secondary, declared now.** Recall in A with every recordist who
contributed a training begging recording removed. False alarms in A split by
call type of the file. The same three numbers at score 0.

## Results

_Filled in after the single run._
