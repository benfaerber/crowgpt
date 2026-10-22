# 0038 — Does dropping three inaudible codebooks make the model better?

**2026-08-03** · 96 blinded trials · **answer: no, sharply — and the sitting
found something bigger about the instrument**

## The question

0024 measured that replacing codebooks 5–7 with draws from the codec's own
marginals is **inaudible**, and drew the consequence itself: *"A 3-second bout is
1,800 tokens at eight codebooks and 1,125 at five, and attention is quadratic —
roughly 61% less attention compute per bout… Every training run in this project
has been paying for three stages that a listener cannot hear."*

Nobody had done it. And after a weekend in which every change made the model's
job *harder* — more codebooks, denser tokens, whiter residuals, each one handed
back at the model — this was the one available move that made it **easier**.

Two arms, both against the incumbent in the same sitting: `k5_matched` is
`model-fair-k8`'s exact recipe at five codebooks (16.6M params), and `k5_bigger`
spends the sequence saving on capacity (41M). Generation fills stages 5–7 from
the measured marginal and decodes at eight, so bitrate is held constant and only
the model moves.

## Result

| arm | good | rate | 95% CI |
|---|---|---|---|
| real | 22/24 | 0.92 | [0.79, 1.00] |
| **fairk8** (incumbent) | 13/24 | **0.54** | [0.33, 0.75] |
| k5-bigger (41M) | 4/24 | 0.17 | [0.04, 0.33] |
| k5-matched (16.6M) | 4/24 | 0.17 | [0.04, 0.33] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| fairk8 − k5-matched | **+0.38** | [+0.12, +0.62] | **resolved** |
| fairk8 − k5-bigger | **+0.38** | [+0.12, +0.62] | **resolved** |
| k5-bigger − k5-matched | +0.00 | [−0.21, +0.21] | not resolved |

**Five codebooks is much worse, and the interval excludes zero.** The saving is
real and the model does not convert it — it loses badly.

**Capacity again bought nothing.** 41M and 16.6M scored *identically*, 4/24 each.
0023 ruled capacity out and I argued it had only been ruled out at a fixed
sequence length, so this arm asked the question at a shorter one. Same answer.
That reframing was wrong and is withdrawn.

### Why it probably failed, and it was written down in advance

The experiment's own header flagged it: *"0024's inaudibility result was
collected on the incumbent's output. A 5-codebook model is a different
distribution, and the marginal fill could interact with it in a way three stages
of the incumbent's did not."*

0024 replaced stages 5–7 of a model that had **learned** them. Here the model
never saw them, so its coarse codes are free to drift somewhere the independent
marginal fill does not sit on top of. Inaudibility of a residual, measured on one
distribution of coarse codes, does not transfer to a model trained without it.

Separable and cheap to check: take `fairk8`, keep its first five rows, fill 5–7
from the same marginal, and rate that. If it also collapses, the fill is the
problem; if it survives, training at K=5 is. That is 0024's test run on 2026's
better-trained incumbent, and it is worth doing before this null is quoted as
"short sequences do not help".

## The bigger finding: the same model moved 33 points

`fairk8` is unchanged weights, rated in two consecutive sittings:

| | 0037 | 0038 |
|---|---|---|
| fairk8 | **0.21** | **0.54** |
| real anchor | 0.92 | 0.92 |

**The real anchor did not move at all, and the model moved 33 points.** So the
control that has been licensing every cross-sitting comparison in this series
does not protect against whatever this is.

Every repeated arm in the series, against its rank inside its own sitting:

| arm | sitting A | rank | sitting B | rank | Δ |
|---|---|---|---|---|---|
| EnCodec-32 | 0.80 (0032) | 2nd of 4 | 0.67 (0033) | 4th of 4 | **−13** |
| DAC-24 32cb | 0.93 (0033) | 2nd of 4 | 0.88 (0034) | 2nd of 5 | −5 |
| fairk8 | 0.21 (0037) | 3rd of 3 | 0.54 (0038) | 2nd of 4 | **+33** |

**When an arm's rank inside its sitting changes, its score moves with it; when
rank holds, the score holds.** That is a contrast effect, not drift: the listener
is grading each clip against the company it is keeping, which is exactly the
relative grading warned against before the first sitting and which no
instruction reliably prevents.

It is also much larger than 0023's 8.3-point session drift, and larger than most
of the model effects this project has been chasing.

**What survives and what does not.** Within-sitting comparisons are unaffected —
every arm met the same company — so this experiment's own result stands.
Cross-sitting *absolute* rates do not, which retires 0037's line that generated
output "never left [0.15, 0.25]" (it reached 0.54) and weakens the cross-sitting
ladder assembled in 0030.

## What this changed

- **Shorter sequences do not help, at least not this way.** The 61% compute
  saving 0024 identified is real and unclaimable by this route.
- **Capacity is now ruled out twice**, at two sequence lengths, on two model
  sizes each. It should stop being proposed.
- **0024's inaudibility does not transfer to a model trained without the
  stages.** A property of a residual measured on one coarse distribution is not
  a property of the codec.
- **Every future sitting needs a fixed reference arm set**, or arms whose rank
  shifts will move for reasons that have nothing to do with the model. The
  cheapest fix is to keep `real` *and* the standing incumbent in every sitting,
  which this one happened to do.
- **The stronger fix is to stop asking for absolute ratings.** A paired
  forced-choice — this clip or that one — has no company to grade against and is
  far more powerful per trial. That is the next tooling job.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0038-stop-paying-for-inaudible-codebooks/run.py
```

Tokenize 15 min, arms 34 and 63 min. Session in
`crowgpt/results/listening/k5-0038/`.
