# 0012 — Are the crow-tools subclasses learnable, or is the collapse right?

## Overview

The training pipeline deliberately folds seven human-labelled call-type flags down to four classes — for example, `mob`, `alert` and `scold` all become one class, `alarm call`. This experiment asked whether that collapse throws away distinctions the audio actually supports, and whether the model's output classes should be made finer. The answer was to keep the collapse: `scold` turned out to be inseparable from `mob` (near-chance discrimination, and mostly the same segments anyway), `grief` has only 3 examples, and `song` and `call` were never collapses in the first place. The one split the data does support, `mob` versus `alert`, is a real acoustic difference — but a classifier shipping it today would be wrong on roughly two of every five "mobbing" badges at useful recall, and there is zero field ground truth to check it against, so the order of work is: label mobbing in the field first, then split.

## In depth

### The question

`FLAG_TO_CORE` in `pipelines/ingest/corpus.py` maps seven crow-tools call-type flags to four trained classes: `mob`, `alert` and `scold` fold into `alarm call`; `softSong` becomes `song`; `rattle` becomes `call`; `begging` stays `begging`; `grief` is dropped. Two ways to be wrong, with different costs: collapsing a distinction the audio supports means a head that can never say *mobbing* — the single most behaviourally interesting thing a crow does — while splitting one the audio does not support means a head that says *mobbing* on a coin flip, which is worse than silence because a confident wrong answer gets believed.

### Method

No new embeddings. The cached pooled embeddings (`pipelines/ingest/results/pooled_embeddings_crowtools_all-public.npz`) were built one row per labelled segment in corpus order, so every row was walked back to its segment and given its raw flags. `align()` proves the join instead of trusting it — each row's cached CORE labels must equal the ones its segment maps to. All 2,494 rows joined, zero mismatches. Everything is recording-grouped 5-fold CV with the same logistic regression the shipped head uses: 2,494 segments across 1,195 recordings.

### What the corpus contains

| flag | folds into | asked on | positives | recordings | biggest recording's share |
|---|---|---|---|---|---|
| mob | alarm call | 2,494 | 738 | 570 | 1% |
| alert | alarm call | 2,494 | 546 | 331 | 4% |
| **scold** | alarm call | **1,089** | 106 | 90 | 4% |
| softSong | song | 2,494 | 605 | 180 | 6% |
| rattle | call | 2,494 | 542 | 175 | 6% |
| begging | begging | 2,494 | 307 | 129 | 6% |
| **grief** | *(dropped)* | **1,375** | **3** | **1** | 100% |

Two structural facts decide most of this before any model runs. First, **`asked` is not `positives + negatives`**: `scold` and `grief` were added after labelling had begun, so on 1,405 segments the scold question was never put to a human — the key is absent, not `False`. Promoting `scold` means either training on 44% of the corpus or treating 1,405 unexamined segments as confident negatives. Second, **no class is one recording in disguise** — mob's 738 positives come from 570 recordings with no recording contributing more than 1% — except `grief`, whose 3 segments all come from one recording, which is why it is dropped.

Co-occurrence shows `scold` is not a sibling of `mob` but a subset of it: 76% of scold segments are also mob segments. `mob` and `alert`, by contrast, co-occur on only 4% of the smaller class — the labellers treated mob-or-alert as a real choice and scold-or-mob not much of one.

### One-vs-rest AUC

Restricted to segments where the flag was actually asked, so negatives are real negatives:

| raw flag | AUC | CORE class it folds into | AUC |
|---|---|---|---|
| mob | 0.838 | alarm call | **0.942** |
| alert | 0.845 | alarm call | ” |
| scold | 0.790 *(n=1,089)* | alarm call | ” |
| softSong | 0.913 | song | 0.913 |
| rattle | 0.961 | call | 0.961 |
| begging | 0.916 | begging | 0.916 |
| grief | — *(3 segments)* | *dropped* | — |

The bottom three rows are identical on both sides: **`song` and `call` are not collapses at all.** Exactly one flag maps to each, so the corpus's `song` class *is* soft song and its `call` class *is* rattle. The shipped head's "call" is a rattle detector wearing the name of the vaguest class in the vocabulary, and it has never seen a contact call — the most common thing a crow says and what `call` will mostly be asked about in the field. That is a data gap, not a taxonomy question.

### The crux: mob against alert, with the recording held constant

| pair | AUC | n | recordings with both |
|---|---|---|---|
| mob vs alert | 0.813 | 1,244 | 41 / 860 |
| mob vs scold | **0.581** | 684 | 69 / 591 |
| rattle vs softSong *(control)* | 0.947 | 899 | 64 / 291 |

`mob vs scold` at 0.581 is near chance while the control pair reaches 0.947 on the same features and folds — the corpus talking, not the pipeline failing. Combined with the 76% co-occurrence: scold is not a separable class here.

`mob vs alert` at 0.813 looks learnable, but only 41 of 860 recordings contain both, so the label is nearly a property of the recording — and recording-grouped CV cannot catch that. Re-run inside only the 41 recordings that carry both labels, where the recording cannot be the answer:

| pair, within recordings holding both | AUC | 5 fold seeds | n |
|---|---|---|---|
| mob vs alert | 0.726 | 0.667 – 0.726 | 138 (38 pos) |
| rattle vs softSong *(control)* | 0.848 | 0.848 – 0.879 | 352 (169 pos) |

