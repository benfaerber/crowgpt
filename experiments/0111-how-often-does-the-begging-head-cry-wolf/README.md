# 0111 — How often does the begging head cry wolf?

**2026-11-22** · CPU · **answer: too often on hand-labelled archive files (21% false alarms, recall 69%) and rarely on winter phone recordings (4%) — by the rule set in advance, not usable as it stands; on Ben's kept captures it fired on the two labelled begging and none of the other 22**

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

One run. The threshold from the archive alone is `T` = −2.00 (the score 90%
of the archive's begging recordings exceed when held out). At that threshold
13% of the archive's own held-out non-begging recordings also fire, which was
a warning before any test set was opened.

| Test set | What it measures | At `T` | 95% interval | At score 0 |
|---|---|---:|---|---:|
| A: 981 hand-labelled files with no begging flag | false alarms | **21.2%** (208) | 18.8 – 23.9 | 7.7% |
| A: 102 hand-labelled begging files | recall | **68.6%** (70) | 59.1 – 76.8 | 51.0% |
| A: the same, training recordists removed (82) | recall | 67.1% | 56.3 – 76.3 | 50.0% |
| B: 297 winter recordings, rest of the corpus | false alarms | **4.0%** (12) | 2.3 – 6.9 | 1.0% |
| B: 301 June–July recordings | firing rate, not false alarms | 24.9% (75) | 20.4 – 30.1 | 13.3% |
| 0110's 33 begging events | recall | 100% | 89.6 – 100 | 100% |

(B drew 400 recordings a season; about 300 of each have a raptor-free crow
window to score.)

**By the reading fixed beforehand: not usable as it stands.** False alarms in
A are above 15%, and recall in A is just under the 70% asked for. Winter B
passes on its own (4.0%, at or below 5%), and that does not rescue it — the
rule was "either".

False alarms in A by the file's main call type: rattle 31%, soft song 26%,
mob 21%, alert 16%, scold 1 of 11. It is worst on the quiet, close, social
calling — which is what a family with young sounds like when nobody is
begging.

### C — the kept captures (described, not tested)

24 of the 29 have a crow window to score. The head fired on **two, and they
are the two a person labelled begging** (104 and 116). It stayed silent on
all 22 others, including 13 where young were noted as present and the labels
say alarm or call. Two of two and none of 22 is the right answer everywhere
it can be checked; it is also 24 captures from one family over four weeks.

### What the two halves say together

The head does well exactly where it has been tested on whole recordings from
a phone (0110's events, winter B, the kept captures) and badly on A. A is
different in two ways at once, and this run cannot separate them: it is
archive audio, and each file is scored from only the few windows that hold a
hand-labelled second rather than from the whole recording. The summer rate
is six times the winter rate, which is what a head hearing real begging
would do, and also what a head hearing "juvenile voice" would do.

## Limits

- A scores a different object from the one the head was built for. A file
  with one labelled rattle is one window; the head was fit on means over
  whole recordings. Some of A's 21% may be that, and none of it can be
  claimed to be.
- A's "no begging flag" covers the labelled seconds. The 3 s window around
  them can hold begging nobody labelled.
- Winter recordings are a false-alarm set by the calendar, not by ear. They
  are also the season with the least soft family calling, which is where A
  says the head is weakest.
- C is small and from one place.

## What it changed

- **"Begging young present" does not go to the app on this evidence.** The
  rule was written first and the head failed it.
- **It is closer than any other scene-level statement.** Perfect on the kept
  captures, 4% in winter, 100% recall on phones. What stands between it and
  a trial is one number: false alarms on summer family calling with no
  begging, heard by a person. That is a listening pool — the head's summer
  firings from B and an equal number of summer non-firings, graded
  begging / not begging — and it is the next step if this is pursued.
- **The threshold has to come from ordinary recordings, not from the five
  archive contexts.** `T` let through 13% of the archive's own held-out
  negatives. Score 0 cuts A's false alarms to 7.7% at 51% recall; that
  trade is now on record but was not the declared threshold, and choosing it
  here would be tuning on the test set.
- 0110's 0.9996 stands as what it was: begging against four other contexts.
  This is the number it was missing.
