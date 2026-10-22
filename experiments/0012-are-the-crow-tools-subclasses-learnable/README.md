# 0012 — Are the crow-tools subclasses learnable, or is the collapse right?

## The question

`FLAG_TO_CORE` in `pipelines/ingest/corpus.py` throws information away on
purpose. crow-tools labels seven call-type flags; CrowGPT trains four classes
from them:

```
mob + alert + scold -> alarm call     softSong -> song
rattle              -> call           begging  -> begging      grief -> dropped
```

Begging is the one flag that was promoted to a class of its own. Should the
others follow — should the head predict `mob` and `alert` and `scold` — or is
folding them into `alarm call` the right call?

Two ways to be wrong, and they cost different things. Collapsing a distinction
the audio supports means a head that can never say *mobbing* when mobbing is
the single most behaviourally interesting thing a crow does. Splitting one the
audio does not support means a head that says *mobbing* on a coin flip, which
is worse than silence, because a confident wrong answer gets believed.

## Method

No new embeddings. `pipelines/ingest/results/pooled_embeddings_crowtools_all-public.npz`
was built one row per labelled segment in corpus order, so every row can be
walked back to its segment and given its **raw flags** instead of the CORE class
it was folded into. `align()` proves the join instead of trusting it: each row's
cached CORE labels must equal the ones its segment maps to, and the run stops if
any file disagrees. All 2,494 rows joined, zero mismatches.

Everything below is recording-grouped 5-fold CV with the same logreg the shipped
head uses, so the numbers sit next to `pipelines/training/models/american-crow/metrics.json`
rather than beside it. 2,494 segments across 1,195 recordings.

## A. What the corpus actually contains

| flag | folds into | asked on | positives | recordings | biggest recording's share |
|---|---|---|---|---|---|
| mob | alarm call | 2,494 | 738 | 570 | 1% |
| alert | alarm call | 2,494 | 546 | 331 | 4% |
| **scold** | alarm call | **1,089** | 106 | 90 | 4% |
| softSong | song | 2,494 | 605 | 180 | 6% |
| rattle | call | 2,494 | 542 | 175 | 6% |
| begging | begging | 2,494 | 307 | 129 | 6% |
| **grief** | *(dropped)* | **1,375** | **3** | **1** | 100% |

Two columns decide most of this before any model runs.

**`asked` is not `positives + negatives`.** crow-tools grew `scold` and `grief`
after labelling had begun, so on 1,405 segments the scold question was never put
to a human — the key is absent, not `False`. Promoting `scold` to a class means
either training on 44% of the corpus or handing the head 1,405 unexamined
segments as confident negatives. Nothing in the current pipeline distinguishes
those two, because nothing currently reads the flag.

**No class is one recording in disguise.** mob's 738 positives come from 570
recordings and no single recording contributes more than 1% — so the grouped
AUCs below are not one loud crow measured 700 times. `grief` is the exception
and the reason it is dropped: 3 segments, all from one recording.

Where the labellers used two flags at once, as a share of the smaller class:

| pair | both | share of smaller |
|---|---|---|
| mob + scold | 80 | **76%** |
| softSong + rattle | 124 | 23% |
| alert + scold | 9 | 8% |
| mob + alert | 20 | **4%** |

`scold` is not a sibling of `mob`, it is a subset of it — three quarters of every
scold segment is also a mob segment. `mob` and `alert`, by contrast, are treated
as alternatives: they co-occur on 4% of the smaller class. The humans who made
this corpus considered mob-or-alert a real choice and scold-or-mob not much of
one.

## B. One-vs-rest AUC: every flag on its own

Restricted to the segments where the flag was actually asked, so the negatives
are real negatives.

| raw flag | AUC | | CORE class it folds into | AUC |
|---|---|---|---|---|
| mob | 0.838 | | alarm call | **0.942** |
| alert | 0.845 | | alarm call | ” |
| scold | 0.790 *(n=1,089)* | | alarm call | ” |
| softSong | 0.913 | | song | 0.913 |
| rattle | 0.961 | | call | 0.961 |
| begging | 0.916 | | begging | 0.916 |
| grief | — *(3 segments)* | | *dropped* | — |

The bottom three rows are identical on both sides, and that is worth saying out
loud: **`song` and `call` are not collapses at all.** Exactly one flag maps to
each, so the corpus's `song` class *is* soft song, and its `call` class *is*
rattle. The shipped head's "call" is a rattle detector wearing the name of the
vaguest class in the vocabulary, and it has never seen a contact call — which is
the most common thing a crow says and what `call` will mostly be asked about in
the field. That is a data gap, not a taxonomy question, and expanding the class
list does nothing about it.

