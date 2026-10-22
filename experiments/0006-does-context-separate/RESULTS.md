# Does the call carry the context?

## Overview

Before building a classifier that says "I see a dog" or "I see a human" from a crow's call, the prior question is whether context is in the signal at all — if crows use the same alarm for a dog and for a person, no amount of data helps. This experiment is fully built and deliberately refuses to run: as of 2026-07-26 the corpus holds only 3 human-labelled calls on kept captures, far below the minimum the script requires, so there is no result yet. What it produced instead is the shape of the collection target: independent recording sessions, not total calls, are the binding constraint.

## In depth

### Method

Human labels only, with context attached to a *label* rather than a capture — a model trained on the analyzer's own guesses learns its bias, and capture-level context credits every situation to every call in the recording.

Two things carry the whole result:

- **Grouped cross-validation, split by capture.** Two caws from the same bout are nearly the same data point. A random split puts near-duplicates on both sides and reports an accuracy that means nothing; every fold here holds out whole recordings.
- **A permutation baseline.** At this sample size "80% accurate" is unreadable. The labels are shuffled 200 times through the same folds and the same class imbalance — only the link to the audio is cut — and the real score is read against that distribution. If it sits inside, there is no signal however good it looked.

The script **refuses to answer below 10 calls across 4 recordings per class.** Reporting a number from four recordings would be the most misleading thing it could do, so it prints what is missing instead.

### Results

Nothing yet. As of 2026-07-26 the corpus holds 3 human-labelled calls on kept captures and 6 context pairings, every one n=1, across 2 recording days.

```
human_gives_food       1 calls across 1 recording(s)
raptor_overhead        0 calls across 0 recording(s)
```

### What it changed

It fixed the shape of the collection target before any of it was collected. The binding constraint is **independent sessions, not total calls** — 500 calls from one crow on one street is close to one data point repeated, and a model trained on it learns that bird, that rooftop, that traffic.

Working numbers, by session rather than by call:

| goal | calls/class | sessions/class |
|---|---|---|
| feasibility — beats chance? | 30–50 | ≥10 |
| weak but real | 100–200 | ≥20 |
| trustworthy | 500+ | ≥30, several sites |

At roughly 2–3 labelled calls per good session, feasibility on two classes is a few weeks of near-daily fieldwork, not an afternoon. The plan is to start with the two *most contrasted* classes rather than three plausible ones: if `human_gives_food` and `raptor_overhead` do not separate, nothing downstream will.

### A note on "threat"

"Threat" cannot be a label that gets collected. The context vocabulary is deliberately descriptive — `dog_visible`, `human_passing` — because an earlier version filed "human walks through" under `threat` and got it wrong for a recordist the birds know, where a human walking through means peanuts. So "threat" has to be a grouping over observed contexts, defined in advance and written down. Better still, it can be treated as a hypothesis to test: does a model trained on `raptor_overhead` and `cat_visible` transfer to `dog_visible`? That is a finding. A threat label is an opinion with extra steps.
