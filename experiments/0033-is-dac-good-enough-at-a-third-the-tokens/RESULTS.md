# 0033 — Is DAC good enough at a third the tokens?

## Overview

Experiment 0032 found that the EnCodec codec only becomes perceptually clean at 32 codebooks — 7,200 tokens for a 3-second bout, far beyond what the project's sequence model can handle — so the question became whether a different codec, DAC, could reach raw quality for fewer tokens. A blind listening sitting compared raw audio against EnCodec at 32 codebooks, DAC's 44 kHz model at 9 codebooks (about a third of the tokens), and DAC's 24 kHz model at 32 codebooks (matched tokens). The token-efficiency hope failed — DAC-44 at 9 codebooks is audibly worse than raw — but DAC-24 at 32 codebooks beat EnCodec by 27 points at identical token count and was the only arm a listener could not separate from raw. The answer is a better tokenizer at the same price, not a cheaper one, and it reversed an earlier rejection of DAC (experiment 0017) whose constraint had expired.

## In depth

### Method

2026-08-02, 120 blinded trials: raw / EnCodec-32 / DAC-44-9cb / DAC-24-32cb, 30 bouts per arm. Experiment 0017 had rejected DAC at matched token count (1,813 against 1,800, where DAC kept 48% of BirdNET's detections and EnCodec 97%) — but that comparison was conditioned on "the model's job must not get harder", a constraint 0032 removed by showing transparency costs 7,200 tokens anyway. DAC's 44 kHz model runs 86 fps with 9 codebooks, about 2,325 tokens per 3-second bout; DAC-24 at 32 codebooks is included at matched tokens to separate "DAC is a better codec" from "the 44 kHz frame rate is what buys it".

### Results

| arm | tokens / 3 s | good | rate | 95% CI |
|---|---|---|---|---|
| raw | — | 29/30 | 0.97 | [0.90, 1.00] |
| DAC 24 kHz, 32 cb | 7,200 | 28/30 | 0.93 | [0.83, 1.00] |
| DAC 44 kHz, 9 cb | ~2,325 | 24/30 | 0.80 | [0.67, 0.93] |
| EnCodec, 32 cb | 7,200 | 20/30 | 0.67 | [0.50, 0.83] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − DAC-24-32 | +0.03 | [−0.07, +0.13] | not resolved |
| raw − DAC-44-9 | +0.17 | [+0.03, +0.33] | resolved |
| raw − EnCodec-32 | +0.30 | [+0.13, +0.50] | resolved |
| EnCodec-32 − DAC-24-32 | −0.27 | [−0.47, −0.07] | resolved |
| EnCodec-32 − DAC-44-9 | −0.13 | [−0.37, +0.10] | not resolved |
| DAC-44-9 − DAC-24-32 | −0.13 | [−0.30, +0.03] | not resolved |

DAC-24 at 32 codebooks beats EnCodec at 32 codebooks by 27 points on identical token count, with an interval that excludes zero. It is also the only arm not separable from raw, and uniquely among the "not resolved" results in this series its interval is genuinely tight — ±10 points, because both proportions sit near ceiling. This is the closest thing to an equivalence result the project has, though still not a formal one.

DAC-44 at 9 codebooks — the token-efficiency candidate, at DAC's full 44 kHz bandwidth with no higher rung to try — lands at 0.80 and is resolved below raw. The cheap option is audibly not transparent, and the sequence-length problem is not solved by switching codec at this operating point.

### The confound, stated plainly

EnCodec-32 scored 0.80 in experiment 0032 and 0.67 here, and this data cannot say why. Three explanations are live and inseparable: different bouts (every sitting uses disjoint recordings, and 30 per arm leaves real sampling variation); peak-normalisation (0033 normalises every clip after decoding and 0032 did not, and codec ringing can push a decoded peak above the source, so normalisation lands unevenly across arms); and the comparison set (a clearly better arm in the sitting raises the implicit standard).

The raw anchor also moved — 0.85, 0.85, 0.87 in earlier sittings, then 0.97 here — for a known reason: the ≥1 s clip filter, which 0032's long-clip subset (0.96) already predicted. But a moved anchor is precisely what forbids cross-sitting comparison, so only the within-0033 comparisons should be trusted. "DAC-24-32 > EnCodec-32" is safe; "EnCodec got worse" is not a finding.

### Caveats

These are pipeline measurements over corpus bouts — codec round-trips rated by ear — not findings about crows. The equivalence of DAC-24-32 with raw is "not resolved at ±10 points", not proven transparency.

### What this changed

- The tokenizer is DAC-24 at 32 codebooks, not EnCodec: best arm tested, not separable from raw, 27 points clear of EnCodec at identical sequence length. Everything downstream should be rebuilt on it.
- Experiment 0017's rejection of DAC stands for its own question and is void for this one. Its measurement was right; the constraint it was conditioned on expired, and nobody had re-derived the conclusion. Worth remembering as a shape of error.
- The sequence-length problem is untouched: 7,200 tokens is still 7,200 tokens, and experiment 0030 showed a flat model at 3,619 already does not beat one at 1,811. WP2's coarse-plus-extender remains the only route to this bitrate — now built on DAC.
- BirdNET detection retention was the wrong instrument, twice: 0017 ranked DAC last on it and the ear ranks it first. Retention measures whether a classifier still fires, which is not what "sounds like a crow" means — the second time that gap produced a wrong call (see experiments 0022 and 0014).

The follow-up question it posed — how few DAC-24 codebooks are enough, since only the 32 rung had been heard — became experiment 0034.
