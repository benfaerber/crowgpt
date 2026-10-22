# What would it take to read a context off a call?

**Answer: four more mornings, on the right two situations. Not more calls.**

Nothing is answerable yet, and this says exactly what is missing — which is the
half experiment 0006 left out. It re-runs itself as the corpus grows and turns
into a real result the moment a pair clears the bar, with no new code.

## Why re-ask

0006 asked whether context is in the signal at all and refused: the corpus held
3 labelled calls with context. That refusal was correct and its instruction was
"collect more", which is not enough to plan a field session around. Two months
of collection is about to happen, and the difference between sessions that make
this answerable and sessions that do not is *which* situation gets recorded and
on *how many separate days*.

## Where the corpus actually is

Kept captures only — the ★ Keep flag is the only thing separating a real field
observation from the seeded archive clips and test uploads that dominate the corpus.

| | |
|---|---|
| labels on kept audio | 42 over 10 captures, 6 days |
| `alarm call` | 23 calls / 6 captures |
| `begging` | 11 calls / **2** captures |
| `call` | 5 calls / 5 captures |
| `alarm call` **with a context chip** | 22 calls / **5** captures |

`alarm call` is the only type with enough context to be worth testing, and that
is where the correction is: it clears the bar for *carrying* context, but **no
pair of contexts within it clears the bar for a contrast**. The best pairs sit
at 2 captures a side against a bar of 4. This was worth measuring precisely
rather than reasoning about, because "alarm call has 23 labelled calls" reads
like enough and is not.

## The bar, and why it is about captures

10+ calls across 4+ *separate captures*, per side — 0006's, unchanged so the two
are comparable. Two caws from one bout are nearly the same data point, so a fold
that splits them reports an accuracy about the recording rather than the
situation. Every fold holds out a whole capture, which means a cell drawn from
two captures has two independent observations however many calls sit in it.

A call can carry several chips at once (`human_known` and `caller_stays` and
`crows_still` all describe one moment), so a pairwise test uses only the calls
carrying exactly one of the two — otherwise it scores a label against itself.

## Result: no pair is answerable

The closest, and what each still needs:

| context A | context B | A | B | needs |
|---|---|---|---|---|
| human_approaching | known_passing | 9/2 | 8/2 | 2 more captures each |
| human_known | known_passing | 9/2 | 8/2 | 2 more captures each |
| human_known | stranger_passing | 9/2 | 5/1 | 2 and 3 more captures |
| known_passing | loud_worker | 8/2 | 8/1 | 2 and 3 more captures |
| caller_stays | human_passing | 17/4 | 3/1 | 3 more captures on B |

No accuracy is reported, on purpose. A number from this much data would be noise
wearing a result's clothes.

Per context, calls are mostly fine and captures are not:

| context | calls | captures | needs |
|---|---|---|---|
| crows_still | 19 | 4 | ready |
| caller_stays | 18 | 4 | ready |
| human_approaching | 9 | 2 | 2 more captures |
| human_known | 9 | 2 | 2 more captures |
| known_passing | 8 | 2 | 2 more captures |
| loud_worker | 8 | **1** | 3 more captures |
| stranger_passing | 5 | **1** | 3 more captures |
| human_gives_food | 2 | 2 | 2 more captures, 8 more calls |

The two "ready" rows are descriptors of the caller's own behaviour rather than
situations — `crows_still` and `caller_stays` say what the birds did, not what
happened to them. They cannot be contrasted with each other to mean anything, so
they do not rescue the table.

## What the answer changed

- **The collection plan for the next two months.** Not "record more", but: get
  `human_known`, `known_passing` and `human_approaching` onto two more mornings
  each, and `loud_worker` and `stranger_passing` onto three. That is roughly
  four to six sessions if each targets a thin cell, against an unbounded number
  if they do not. At 2–4 recordings a day this is weeks, not months — but only
  if the situation is chosen before the recorder starts.
- **It corrected a claim made an hour earlier**, that alarm call was ready to
  test. It has enough calls and not enough mornings, and only the pairwise count
  shows that.
- **The dashboard now shows it.** `SemanticsPanel` reads `calls/captures` per
  cell with a `!` under four captures, so a thin cell is visible during a
  session rather than after.
- **It did not change the backbone question.** This uses BirdNET's 3 s grid, the
  same as 0006, deliberately — so a change in the answer later is a change in
  the corpus and not in the method. Whether Perch 2.0 (which won 0025 on call
  *type*) is also better for context cannot be asked until a pair clears the bar.

## Running it

```bash
../../pipelines/representation/.venv-birdnet/bin/python run.py
../../pipelines/representation/.venv-birdnet/bin/python run.py --call-type begging
```

Re-run after each field session. When a pair clears, it embeds the calls, runs
leave-one-capture-out with a 200-permutation shuffled baseline, and reports
whether the separation beats chance — `results.json` carries both the readiness
table and any test that fired.
