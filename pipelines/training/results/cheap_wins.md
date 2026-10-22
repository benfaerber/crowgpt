# Cheap-wins experiment — improving call-type AUC with only existing data

**Question:** with no new downloads, can we lift the weak classes (alarm 0.68,
song 0.59)? Three levers: (1) recover multi-label data the old pipeline threw
away, (2) mean+std+max pooling instead of mean-only, (3) a binary alarm sanity
check. `recover_and_pool.py` builds the pooled cache and runs all three.

## What we recovered

The old pipeline did `if "," in call_type: continue` — dropping every
compound-tagged clip. Parsing the tags into label *sets* instead recovers:

| class | old (single-label) | recovered |
|---|---|---|
| alarm call | 10 | **28** |
| song | 11 | **18** |
| flight call | 25 | 40 |
| call | 71 | 112 |

## Result 1 — recovering compound labels does NOT rescue alarm (negative)

Per-class one-vs-rest AUC, multi-label target:

| config | alarm | call | flight | song |
|---|---|---|---|---|
| baseline (mean, single-label) | 0.68 | 0.72 | 0.87 | 0.59 |
| multi-label (mean) | 0.64 | 0.67 | 0.76 | 0.62 |
| multi-label (mean+std+max) | 0.65 | 0.62 | 0.78 | 0.67 |

Binary alarm-vs-rest: **AUC 0.65, F1 0.45** — barely above chance even at n=28.

The recovered alarm examples are compound clips (`alarm call, call, flight
call`) — messy recordings where alarm is one of several overlapping things. They
don't add a clean alarm signal, and they *dilute* the clean classes (flight
0.87→0.78). **Direct evidence for the Phase 3 thesis: alarm is label-limited;
the fix is clean witnessed labels (gold set / mobbing video), not more scraped
tags.** Do not spend a corpus run on more archive alarm data.

## Result 2 — mean+std+max pooling is a clean win (shipped)

The multi-label drops above are a task artifact (harder eval + compound
dilution). Isolating *just* pooling in the clean single-label regime the
production model ships on (n=129):

| features | alarm | call | flight | song | macro-F1 |
|---|---|---|---|---|---|
| mean (1024) | 0.708 | 0.707 | 0.897 | 0.624 | 0.441 |
| **mean+std+max (3072)** | **0.724** | 0.699 | **0.913** | **0.649** | **0.481** |
| delta | +.016 | −.008 | +.016 | +.025 | **+.040** |

Pooling helps song (+.025, the target), helps flight and alarm, leaves call
flat, and lifts macro-F1 by 4 points. std/max encode the temporal spread mean
throws away — the signature of sustained/structured calls. **This is what we
shipped:** `pooling.py` is the shared feature def; `train.py` trains on clean
single-label pooled features; `predict.py` and the demo pool over the clip /
call region before classifying.

## Takeaways

- Alarm and song are **label-limited from web data** — confirmed again. Next
  alarm gains come from clean witnessed labels, not scraping.
- Temporal pooling is a free, honest lift (macro-F1 0.44→0.48); folded into
  production.
- Region-level pooling also made the demo more honest: on `rcrows_sample.mp3`
  it now reads the excited peanut-calling as `call` instead of hallucinating
  `song 82%` / `alarm call 97%` from noisy single-window guesses.
