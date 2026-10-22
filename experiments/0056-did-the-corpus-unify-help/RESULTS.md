# 0056 — did the corpus unification change anything a training run would notice?

## Overview

Ben rewrote the corpus database on 2026-08-06 to fix what he described as misorganized files and possibly wrong species folders, and the question was whether it is worth 35 minutes of re-extraction and two hours of re-tokenising to pick the change up. The answer is no for the American Crow generator — the species relabels touch 0.17% of bouts, no new audio arrived, and no duplicates existed — but yes, eventually, for anything multi-species, because the unify's stricter recordist-day grouping reveals that 17.7% of the multi-species held-out set shared a recordist-day with training. American Crow, the species every listening result is measured on, sits at only 2.4%, so nothing on record needs re-deriving.

## In depth

### What made the question answerable

The unify is real work — recordings went 11,689 → 25,000 and the table gained `slug`, `core_type`, `content_sha256`, `bytes`, `group_key` and `group_basis` — but `data/crowgpt/bouts` was written 5 Aug and the unify landed 6 Aug, so nothing any model reads has seen it. Both label sets are on disk to diff (Ben kept a `.pre-unify` backup).

### What actually changed in the extracted corpus

**Species: 214 bouts of 127,553 — 0.17%.**

| relabel | bouts |
|---|---|
| indian-jungle-crow → large-billed-crow | 212 |
| common-raven → american-crow | 2 |

The 212 are a taxonomic rename, not a misfiling — Indian Jungle Crow and Large-billed Crow are the same split. Genuinely misfiled audio comes to two bouts. Whatever was in the wrong folder, it was not in the bouts store.

**No duplicates.** `content_sha256`, now computed for every recording, finds zero collisions — a real negative finding that the two archives were not silently supplying the same audio twice.

**No new audio.** The big archive's 13,311 assets entering the database look like growth, but the bouts store already holds 56,164 of its bouts against 71,304 from the other archive. Metadata arriving is not audio arriving.

### The one thing that did change: grouping

`group_key` differs for 99.9% of bouts, but most of that is a format change (old: `species:Recordist Name|date|locality`; new: `species|rec-day|RECORDIST_ID|date`). What matters is whether groups collapse, since a coarser key means a stricter split:

| species | recordings | old groups | new groups | collapse |
|---|---|---|---|---|
| american-crow | 10,818 | 9,409 | 9,288 | 1.3% |
| hooded-crow | 3,243 | 1,549 | 983 | 36.5% |
| rook | 462 | 462 | 354 | 23.4% |
| eurasian-jackdaw | 891 | 834 | 710 | 14.9% |
| common-raven | 1,819 | 1,596 | 1,424 | 10.8% |
| carrion-crow | 865 | 777 | 703 | 9.5% |

This is exactly the asymmetry `crowgpt/README.md` predicted: the five species fetched earlier had manifests without recordist grouping and fell back to per-recording grouping, which is weaker. American Crow was always grouped properly and barely moves; the older fetches move a lot. Dropping locality from the key is what collapses groups — two recordings by one recordist on one day at two localities used to be two groups and are now one, which is more conservative and cannot leak more than the old key did.

### The number that decides it: leakage in the split actually used

A leak means two recordings the old key called separate groups, which the new key says are one recordist on one day, that the split put on opposite sides — one bird on one morning in both train and held-out.

| | |
|---|---|
| new groups spanning more than one split | 272 of 14,671 |
| held-out bouts inside a leaking group | 3,632 of 20,508 — **17.7%** |
| American Crow held-out inside a leaking group | 227 of 9,546 — **2.4%** |

By species, the leaking groups are hooded-crow 109, common-raven 46, american-crow 35, eurasian-jackdaw 28, rook 28, carrion-crow 20. So the multi-species validation numbers were mildly optimistic, and the American Crow ones essentially were not.

### What this changed

- **Do not re-extract for the generator.** 0.17% relabels, 1.3% group collapse on American Crow, 2.4% val cleanup, no new audio, no duplicates. Against experiment 0048's scaling curve — a doubling of data buys about 0.017 nats, and experiment 0023 moved val by 0.164 nats for a listening difference of exactly zero — this is not a measurable change to anything.
- **Do re-extract before the next multi-species or classifier run.** 17.7% of the held-out set sharing a recordist-day with training is worth fixing, and experiment 0048 explicitly exempted the classifier and context work from "more data will not help".
- **Read the multi-species val losses on record as slightly optimistic** rather than re-deriving them. Nothing in the project turns on them: experiment 0049's conclusion was a listening null, and experiment 0048's scaling curve was measured on the American Crow val split, which is the clean one.
- **Re-extraction has an unpriced cost that is not GPU time.** The spent-bout ledger is keyed on bout index, and experiment 0050 recorded what a rebuild does to those. Re-extracting now would invalidate 822 heard-bout records across `results/listening/` and experiment 0053's claim of 132 in `bouts.json` — the mechanism that stops a sitting replaying audio Ben has already heard. Key the ledger on `recording_id` before re-extracting anything; that survives a rebuild and a bout index does not.
