# 0035 — WP2 arm B: can predicted fine stages stand in for true ones?

## Overview

After the tokenizer was settled (DAC 24 kHz at 24 codebooks, experiments 0033/0034) and the flat-model alternative killed (experiment 0030), exactly one architecture remained: generate 8 coarse codebooks of structure at about 1,800 tokens, then have a second model — an extender — fill in codebooks 8–23 before decoding. This experiment tested only the extender half, at its ceiling: it was handed the true coarse codes from real held-out recordings, so no generator error was involved. The result was the most complete failure in the series — the extender's output scored 0 out of 24 in blind listening — and the cause is structural rather than fixable: DAC's fine stages carry almost no redundancy for a model to predict, precisely because DAC uses its capacity so efficiently. The extender route is dead on DAC, and no amount of training will revive it.

## In depth

### Method

2026-08-02, 72 blinded trials, no generator anywhere. Every clip starts as a real held-out recording; the extender is handed the true coarse codes (stages 0–7) and predicts stages 8–23, which are then decoded at 24 codebooks. If predicted fine stages cannot match true fine stages on real coarse codes, no generator is worth attaching. Costs: tokenize 57 min, train 2.1 h, arm B 11 min. Session in `crowgpt/results/listening/extender-0035/`.

### Result

| arm | good | rate | 95% CI |
|---|---|---|---|
| raw | 21/24 | 0.88 | [0.75, 1.00] |
| DAC-24 round-trip | 18/24 | 0.75 | [0.58, 0.92] |
| extender | 0/24 | 0.00 | [0.00, 0.00] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − round-trip | +0.12 | [−0.08, +0.33] | not resolved |
| round-trip − extender | +0.75 | [+0.58, +0.92] | resolved |

Zero out of twenty-four. Ben: "arm extender is really bad, it makes it very garbled and robotic." No other arm in the series, including DAC-24 at 12 codebooks, scored below 0.33. The round-trip arm behaved exactly as experiment 0034 predicted (0.75 against raw's 0.88, unresolved), so the sitting itself is sound; the extender is what failed.

### Why: DAC's fine stages are nearly white, and that is not a bug

Per-stage marginal entropy over 150 held-out bouts, out of a possible 10 bits:

| | stages 0–7 | stages 8–23 | redundancy left in 8–23 |
|---|---|---|---|
| DAC-24 at 24 cb | 9.555 | 9.935 | 0.065 bits |
| EnCodec at 24 cb | 8.983 | 9.403 | 0.597 bits |

EnCodec leaves 9.2× more predictable structure in its fine stages than DAC does. The extender reached 9.901 bits against DAC's 9.935 marginal — it recovered 0.034 bits from the coarse context, where experiment 0030's flat model on EnCodec recovered 1.218 bits in the equivalent stages.

It is not undertrained: validation moved monotonically, 6.919 → 6.878 nats across 20,000 steps, still creeping down — but the whole descent is 0.059 bits. It learned what there was to learn, and there was almost nothing.

The cause is exactly the property that made DAC win by ear. DAC's factorised, L2-normalised codebooks run at 95–98% utilisation against EnCodec's 92% (experiment 0017), which is another way of saying DAC spreads information evenly and leaves little redundancy anywhere. Experiment 0034 showed the same thing from the other side: DAC at 12 codebooks collapses to 0.33 because there is no "coarse carries it all" regime to truncate into. WP2 assumed a split — coarse carries structure, fine carries predictable texture — that is true of EnCodec and false of DAC.

### A correction the README owes and records

After experiment 0030, the plan's WP2 gate — "stages ≥ 8 beat the codec marginal by > 0.3 bits" — was called "dead as a discriminator" because it passes codebooks experiment 0024 proved inaudible. That was half right and overstated. The gate has false positives, but here it would have returned 0.034 bits and correctly failed this run before the sitting. It is a valid necessary condition, not a sufficient one: clearing 0.3 bits does not mean audible, but failing it does mean nothing was learned. Had it been wired in as a pre-gate, it would have saved a sitting.

### Caveats

All material is corpus bouts through codecs and models — pipeline measurements, not findings about crows. The 0/24 is a ceiling test: real coarse codes, so the failure cannot be blamed on a generator upstream.

### What this changed

- WP2 is dead on DAC, for a reason that will not go away with more training: the redundancy the architecture needs is 0.065 bits per fine stage, and no amount of capacity extracts what is not there.
- The plan is out of routes as written: WP1 answered, WP3 a collected null, WP4 mostly evaporated, WP2 dead. What remains is not on the plan.
- A trade-off nobody had named: codec quality and codec modellability pull against each other. EnCodec is worse to listen to (0.67–0.80) and has 9.2× more exploitable structure; DAC is better (0.88–0.93) and has almost none. "Use the best codec" is no longer automatically right.
- The most promising unexplored point is DAC 44 kHz at 9 codebooks: experiment 0033 scored it 0.80 at 2,325 tokens per 3-second bout — only 28% more than the 1,811 the current generator handles, with a ceiling far above EnCodec-8's. Nothing had been trained on it.
- A flat DAC model is worth reconsidering despite experiment 0030: that null was measured where extra bandwidth bought no audible ceiling, and with DAC the ceiling moves enormously — the sequence cost is the same shape, the prize is not.

The DAC-44 idea became experiment 0037.