Only `alarm call` is a genuine collapse, and it scores 0.942 against 0.838 and
0.845 for its parts. That gap is mostly arithmetic — a union of two classes has
more positives than either — so it does not settle anything on its own.

## C. The crux: mob against alert, with the recording held constant

| pair | AUC | n | recordings with both |
|---|---|---|---|
| mob vs alert | 0.813 | 1,244 | 41 / 860 |
| mob vs scold | **0.581** | 684 | 69 / 591 |
| rattle vs softSong *(control)* | 0.947 | 899 | 64 / 291 |

`mob vs scold` at 0.581 is near chance while the control pair reaches 0.947 on
the same features and the same folds, so 0.581 is the corpus talking, not the
pipeline failing. Combined with the 76% co-occurrence: **scold is not a
separable class here.**

`mob vs alert` at 0.813 looks learnable. But only 41 of 860 recordings contain
both, so the label is nearly a property of the recording — and recording-grouped
CV cannot catch that, because holding out a recording also holds out its label.
So run it again inside the 41 recordings that carry both, where the recording is
constant and cannot be the answer:

| pair, within recordings holding both | AUC | 5 fold seeds | n |
|---|---|---|---|
| mob vs alert | 0.726 | 0.667 – 0.726 | 138 (38 pos) |
| rattle vs softSong *(control)* | 0.848 | 0.848 – 0.879 | 352 (169 pos) |

Both pairs lose about a tenth of an AUC when the recording stops helping —
0.947→0.848 for the control, 0.813→0.726 for mob/alert. The distinction survives
in the same proportion a known-acoustic one does, so **mob vs alert is a real
acoustic difference, not recording identity.** It is also thin: 138 segments, and
the seed spread runs down to 0.667.

## D. At a threshold, which is what shipping means

AUC is a ranking score over the whole sweep. `SpeciesHead.predict` does not ship a
sweep — it takes one answer and shows it to a recordist. So: average precision,
and the precision actually available at three recall levels. Prevalence is beside
them because precision means nothing without it — 30% of this corpus is mob, so
0.30 is what guessing gets you.

| flag | prevalence | AP | best F1 | P@recall 0.5 | P@0.7 | P@0.9 |
|---|---|---|---|---|---|---|
| mob | 0.30 | 0.67 | 0.65 | 0.71 | **0.59** | 0.46 |
| alert | 0.22 | 0.60 | 0.62 | 0.66 | 0.54 | 0.35 |
| begging | 0.12 | 0.78 | 0.72 | **0.93** | 0.68 | 0.27 |
| rattle *(control)* | 0.22 | 0.87 | 0.84 | 0.92 | **0.91** | 0.78 |

**This is where mob stops looking shippable.** To catch 70% of mobbing you accept
41% false positives; at 90% recall more than half the calls labelled mob are not
mob, against a 30% base rate. Rattle on the same features, the same folds and the
same classifier gets 0.91 at that recall — so this is the class, not the pipeline.

And it exposes something about the product's own yardstick.
`analyzer.birdnet.reliability_tier` grades a class from its **AUC**: ≥0.80 reads
to the recordist as "reliable". mob's 0.838 earns that word while delivering 59%
precision at 70% recall. AUC is insensitive to prevalence and the tiers inherit
that, so they flatter exactly the imbalanced classes where a recordist most needs
the warning. Worth fixing separately from anything about taxonomy — the tier
should be computed from average precision, where mob's 0.67 and rattle's 0.87 sit
where a reader would expect them.

## E. What it costs the head that ships

AUC scores a class against the rest in isolation. What ships is one multiclass
head whose classes compete, and the price of splitting alarm is paid in confusion
between the halves. Same rows (2,149 with exactly one flag), same folds, two
label spaces — and the expanded head's predictions mapped back down to CORE:

| head | macro-F1 |
|---|---|
| trained on CORE | 0.842 |
| trained on 6 flags, predictions mapped down to CORE | **0.843** |
| trained on 6 flags, scored at its own 6 classes | 0.644 |

`mob` called `alert` 124/595 · `alert` called `mob` 126/475.

The first two lines are the finding. **Expanding costs nothing at the CORE level**
— train fine, collapse for display, and the app is exactly as accurate as it is
today. The finer answer is free in the sense that it does not damage the coarse
one.

It is just not very good. One in four alarm calls lands on the wrong side of the
mob/alert line, and 0.644 across six classes is dominated by that pair.

## F. A confound worth knowing about begging

| | n |
|---|---|
| begging | 307 |
| crowAge = juvenile | 313 |
| both | 279 |

