# Does the call carry the context?

**Status: waiting on data.** Ready to run the moment there is enough.

## Why

Before building an "I see a dog" / "I see a human" classifier, the prior
question is whether context is in the signal at all. If crows use the same alarm
for a dog and for a person, no amount of data helps — you would be predicting
the world from something that does not encode it, and every accuracy number
would be measuring the recordist's sampling rather than the bird.

## Method

Human labels only, with context attached to a *label* rather than a capture — a
model trained on the analyzer's own guesses learns its bias, and capture-level
context credits every situation to every call in the recording.

Two things carry the whole result:

**Grouped cross-validation, split by capture.** Two caws from the same bout are
nearly the same data point. A random split puts near-duplicates on both sides
and reports an accuracy that means nothing; every fold here holds out whole
recordings.

**A permutation baseline.** At this sample size "80% accurate" is unreadable.
The labels are shuffled 200 times through the same folds and the same class
imbalance — only the link to the audio is cut — and the real score is read
against that distribution. If it sits inside, there is no signal however good it
looked.

**It refuses to answer below 10 calls across 4 recordings per class.** Reporting
a number from four recordings would be the most misleading thing this script
could do, so it prints what is missing instead.

## Result

Nothing yet. As of 2026-07-26 the corpus holds 3 human-labelled calls on kept
captures and 6 context pairings, every one n=1, across 2 recording days.

```
human_gives_food       1 calls across 1 recording(s)
raptor_overhead        0 calls across 0 recording(s)
```

## What it changed

Fixed the shape of the collection target before any of it was collected. The
binding constraint is **independent sessions, not total calls** — 500 calls from
one crow on one street is close to one data point repeated, and a model trained
on it learns that bird, that rooftop, that traffic.

Working numbers, by session rather than by call:

| goal | calls/class | sessions/class |
|---|---|---|
| feasibility — beats chance? | 30–50 | ≥10 |
| weak but real | 100–200 | ≥20 |
| trustworthy | 500+ | ≥30, several sites |

At roughly 2–3 labelled calls per good session, feasibility on two classes is a
few weeks of near-daily fieldwork, not an afternoon.

Start with the two *most contrasted* classes rather than three plausible ones.
If `human_gives_food` and `raptor_overhead` do not separate, nothing downstream
will.

## A note on "threat"

It cannot be a label that gets collected. The context vocabulary is deliberately
descriptive — `dog_visible`, `human_passing` — because an earlier version filed
"human walks through" under `threat` and got it wrong for a recordist the birds
know, where a human walking through means peanuts.

So "threat" has to be a grouping over observed contexts, defined in advance and
written down. Better still, treat it as a hypothesis to test: does a model
trained on `raptor_overhead` and `cat_visible` transfer to `dog_visible`? That
is a finding. A threat label is an opinion with extra steps.
