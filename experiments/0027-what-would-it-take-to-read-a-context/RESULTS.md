# What would it take to read a context off a call?

## Overview

Experiment 0006 asked whether the situation a crow calls in (a stranger approaching, a known human passing, and so on) can be read from the call itself, and correctly refused to answer: the corpus held only 3 labelled calls with context. Its instruction — "collect more" — was not enough to plan field sessions around, so this experiment measured exactly what is missing. The answer: four more mornings on the right two situations, not more calls. No context pair is answerable yet — the bottleneck is separate recording days (captures), not call counts — and the experiment re-runs itself as the corpus grows, turning into a real result the moment a pair clears the bar, with no new code.

## In depth

### Why re-ask

Two months of field collection were about to happen, and the difference between sessions that make this question answerable and sessions that do not is *which* situation gets recorded and on *how many separate days*. This experiment says exactly that — the half 0006 left out.

### Where the corpus is

Kept captures only — the ★ Keep flag is the only thing separating real field observations from the seeded archive clips and test uploads that dominate the corpus, so every number here is about the field corpus.

| | |
|---|---|
| labels on kept audio | 42 over 10 captures, 6 days |
| `alarm call` | 23 calls / 6 captures |
| `begging` | 11 calls / 2 captures |
| `call` | 5 calls / 5 captures |
| `alarm call` with a context chip | 22 calls / 5 captures |

`alarm call` is the only type with enough context to be worth testing, and that is where the correction is: it clears the bar for *carrying* context, but no pair of contexts within it clears the bar for a *contrast*. The best pairs sit at 2 captures a side against a bar of 4. "Alarm call has 23 labelled calls" reads like enough and is not — which is why this was worth measuring precisely rather than reasoning about.

### The bar, and why it is about captures

10+ calls across 4+ separate captures, per side — 0006's bar, unchanged so the two are comparable. Two caws from one bout are nearly the same data point, so a fold that splits them reports an accuracy about the recording rather than the situation; every fold holds out a whole capture. A call can carry several chips at once, so a pairwise test uses only calls carrying exactly one of the two — otherwise it scores a label against itself.

### Result: no pair is answerable

The closest pairs (calls/captures per side):

| context A | context B | A | B | needs |
|---|---|---|---|---|
| human_approaching | known_passing | 9/2 | 8/2 | 2 more captures each |
| human_known | known_passing | 9/2 | 8/2 | 2 more captures each |
| human_known | stranger_passing | 9/2 | 5/1 | 2 and 3 more captures |
| known_passing | loud_worker | 8/2 | 8/1 | 2 and 3 more captures |
| caller_stays | human_passing | 17/4 | 3/1 | 3 more captures on B |

No accuracy is reported, on purpose — a number from this much data would be noise wearing a result's clothes.

Per context, calls are mostly fine and captures are not:

| context | calls | captures | needs |
|---|---|---|---|
| crows_still | 19 | 4 | ready |
| caller_stays | 18 | 4 | ready |
| human_approaching | 9 | 2 | 2 more captures |
| human_known | 9 | 2 | 2 more captures |
| known_passing | 8 | 2 | 2 more captures |
| loud_worker | 8 | 1 | 3 more captures |
| stranger_passing | 5 | 1 | 3 more captures |
| human_gives_food | 2 | 2 | 2 more captures, 8 more calls |

The two "ready" rows do not rescue the table: `crows_still` and `caller_stays` describe the caller's own behaviour rather than situations, so contrasting them with each other would not mean anything.

### What the answer changed

- **The collection plan for the next two months.** Not "record more", but: get `human_known`, `known_passing` and `human_approaching` onto two more mornings each, and `loud_worker` and `stranger_passing` onto three. Roughly four to six sessions if each targets a thin cell, against an unbounded number if they do not. At 2–4 recordings a day this is weeks, not months — but only if the situation is chosen before the recorder starts.
- **It corrected a claim made an hour earlier**, that alarm call was ready to test. It has enough calls and not enough mornings, and only the pairwise count shows that.
- **The dashboard now shows it.** `SemanticsPanel` reads `calls/captures` per cell with a `!` under four captures, so a thin cell is visible during a session rather than after.
- **It did not change the backbone question.** This uses BirdNET's 3 s grid, the same as 0006, deliberately — so a change in the answer later is a change in the corpus and not in the method. Whether Perch 2.0 (which won experiment 0025 on call *type*) is also better for context cannot be asked until a pair clears the bar.

The script is designed to be re-run after each field session: when a pair clears the bar, it embeds the calls, runs leave-one-capture-out with a 200-permutation shuffled baseline, and reports whether the separation beats chance — `results.json` carries both the readiness table and any test that fired.