91% of begging is juvenile-aged and 89% of juvenile is begging. `begging` at
0.916 AUC is the corpus's cleanest class, but it is nearly the same variable as
"a juvenile is present in this recording" — so some of that score is juvenile
recording character rather than the begging call. It does not change the
decision to keep begging as its own class (a juvenile that begs is what the
class means), and it is the reason not to read 0.916 as a ceiling for anything
else.

## The answer

**Keep the collapse. Expand nothing right now, and begging + the rest was the
right choice.** Three separate reasons, only one of which is about accuracy:

1. **`scold` cannot be expanded.** 0.581 against a 0.947 control, 76% of it is
   also `mob`, and it was only asked on 44% of the corpus. Three independent
   reasons and no counterweight.
2. **`grief` cannot be expanded.** 3 segments, one recording.
3. **`song` and `call` are already 1:1.** There is nothing to expand — only a
   contact-call gap to fill, which is a collection problem.

That leaves `mob` vs `alert`, the one split the corpus does support (0.726 with
the recording held constant, against a 0.848 control) and the one that costs
nothing at the CORE level (0.843 mapped down vs 0.842). Two reasons to still not
do it today, and section D added the first one.

**As a shipped answer, mob is not good enough yet.** 0.67 average precision, 59%
precision at 70% recall, against a 30% base rate — while rattle reaches 0.91 on
the same pipeline. The head can rank mobbing; it cannot assert it. Two in five
"mobbing" badges would be wrong at a useful recall, and a wrong badge on the one
behaviour the whole project is pointed at is worse than no badge.

**And there is no field data to evaluate it on.**
`label_defs` has offered `mobbing` and `scold` as field labels since the
contributor layer landed, and of 35 human labels on the field server, **zero use
either.** Shipping a head that distinguishes mobbing from alerting, with no
ground truth to check it against and a one-in-four error rate on that axis,
means the first evidence it is wrong arrives as a wrong answer on a real
recording.

The order is therefore: label `mobbing` in the field first, then split. Not the
reverse.

## What changed

`FLAG_TO_CORE` stays exactly as it is, and this is the measurement that says so
rather than the assumption that said so before. Four things came out of it.

**The end state is decided, and it is a replacement.** When mob and alert do
arrive, `alarm call` stops being a CORE class and they take its place. No
second-stage head over a coarse one, no phone showing the old word while a finer
answer waits in a side channel. Two vocabularies for the same distinction is what
rots — every count has to say which one it used, and eventually one is wrong.
Recorded in `FUTURE.txt` with what has to happen first.

**Three things went in ahead of it**, so that the relabelling it needs does not
destroy what it replaces:

- a re-answered label keeps its old answer in `label_revisions` rather than
  overwriting it, and its `config_version` moves with the new answer. The id does
  not move, so a label's witnessed context stays attached. This is what makes
  "did the finer list change anybody's mind" answerable at all.
- `export_manifest.py` carries the word the human chose next to the CORE class it
  folds into, so a finer head selects the rows that said the finer word instead of
  reading the coarse ones as negatives. That is section A's `asked` trap, in our
  own table this time.
- `label_defs.version_introduced` is recorded when a label reaches a running
  fleet instead of defaulting to 1 — the column that says whether a word was on
  the menu when somebody chose a different one.

**`reliability_tier` grades on the wrong number.** It reads AUC, so mob's 0.838
earns the word "reliable" in front of a recordist while delivering 59% precision
at 70% recall. AUC ignores prevalence and the tiers inherit that, flattering
exactly the imbalanced classes where the warning matters. It should be average
precision, where mob's 0.67 and rattle's 0.87 land where a reader expects. Not
fixed here — it is a change to what the app claims, not to what the corpus says.

**`scold` and `grief` are not expandable, and the partial-coverage trap makes it
worse.** Anyone reading `FLAG_TO_CORE` and thinking "why not add scold" would find
106 positives and reasonably try it. `corpus.py` now points here.

**The corpus's `call` class is a rattle detector.** Unrelated to the taxonomy
question and more consequential than it: the field will mostly hand it contact
calls, of which it has seen none.

## Re-running

```bash
../../pipelines/representation/.venv-birdnet/bin/python run.py
```

Needs the vendored labels (for the raw flags) and the built feature cache (for
the audio). It said "the fork" when this was written; the labels were vendored
into `pipelines/ingest/crowtools/labels.json` on 2026-07-30 and no fork is
involved. Sections D and E fit 3072-dimensional logregs over five folds and take
a few minutes between them — E's two multiclass passes are most of it; everything
else is seconds. Results land in `results.json`.
