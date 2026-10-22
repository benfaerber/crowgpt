# 0037 — Does the best quality-per-token codec make a better generator?

**2026-08-02** · 72 blinded trials · **answer: no, and it is the finding of the
weekend**

## The question

Five sittings put the codec ceilings far apart:

| tokenizer | tokens / 3 s | ceiling by ear |
|---|---|---|
| EnCodec 8 cb | 1,811 | 0.45 (0028) |
| DAC-44 9 cb | 2,325 | 0.80 (0033) |
| DAC-24 24 cb | 5,400 | 0.88 (0034) |

The incumbent generator sits on the first row. The third was made unreachable
when 0035 killed the extender. The middle row had never been trained on: **28%
more tokens for 35 more points of ceiling**, which looked like the best trade
available.

Matched to `model-fair-k8` exactly — d384/L8/H6, effective batch 18, dropout 0,
30,000 steps — so the tokenizer is the only difference between the two
generators.

## Result

| arm | good | rate | 95% CI |
|---|---|---|---|
| real | 22/24 | 0.92 | [0.79, 1.00] |
| DAC-44 generated | 6/24 | 0.25 | [0.08, 0.42] |
| EnCodec-8 generated | 5/24 | 0.21 | [0.04, 0.38] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| real − DAC-44 gen | **+0.67** | [+0.46, +0.88] | **resolved** |
| real − EnCodec-8 gen | **+0.71** | [+0.50, +0.88] | **resolved** |
| DAC-44 gen − EnCodec-8 gen | +0.04 | [−0.21, +0.29] | not resolved |

**A 35-point ceiling improvement produced at most a 4-point generator
improvement.** Ben's note — *"dac44 the best, but it still needs work"* — matches
the direction of the point estimate, and the interval cannot separate the two
arms. The honest reading is not "DAC-44 is slightly better"; it is that **nearly
all of a large ceiling advantage failed to reach the output.**

Sizing that claim: for a difference to go undetected at 24 an arm it must be
under roughly 25 points. The ceiling advantage was 35. So at least ten points
were definitely lost, and the point estimate says closer to thirty-one.

## Why: the better codec is harder to model, and this is now a pattern

| | marginal entropy | model recovered | model cost by ear |
|---|---|---|---|
| EnCodec 8 cb | 8.983 bits | **+2.365 bits** | 0.45 → 0.21 (−0.24) |
| DAC-44 9 cb | 9.554 bits | **+1.401 bits** | 0.80 → 0.25 (−0.55) |

Per-stage marginals, 150 held-out bouts:

```
EnCodec 8cb : 7.53 8.36 8.84 9.18 9.39 9.48 9.55 9.54
DAC-44 9cb  : 7.59 9.28 9.73 9.84 9.88 9.89 9.92 9.93 9.92
```

**DAC packs more information into every token, so there is less redundancy left
for a sequence model to exploit.** The model recovered 41% fewer bits over the
marginal, and its cost by ear more than doubled — 0.24 points below ceiling on
EnCodec against 0.55 on DAC. Every point of ceiling the tokenizer won was handed
straight back at the model.

**This unifies three separate failures into one law:**

- **0030** — more EnCodec codebooks: no audible gain. More stages, each harder.
- **0035** — extender on DAC: 0/24. Fine stages at 9.935 bits, nothing to learn.
- **0037** — better codec end to end: no resolvable gain. 9.554 against 8.983.

**Codec efficiency and model learnability are in direct tension.** A codec that
uses its capacity well is, by construction, a codec whose tokens a model cannot
predict. Every attempt this weekend to improve the audio by improving the
tokenizer has been paid for at exactly the same place.

## What this changed

- **The binding constraint is the model, not the tokenizer.** PLAN-TIMBRE
  reopened the tokenizer on 0024's finding that the codec round-trip is audibly
  scratchy. That finding was right — 0028 confirmed it blind, 40 points — and it
  still does not help, because the generator cannot use a better tokenizer. Four
  tokenizer configurations have now been tried and the generated output has not
  moved outside [0.15, 0.25] for any of them.
- **Stop buying ceiling.** There is no configuration left that raises the codec
  ceiling and can be modelled; DAC-24 at 24 cb is the best available and 0035
  showed it is the least modellable of all. The next thing to change has to be
  the model, the objective, or the data.
- **The most promising unexplored lever is sequence length made cheap, not
  short.** `sample.py` records that there is no KV cache, so generation re-runs
  the whole forward pass per step and cost is quadratic in bout length — worth
  "roughly a thousandfold on the redundant work". That does not make a model
  learn more per token, but it is what would make a larger model or a longer
  context affordable, and every route left is on that side of the ledger.
- **A generated-audio result that is honestly a null.** Both generators sit
  around 0.21–0.25 against real audio's 0.92. The gap to real is 67–71 points and
  resolved in both cases. Nothing this weekend moved it.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0037-a-flat-generator-on-dac44/run.py
```

Tokenize 1.7 h, train 69 min, generate 2 min. Session in
`crowgpt/results/listening/dac44-gen-0037/`.
