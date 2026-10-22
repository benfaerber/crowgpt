# 0033 — Is DAC good enough at a third the tokens?

**2026-08-02** · 120 blinded trials · raw / EnCodec-32 / DAC-44-9cb / DAC-24-32cb

## The question

0017 rejected DAC and was right about the question it asked: retention **at
matched token count**, 1,813 against 1,800, where DAC keeps 48% of BirdNET's
detections and EnCodec 97%. The constraint doing the work was *the model's job
must not get harder*.

0032 removed that constraint. The only rung a listener could not separate from
raw was EnCodec at 32 codebooks — **7,200 tokens** for a 3-second bout. So the
sequence length that buys transparency was never 1,800, and the question stopped
being "which codec is better at 1,800 tokens" and became: **can anything reach
raw quality for fewer than 7,200?**

DAC's 44 kHz model runs 86 fps with 9 codebooks — about 2,325 tokens for a
3-second bout, roughly a third — and 0017 measured its spectral distance *below*
EnCodec-32's. DAC-24 at 32 codebooks is in at matched tokens, to separate "DAC is
a better codec" from "the 44 kHz frame rate is what buys it".

## Results

| arm | tokens / 3 s | good | rate | 95% CI |
|---|---|---|---|---|
| raw | — | 29/30 | 0.97 | [0.90, 1.00] |
| **DAC 24 kHz, 32 cb** | 7,200 | 28/30 | **0.93** | [0.83, 1.00] |
| DAC 44 kHz, 9 cb | ~2,325 | 24/30 | 0.80 | [0.67, 0.93] |
| EnCodec, 32 cb | 7,200 | 20/30 | 0.67 | [0.50, 0.83] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − DAC-24-32 | +0.03 | [−0.07, +0.13] | not resolved |
| raw − DAC-44-9 | **+0.17** | [+0.03, +0.33] | **resolved** |
| raw − EnCodec-32 | **+0.30** | [+0.13, +0.50] | **resolved** |
| EnCodec-32 − DAC-24-32 | **−0.27** | [−0.47, −0.07] | **resolved** |
| EnCodec-32 − DAC-44-9 | −0.13 | [−0.37, +0.10] | not resolved |
| DAC-44-9 − DAC-24-32 | −0.13 | [−0.30, +0.03] | not resolved |

**0017's verdict is reversed at the new constraint.** DAC-24 at 32 codebooks
beats EnCodec at 32 codebooks by 27 points on identical token count, and the
interval excludes zero. It is also the only arm not separable from raw, and
uniquely among every "not resolved" result in this series **its interval is
genuinely tight** — ±10 points, because both proportions sit near ceiling and
that shrinks the variance. This is the closest thing to an equivalence result the
project has, though still not a formal one.

**The token-efficiency hope failed.** DAC-44 at 9 codebooks — DAC's 44 kHz model
at *full* bandwidth, so there is no higher rung to try — lands at 0.80 and is
resolved below raw. The cheap option is audibly not transparent, and the
sequence-length problem is not solved by switching codec at this operating point.

So the answer is a better tokenizer at the same price, not a cheaper one.

## The confound this sitting has, stated plainly

**EnCodec-32 scored 0.80 in 0032 and 0.67 here, and this data cannot say why.**
Three explanations are live and not separable:

1. **Different bouts.** Every sitting uses disjoint recordings; 30 an arm leaves
   real sampling variation.
2. **Peak-normalisation.** 0033 normalises every clip after decoding and 0032 did
   not. Codec ringing can push a decoded peak above the source, so normalising
   makes such a clip quieter — a change that lands unevenly across arms.
3. **The comparison set.** DAC-24-32 is in this sitting and was not in 0032. A
   clearly better arm raises the implicit standard, which is exactly the relative
   grading everyone was warned against and which no instruction fully prevents.

**The raw anchor also moved**, for a known reason: 0.85, 0.85, 0.87, then 0.97
here, and 0032's long-clip subset was already 0.96. The ≥1 s filter explains it.
But a moved anchor is precisely what licensed the cross-sitting comparison in
0030 and it is absent here, so **only the within-0033 comparisons above should be
trusted.** DAC-24-32 > EnCodec-32 is safe; "EnCodec got worse" is not a finding.

## What this changed

- **The tokenizer is DAC-24 at 32 codebooks, not EnCodec.** Best arm tested, not
  separable from raw, and 27 points clear of EnCodec at identical sequence
  length. Everything downstream should be rebuilt on it.
- **0017's rejection stands for its own question and is void for this one.** It
  measured DAC where the model's job had to stay constant. That constraint died
  when transparency turned out to cost 7,200 tokens. Worth remembering as a shape
  of error: the measurement was right, the constraint it was conditioned on
  expired, and nobody re-derived the conclusion.
- **The sequence-length problem is untouched.** 7,200 tokens is still 7,200
  tokens, and 0030 showed a flat model at 3,619 already does not beat one at
  1,811. WP2's coarse-plus-extender remains the only route to this bitrate — now
  built on DAC.
- **BirdNET retention was the wrong instrument for this, twice.** 0017 ranked DAC
  last on it; the ear ranks it first. Detection retention measures whether a
  classifier still fires, which is not what "sounds like a crow" means, and this
  is the second time that gap has produced a wrong call (0022, 0014).

## What to ask next

**How few DAC-24 codebooks are enough?** Only 32 has been heard. 0017 tested 8
and 12 and both were poor, but on retention rather than by ear, and the rungs
between — 16, 20, 24 — have never been played to anyone. DAC-24 at 16 codebooks
is 3,600 tokens; if that is clean, it halves the sequence length that
transparency costs and changes what the generator has to do.

`rate-dac24-ladder-blind.html` is built and waiting.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0033-is-dac-good-enough-at-a-third-the-tokens/run.py
```

Session in `crowgpt/results/listening/dac-blind-0033/`.