Both pairs lose about a tenth of an AUC when the recording stops helping (0.947→0.848 for the control, 0.813→0.726 for mob/alert). The distinction survives in the same proportion a known-acoustic one does, so **mob vs alert is a real acoustic difference, not recording identity** — but thin: 138 segments, seed spread down to 0.667.

### At a threshold, which is what shipping means

AUC is a ranking score; `SpeciesHead.predict` ships one answer. So: average precision and precision at fixed recall, with prevalence beside them (30% of this corpus is mob, so 0.30 is what guessing gets you):

| flag | prevalence | AP | best F1 | P@recall 0.5 | P@0.7 | P@0.9 |
|---|---|---|---|---|---|---|
| mob | 0.30 | 0.67 | 0.65 | 0.71 | **0.59** | 0.46 |
| alert | 0.22 | 0.60 | 0.62 | 0.66 | 0.54 | 0.35 |
| begging | 0.12 | 0.78 | 0.72 | **0.93** | 0.68 | 0.27 |
| rattle *(control)* | 0.22 | 0.87 | 0.84 | 0.92 | **0.91** | 0.78 |

This is where mob stops looking shippable. To catch 70% of mobbing you accept 41% false positives; at 90% recall more than half the calls labelled mob are not mob, against a 30% base rate. Rattle on the same pipeline gets 0.91 precision at that recall — so this is the class, not the pipeline.

It also exposes a product flaw: `analyzer.birdnet.reliability_tier` grades a class from AUC, where ≥0.80 reads as "reliable". mob's 0.838 earns that word while delivering 59% precision at 70% recall. AUC is insensitive to prevalence, so the tiers flatter exactly the imbalanced classes where a recordist most needs the warning. The tier should be computed from average precision, where mob's 0.67 and rattle's 0.87 sit where a reader would expect.

### What splitting costs the head that ships

Same rows (2,149 with exactly one flag), same folds, two label spaces, with the expanded head's predictions mapped back down to CORE:

| head | macro-F1 |
|---|---|
| trained on CORE | 0.842 |
| trained on 6 flags, predictions mapped down to CORE | **0.843** |
| trained on 6 flags, scored at its own 6 classes | 0.644 |

`mob` was called `alert` on 124/595 segments and `alert` called `mob` on 126/475. Expanding costs nothing at the CORE level — train fine, collapse for display, and the app is exactly as accurate as today. The finer answer is just not very good: one in four alarm calls lands on the wrong side of the mob/alert line.

### A confound worth knowing about begging

307 begging segments, 313 juvenile-aged segments, 279 both: 91% of begging is juvenile-aged and 89% of juvenile is begging. `begging` at 0.916 AUC is the corpus's cleanest class, but it is nearly the same variable as "a juvenile is present in this recording" — some of that score is juvenile recording character rather than the begging call. It does not change the decision to keep begging as its own class, and it is the reason not to read 0.916 as a ceiling for anything else.

### The answer

**Keep the collapse. Expand nothing right now.** Three reasons, only one about accuracy:

1. `scold` cannot be expanded: 0.581 against a 0.947 control, 76% of it is also `mob`, and it was only asked on 44% of the corpus.
2. `grief` cannot be expanded: 3 segments, one recording.
3. `song` and `call` are already 1:1 — nothing to expand, only a contact-call collection gap to fill.

That leaves mob vs alert, which the corpus does support and which costs nothing at the CORE level — but as a shipped answer mob is not good enough yet (0.67 average precision, 59% precision at 70% recall against a 30% base rate), and of the 35 human labels on the field server, **zero** use the `mobbing` or `scold` field labels that have been offered since the contributor layer landed. Shipping the split with no ground truth means the first evidence it is wrong arrives as a wrong answer on a real recording. Label mobbing in the field first, then split — not the reverse.

### What changed

- `FLAG_TO_CORE` stays exactly as it is — now by measurement rather than assumption.
- **The end state is decided, and it is a replacement**: when mob and alert do arrive, `alarm call` stops being a CORE class and they take its place. No second-stage head over a coarse one, no two vocabularies for the same distinction. Recorded in `FUTURE.txt` with prerequisites.
- **Three things went in ahead of it** so the future relabelling does not destroy what it replaces: re-answered labels keep their old answer in `label_revisions` (the id does not move, so witnessed context stays attached); `export_manifest.py` carries the word the human chose next to the CORE class it folds into, so a finer head can select rows that said the finer word instead of reading coarse ones as negatives; and `label_defs.version_introduced` is recorded when a label reaches a running fleet, saying whether a word was on the menu when somebody chose a different one.
- **`reliability_tier` grades on the wrong number** (AUC rather than average precision). Noted, not fixed here — it is a change to what the app claims, not what the corpus says.
- `corpus.py` now points at this experiment so nobody reads `FLAG_TO_CORE`, finds scold's 106 positives, and reasonably tries adding it.
- **The corpus's `call` class is a rattle detector** — unrelated to the taxonomy question and more consequential than it: the field will mostly hand it contact calls, of which it has seen none.

### Re-running

`../../pipelines/representation/.venv-birdnet/bin/python run.py` — needs the vendored labels (`pipelines/ingest/crowtools/labels.json`, vendored 2026-07-30) and the built feature cache. Takes a few minutes; results land in `results.json`.
