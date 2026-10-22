# 0056 — did the corpus unification change anything a training run would notice?

**Question.** Ben rewrote `data/corvid.db` on 2026-08-06, keeping a `.pre-unify`
backup: *"there were some misorganized files… I think it may have had species in
wrong folders and stuff."* Is it worth 35 minutes re-extracting and two hours
re-tokenising to pick it up?

**Answer: not for the generator. Yes, eventually, for anything multi-species.**

The unify is real work — recordings went **11,689 → 25,000** and the table gained
`slug`, `core_type`, `content_sha256`, `bytes`, `group_key` and `group_basis`. But
almost none of it lands where American Crow generation would feel it.

`data/crowgpt/bouts` was written 5 Aug and the unify landed 6 Aug, so nothing any
model reads has seen it. That is what makes the question answerable: both label
sets are on disk to diff.

## What actually changed, in the extracted corpus

**Species: 214 bouts of 127,553 — 0.17%.**

| relabel | bouts |
|---|---|
| indian-jungle-crow → large-billed-crow | 212 |
| common-raven → american-crow | 2 |

The 212 are a **taxonomic rename**, not a misfiling — Indian Jungle Crow and
Large-billed Crow are the same split. Genuinely misfiled audio comes to **two
bouts**. Whatever was in the wrong folder, it was not in the bouts store.

**No duplicates.** `content_sha256` is now computed for every recording and finds
**zero** collisions, which is a real (negative) finding: the two archives
were not silently supplying the same audio twice.

**No new audio.** The big archive's 13,311 assets entering the database looks like
growth, but the bouts store already holds **56,164 of its bouts** against 71,304
from the other archive. Metadata arriving is not audio arriving.

## The one thing that did change: grouping

`group_key` differs for 99.9% of bouts, but most of that is a format change — the
old key was `species:Recordist Name|date|locality`, the new one is
`species|rec-day|RECORDIST_ID|date`. What matters is whether groups **collapse**,
because a coarser key means a stricter split.

| species | recordings | old groups | new groups | collapse |
|---|---|---|---|---|
| american-crow | 10,818 | 9,409 | 9,288 | **1.3%** |
| hooded-crow | 3,243 | 1,549 | 983 | **36.5%** |
| rook | 462 | 462 | 354 | 23.4% |
| eurasian-jackdaw | 891 | 834 | 710 | 14.9% |
| common-raven | 1,819 | 1,596 | 1,424 | 10.8% |
| carrion-crow | 865 | 777 | 703 | 9.5% |

That is exactly the asymmetry `crowgpt/README.md` predicted: *"The five species
fetched earlier have manifests carrying only `{id, type, path, quality}` and still
fall back to per-recording grouping, which is weaker."* American Crow was always
grouped properly and barely moves; the older fetches move a lot.

Dropping locality from the key is what collapses them. Two recordings by one
recordist on one day at two localities used to be two groups and are now one —
more conservative, and it cannot leak *more* than the old key did.

## The number that decides it: leakage in the split actually used

A leak here means two recordings the **old** key called separate groups, which the
**new** key says are one recordist on one day, that the split then put on opposite
sides. Under the new key that is one bird on one morning appearing in both train
and held-out.

| | |
|---|---|
| new groups spanning more than one split | **272** of 14,671 |
| held-out bouts inside a leaking group | **3,632 of 20,508 — 17.7%** |
| **American Crow held-out inside a leaking group** | **227 of 9,546 — 2.4%** |

By species, the leaking groups are hooded-crow 109, common-raven 46,
american-crow 35, eurasian-jackdaw 28, rook 28, carrion-crow 20.

**So the multi-species validation numbers were mildly optimistic and the American
Crow ones essentially were not.** 0049's `multi` arm, `tokens-v2` and anything
else scored across 46 species had roughly a sixth of its held-out set sharing a
recordist-day with training. American Crow, which every listening result in this
project is measured on, sits at 2.4%.

## What this changed

- **Do not re-extract for the generator.** 0.17% relabels, 1.3% group collapse on
  American Crow, 2.4% val cleanup, no new audio, no duplicates. Against 0048's
  scaling curve — a *doubling* of data buys ~0.017 nats, and 0023 moved val by
  0.164 nats for a listening difference of exactly zero — this is not a
  measurable change to anything.
- **Do re-extract before the next multi-species or classifier run.** 17.7% of the
  held-out set sharing a recordist-day with training is worth fixing, and 0048
  explicitly exempted the classifier and context work from "more data will not
  help".
- **The multi-species val losses on record should be read as slightly optimistic**
  rather than re-derived. Nothing in the project turns on them: 0049's conclusion
  was a listening null, and 0048's scaling curve was measured on the American Crow
  val split, which is the clean one.
- **Re-extraction has a cost nobody has priced, and it is not GPU time.** The
  spent-bout ledger is keyed on **bout index**, and 0050 already recorded what a
  rebuild does to those: *"every earlier sitting drew from v1 and those indices
  stopped meaning the same thing after the rebuild."* Re-extracting now would
  invalidate 822 heard-bout records across `results/listening/` and 0053's claim
  of 132 in `bouts.json` — the mechanism that stops a sitting replaying audio Ben
  has already heard. **Key the ledger on `recording_id` before re-extracting
  anything**, since that survives a rebuild and a bout index does not.
