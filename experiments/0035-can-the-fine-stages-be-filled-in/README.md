# 0035 — WP2 arm B: can predicted fine stages stand in for true ones?

**2026-08-02** · 72 blinded trials · no generator anywhere · **answer: no, and the
reason is structural**

## The question

Five sittings settled the tokenizer (DAC 24 kHz at 24 codebooks, 0033/0034) and
killed the alternative (a flat model at the transparent bitrate, 0030). That left
exactly one route: generate 8 codebooks of structure at ~1,800 tokens, then have
a second model fill stages 8–23 before decoding at 24.

This tests only the second half, and it tests its **ceiling**. Every clip starts
as a real held-out recording; the extender is handed the *true* coarse codes.
If predicted fine stages cannot match true fine stages on real coarse codes, no
generator is worth attaching.

## Result

| arm | good | rate | 95% CI |
|---|---|---|---|
| raw | 21/24 | 0.88 | [0.75, 1.00] |
| DAC-24 round-trip | 18/24 | 0.75 | [0.58, 0.92] |
| **extender** | **0/24** | **0.00** | [0.00, 0.00] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − round-trip | +0.12 | [−0.08, +0.33] | not resolved |
| round-trip − extender | **+0.75** | [+0.58, +0.92] | **resolved** |

**Zero out of twenty-four.** Ben: *"arm extender is really bad, it makes it very
garbled and robotic."* This is the most complete failure of any arm in the
series — no other arm, including DAC-24 at 12 codebooks, scored below 0.33.

The round-trip arm behaved exactly as 0034 predicted (0.75 against raw's 0.88,
unresolved), so the sitting itself is sound. The extender is what failed.

## Why: DAC's fine stages are nearly white, and that is not a bug

Per-stage marginal entropy, 150 held-out bouts, out of a possible 10 bits:

| | stages 0–7 | stages 8–23 | redundancy left in 8–23 |
|---|---|---|---|
| DAC-24 at 24 cb | 9.555 | **9.935** | 0.065 bits |
| EnCodec at 24 cb | 8.983 | 9.403 | 0.597 bits |

**EnCodec leaves 9.2× more predictable structure in its fine stages than DAC
does.** The extender reached 9.901 bits against DAC's 9.935 marginal — it
recovered **0.034 bits** by using the coarse context. For comparison, 0030's flat
model on EnCodec recovered **1.218 bits** in the equivalent stages.

**It is not undertrained.** Validation moved monotonically, 6.919 → 6.878 nats
across 20,000 steps, and was still creeping down — but the whole descent is 0.059
bits. It learned what there was to learn. There was almost nothing.

**And the cause is exactly the property that made DAC win.** DAC's factorised,
L2-normalised codebooks run at 95–98% utilisation against EnCodec's 92% (0017),
which is another way of saying DAC spreads information evenly across its stages
and leaves little redundancy anywhere. 0034 already showed the same thing from
the other side: DAC at 12 codebooks collapses to 0.33, because there is no
"coarse carries it all" regime to truncate into.

**WP2 assumed a split that DAC does not have.** The extender architecture rests
on "coarse carries structure, fine carries texture, and texture is predictable
from structure." That is true of EnCodec and false of DAC. A codec that uses its
capacity efficiently is, by construction, a codec whose residuals a second model
cannot guess.

## A correction I owe

After 0030 I called PLAN-TIMBRE's WP2 gate — *"stages ≥ 8 beat the codec marginal
by > 0.3 bits"* — **"dead as a discriminator"**, on the grounds that it passes
codebooks 0024 proved inaudible. That was half right and I overstated it.

It has false positives, which is what 0030 showed. But here it would have
returned 0.034 bits and **failed this run correctly, before the sitting**. So it
is a valid *necessary* condition and not a sufficient one: clearing 0.3 bits does
not mean audible, but failing it does mean nothing was learned. I disabled it in
this run's design on the strength of the overstatement; had it been wired in as a
pre-gate, it would have saved a sitting.

## What this changed

- **WP2 is dead on DAC, and for a reason that will not go away with more
  training.** The redundancy the architecture needs is 0.065 bits per fine stage.
  No amount of capacity extracts what is not there.
- **The plan is now out of routes as written.** WP1 answered, WP3 a collected
  null, WP4 mostly evaporated, WP2 dead. What remains is not on the plan.
- **A trade-off nobody had named:** codec quality and codec modellability pull
  against each other here. EnCodec is worse to listen to (0.67–0.80) and has
  9.2× more exploitable structure; DAC is better (0.88–0.93) and has almost none.
  Any future architecture has to pick a side, and "use the best codec" is no
  longer automatically right.
- **The most promising unexplored point is DAC 44 kHz at 9 codebooks.** 0033
  scored it 0.80 — below raw, but above EnCodec-32's 0.67 — at **2,325 tokens**
  for a 3-second bout. That is only 28% more than the 1,811 the current generator
  already handles, against a ceiling far above EnCodec-8's. It is the best
  quality-per-token point measured, and nothing has been trained on it.
- **A flat DAC model is worth reconsidering despite 0030.** That null was
  measured where the extra bandwidth bought no audible ceiling (EnCodec K=8 and
  K=16 are indistinguishable). With DAC the ceiling moves enormously, so the
  trade 0018 and 0030 both lost may come out differently — the sequence cost is
  the same shape, the prize is not.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0035-can-the-fine-stages-be-filled-in/run.py
```

Tokenize 57 min, train 2.1 h, arm B 11 min. Resumable per stage. Session in
`crowgpt/results/listening/extender-0035/`.
