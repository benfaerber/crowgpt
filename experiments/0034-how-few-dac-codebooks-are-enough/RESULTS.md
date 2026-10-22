# 0034 — How few DAC-24 codebooks are enough?

## Overview

Experiment 0033 settled on DAC 24 kHz at 32 codebooks as the project's tokenizer, but 32 codebooks means 7,200 tokens for a 3-second bout — and every codebook that can be dropped without a listener noticing is sequence length a generator does not have to learn. This blind listening sitting walked down the ladder (32, 24, 16, 12 codebooks) against raw audio, most of which had never been played to anyone. The answer: 24 codebooks is enough — it scored identically to 32 and neither is separable from raw — while 16 is audibly worse and 12 collapses badly. That fixed the tokenizer at DAC-24 with 24 codebooks (5,400 tokens per 3-second bout, a 25% cut for no audible cost) and located a sharp perceptual floor between 16 and 24 codebooks.

## In depth

### Method

2026-08-02, 120 blinded trials: raw plus DAC-24 at 12, 16, 24 and 32 codebooks, 24 clips per arm. Only the 32 rung had ever been heard by ear; experiment 0017 had tested DAC-24 at 8 and 12 codebooks and found both poor, but on BirdNET retention — the instrument that ranked DAC last overall where the ear ranks it first.

### Results

| arm | tokens / 3 s | good | rate | 95% CI |
|---|---|---|---|---|
| raw | — | 22/24 | 0.92 | [0.79, 1.00] |
| DAC-24, 32 cb | 7,200 | 21/24 | 0.88 | [0.75, 1.00] |
| DAC-24, 24 cb | 5,400 | 21/24 | 0.88 | [0.75, 1.00] |
| DAC-24, 16 cb | 3,600 | 16/24 | 0.67 | [0.46, 0.83] |
| DAC-24, 12 cb | 2,700 | 8/24 | 0.33 | [0.17, 0.54] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − 32 cb | +0.04 | [−0.12, +0.21] | not resolved |
| raw − 24 cb | +0.04 | [−0.12, +0.21] | not resolved |
| raw − 16 cb | +0.25 | [+0.04, +0.46] | resolved |
| raw − 12 cb | +0.58 | [+0.38, +0.79] | resolved |
| 32 cb − 24 cb | +0.00 | [−0.17, +0.21] | not resolved |
| 24 cb − 16 cb | +0.21 | [−0.04, +0.42] | not resolved |
| 16 cb − 12 cb | +0.33 | [+0.04, +0.58] | resolved |

Twenty-four codebooks is enough; the last eight buy nothing — the 32 and 24 arms scored identically, a difference of exactly zero, and neither is separable from raw. The floor is sharp and close: 16 cb is resolved below raw, and 12 cb collapses to 0.33, worse than any codec arm in any sitting in this series, including EnCodec at 6 kbps. The knee sits between 16 and 24 codebooks — between 3,600 and 5,400 tokens. Ben's note agrees from the inside: "dac24_24-dac24_32 are both pretty good most of the time."

### This sitting replicates, which the last one could not

Experiment 0033's cross-sitting comparisons had to be thrown out because its raw anchor moved. This sitting carried the 32 cb arm forward on purpose:

| | 0033 | 0034 |
|---|---|---|
| raw | 0.97 | 0.92 |
| DAC-24, 32 cb | 0.93 | 0.88 |
| raw − 32 cb | +0.03 | +0.04 |

Both arms sit about five points lower — a whole-sitting shift well inside noise — and the difference between them is identical to within a point. That is what a stable instrument looks like, and it is the first time in this series two sittings agreed on a repeated arm. Pace was 1,416 ms per clip against 1,374 / 1,308 / 1,403 / 1,438 in the four earlier sittings, so the fatigue that had been warned about does not show up in the timing either.

### Caveats

These are blind ratings of codec round-trips over corpus bouts — a pipeline measurement, not a finding about crows. "Not resolved" against raw at 24 clips per arm is not proven transparency; it means no difference was detectable at this power.

### What this changed

- The tokenizer is settled: DAC 24 kHz at 24 codebooks, 5,400 tokens per 3-second bout. Best quality available, indistinguishable from raw at this power, a quarter cheaper than the 32 cb rung 0033 landed on.
- A flat generator at the transparent bitrate is not viable, and this is the third independent line saying so: 5,400 tokens is three times the 1,811 the current generator handles, experiment 0030 showed 3,619 already loses, and the knee at 16–24 codebooks sits above anything a flat model has managed.
- WP2's coarse-plus-extender became the only route on the table, to be built on DAC-24 rather than EnCodec: an 8-codebook coarse stream is 1,800 tokens — almost exactly what the generator already trains on — with an extender filling stages 8–23 before decoding at 24.
- The 12 cb collapse is a warning about the coarse stream: at 0.33 it is the worst arm measured in this series, so coarse codes alone will not decode to anything listenable. Fine for the architecture — nothing ever decodes them alone — but the extender cannot be evaluated by listening to its input, and any intermediate audio will sound broken by design.
- Experiment 0017 was wrong about DAC-24 at 12 codebooks for the right reason: it called that rung poor on retention, and by ear it is poor too. The rungs it never tested are where the answer was.

The next question it posed — can predicted fine stages stand in for true ones, tested with no generator involved — became experiment 0035.
