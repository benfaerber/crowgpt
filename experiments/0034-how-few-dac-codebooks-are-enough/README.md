# 0034 — How few DAC-24 codebooks are enough?

**2026-08-02** · 120 blinded trials · raw + DAC-24 at 12, 16, 24, 32 codebooks

## The question

0033 found the tokenizer — DAC 24 kHz at 32 codebooks, the only arm a listener
could not separate from raw, and 27 points clear of EnCodec at identical
sequence length. But 32 codebooks is 7,200 tokens for a 3-second bout, and 0030
showed a flat model at 3,619 tokens already fails to beat one at 1,811.

**Only the 32 rung had ever been heard.** 0017 tested DAC-24 at 8 and 12 and
found both poor, but on BirdNET retention — the instrument that ranked DAC last
overall where the ear ranks it first. Everything between had never been played to
anyone, and every codebook that can be dropped without a listener noticing is
sequence length the generator does not have to learn.

## Results

| arm | tokens / 3 s | good | rate | 95% CI |
|---|---|---|---|---|
| raw | — | 22/24 | 0.92 | [0.79, 1.00] |
| DAC-24, 32 cb | 7,200 | 21/24 | 0.88 | [0.75, 1.00] |
| **DAC-24, 24 cb** | **5,400** | 21/24 | **0.88** | [0.75, 1.00] |
| DAC-24, 16 cb | 3,600 | 16/24 | 0.67 | [0.46, 0.83] |
| DAC-24, 12 cb | 2,700 | 8/24 | 0.33 | [0.17, 0.54] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − 32 cb | +0.04 | [−0.12, +0.21] | not resolved |
| raw − 24 cb | +0.04 | [−0.12, +0.21] | not resolved |
| raw − 16 cb | **+0.25** | [+0.04, +0.46] | **resolved** |
| raw − 12 cb | **+0.58** | [+0.38, +0.79] | **resolved** |
| 32 cb − 24 cb | **+0.00** | [−0.17, +0.21] | not resolved |
| 24 cb − 16 cb | +0.21 | [−0.04, +0.42] | not resolved |
| 16 cb − 12 cb | **+0.33** | [+0.04, +0.58] | **resolved** |

**Twenty-four codebooks is enough; the last eight buy nothing.** The 32 and 24
arms scored identically — a difference of exactly zero — and neither is separable
from raw. That is 5,400 tokens instead of 7,200, a 25% cut for no audible cost.

**The floor is sharp and it is close.** 16 cb is resolved below raw, and 12 cb
collapses to 0.33 — worse than any codec arm in any sitting this series,
including EnCodec at 6 kbps. So the knee sits between 16 and 24 codebooks, which
is between 3,600 and 5,400 tokens. Ben's note says the same thing from the
inside: *"dac24_24-dac24_32 are both pretty good most of the time."*

### This sitting replicates, which the last one could not

0033's cross-sitting comparisons had to be thrown out because its raw anchor
moved. This one carries the 32 cb arm forward on purpose, and both it and raw
land where they did:

| | 0033 | 0034 |
|---|---|---|
| raw | 0.97 | 0.92 |
| DAC-24, 32 cb | 0.93 | 0.88 |
| **raw − 32 cb** | **+0.03** | **+0.04** |

Both arms sit about five points lower — a whole-sitting shift, well inside noise
— and the *difference between them* is identical to within a point. That is what
a stable instrument looks like, and it is the first time in this series two
sittings have agreed on a repeated arm.

Pace was 1,416 ms a clip against 1,374 / 1,308 / 1,403 / 1,438 in the four
earlier sittings, so the fatigue this was warned about does not show up in the
timing either.

## What this changed

- **The tokenizer is settled: DAC 24 kHz at 24 codebooks, 5,400 tokens per
  3-second bout.** Best quality available, indistinguishable from raw at this
  power, and a quarter cheaper than the 32 cb rung that 0033 landed on.
- **A flat generator at the transparent bitrate is not viable, and this is the
  third independent line saying so.** 5,400 tokens is three times what the
  current generator handles at 1,811, and 0030 showed 3,619 already loses. The
  knee at 16–24 codebooks sits *above* anything a flat model has managed.
- **WP2's coarse-plus-extender is now the only route on the table**, and it
  should be built on DAC-24 rather than EnCodec: an 8-codebook coarse stream is
  1,800 tokens — almost exactly what the generator already trains on — with an
  extender filling stages 8–23 before decoding at 24.
- **The 12 cb collapse is a warning about the coarse stream.** At 0.33 it is the
  worst arm measured in this series, so the coarse codes on their own will not
  decode to anything listenable. That is fine for the architecture — nothing ever
  decodes them alone — but it does mean **the extender cannot be evaluated by
  listening to its input**, and any intermediate audio will sound broken by
  design.
- **0017 was wrong about DAC-24 at 12 codebooks for the right reason.** It called
  that rung poor on retention, and by ear it is poor too. The rungs it never
  tested are where the answer was.

## What to ask next

WP2 arm B, on DAC-24, as a ceiling test with no generator involved: take real
held-out bouts, encode at 24 codebooks, keep the first 8, predict stages 8–23
from them, decode, and rate against raw. If predicted fine stages cannot match
true fine stages on *real* coarse codes, the architecture fails before a
generator is ever attached — and that is a training run, not a sitting.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0034-how-few-dac-codebooks-are-enough/run.py
```

Session in `crowgpt/results/listening/dac24-ladder-0034/`.
