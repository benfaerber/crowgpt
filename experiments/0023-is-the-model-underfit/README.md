# 0023 — Is the model underfit?

FUTURE.txt had said for a while that every capacity decision here was being made
blind, and it was right. `history.json` recorded `loss.item()` from ONE training
minibatch with dropout 0.25 still active and compared it against a 20-batch mean
under `eval()`. That is two different measurements rather than a gap, which is
why several came out negative — including the call-type run, where "train" sat
*above* "val" at step 38,000.

`Trainer.evaluate` now scores both splits the same way: same batch count, both
under `eval()`, a batcher of its own so scoring cannot perturb training's
sampling order. Twenty extra forward passes per eval, well under 1% of runtime.
The old figure is kept in each row as `train_minibatch` so older histories still
line up.

## The sweep

Five arms, 40,000 steps, same seed, one knob each. Every arm early-stopped at
38,000, so they are directly comparable.

| arm | best val | final gap (val − train) | batch | minutes |
|---|---:|---:|---:|---:|
| baseline (dropout 0.25) | 4.7021 | −0.008 | 16 | 72 |
| dropout 0.10 | 4.6573 | +0.011 | 16 | 69 |
| dropout 0.00 | 4.6230 | +0.036 | 16 | 67 |
| **batch 32** | **4.6043** | +0.104 | 32 | 140 |
| anneal to zero | 4.7018 | −0.011 | 16 | 69 |

## The answer: underfit, unambiguously

**The baseline gap is −0.008.** After 38,000 steps the model is no better on data
it trained on than on data it has never seen. There is no overfitting to
regularise against, so the dropout was paying a premium on insurance against a
risk that does not exist.

**Removing the dropout monotonically improves validation loss** — 4.7021 → 4.6573
→ 4.6230 as it goes 0.25 → 0.10 → 0.00. That is the clean signature: when
regularisation only ever costs you, the model cannot fit its own training set.

**Unclipping the batch helps most and is the only arm with a real gap.** A
requested batch of 32 had been silently running as 16 for the whole project,
clipped by a `budget = 240_000_000` constant nobody chose. Restoring it gives
the best validation loss of the five, 4.6043, and the first honest positive gap
(+0.104) — the first sign of the model beginning to prefer its training data.

Baseline to best is 0.098 nats, about **0.14 bits per token**. Real, and not
enormous.

## One measured null

**The learning-rate floor does nothing.** The cosine settles at 10% of peak and
never anneals, which looked like a plausible reason runs finish while still
moving. Annealing to zero scores 4.7018 against the baseline's 4.7021 — a
difference of 0.0003, which is nothing. That knob is closed; do not spend
another night on it.

## What this does not show

Validation loss is not the ear. 0022 established that BirdNET detection is
circular in crowgpt's favour, and the listening test is the only judge without
that bias. **A 0.14 bit improvement has not been shown to sound like anything
at all**, and the honest next step is to put the best checkpoint through the
60-trial sheet against the standing 75.0% [63, 85].

The two knobs that mattered have also never been combined: every arm moved one
thing. `batch 32 + dropout 0.00` is untested and is the obvious candidate for
the best configuration available without touching the architecture.

## Then the ear disagreed

The combined arm was sat on the 60-trial sheet, generated from its own weights,
against the standing sitting on `model-d384-6k`. Chance is the target, so higher
is worse:

| checkpoint | best val | listening | d′ | fooled him |
|---|---:|---:|---:|---:|
| model-d384-6k | 4.711 | 75.0% [63, 85] | 1.34 | 10 / 30 |
| batch-32-dropout-0 | **4.538** | **88.3% [80, 97]** | 2.27 | 4 / 30 |

**The better model is the more obvious one.** It fooled the listener four times
out of thirty where the older model managed ten, and both cells moved the same
way — generated clips spotted went 67% → 87%, and real clips wrongly called fake
went 17% → 10%. Ben's note, written without seeing any of these numbers, opens
"I feel like there was a minor quality degradation."

## The listener is not a stable instrument, and that was most of it

Ben's own objection to the comparison above: the two sittings were Friday 21:33
and Saturday 12:15. So the old checkpoint was re-sat on **fresh clips from the
same weights** on the Saturday morning, holding the listener constant and moving
only the model back.

| sitting | correct | 95% CI | d′ | fooled him |
|---|---:|---:|---:|---:|
| old model, Fri 21:33 evening | 75.0% | [63, 85] | 1.34 | 10/30 |
| new model, Sat 12:15 morning | 88.3% | [80, 97] | 2.27 | 4/30 |
| old model, Sat 12:29 morning (control) | 83.3% | [73, 92] | 1.91 | 7/30 |

**Identical weights scored 75.0% in the evening and 83.3% in the morning.**
Eight and a third points of listener, not model — roughly two thirds of the gap
that had just been written up as a quality regression. Practice is the likelier
half of it: the evening note ends "all the bad ones seem to have the xelophone /
modem sounds in them", so the tell was learned in sitting one and applied in
sitting two.

Morning against morning, the honest comparison is **88.3% vs 83.3% — paired
+0.067 [−0.133, +0.233], not significant.** Ben's note on the control says "it
is hard to tell which is better… if I had to say this one is slightly better",
which is the same faint lean and no more.

So the surviving claim is the narrow one: **0.164 nats of validation loss bought
no audible improvement.** Not that it made things worse. The wrong-way evidence
mostly belonged to the clock.

That is still enough to decouple loss from realism — an improvement this clean,
monotonic across five arms, should have shown up somewhere and did not.

## Settled: one sitting, both checkpoints, zero difference

The interleaved sheet was built and sat the same afternoon — 60 trials, 30 per
checkpoint, shuffled together, so practice and time of day apply equally to both.

| checkpoint | correct | 95% CI | d′ | fooled him |
|---|---:|---:|---:|---:|
| model-d384-6k | 86.7% | [73, 97] | 2.09 | 3/15 |
| batch-32-dropout-0 | 83.3% | [70, 97] | 1.79 | 2/15 |

**Paired on the 15 matched conditions: mean difference 0.000**, CI [−0.27,
+0.27]. He got exactly the same number right for each model.

So 0.164 nats of validation loss is audibly nothing — not better, not worse. And
the two earlier readings are explained: 13.3 points across an evening and a
morning, 5.0 points morning-to-morning, 0.0 within a single sitting. The apparent
effect shrank monotonically as the confound was removed, which is what a confound
looks like when it is taken out properly.

The interval is still ±0.27 on 15 pairs, so a moderate difference cannot be
excluded. What can be excluded is the one this experiment was built to find.

**The instrument needs fixing before it is trusted across sessions again.** Two
checkpoints compared in separate sittings are confounded by everything about the
listener that changed in between, and here that was larger than the effect being
measured. The fix is one sitting containing clips from both checkpoints,
interleaved and shuffled, so listener state and practice are shared and cancel.
Until that exists, a cross-session comparison needs a same-session control of
the kind that rescued this one.

## What changed

- **"Underfit or overfit" is settled**, and every capacity and regularisation
  decision that was waiting on it is unblocked. The model is capacity-starved,
  not over-regularised, which is the same direction 0019 pointed from the
  dead-codebook side — three of eight codebooks carrying no learned signal is
  what a model that cannot fit its data looks like from the other end.
- **Two defaults are now known to be wrong.** `dropout=0.25` costs about 0.08
  nats, and `memory_budget` has been halving the batch since the beginning.
  Neither should stay as the default.
- **The LR floor is closed** as a measured null.
- **More capacity is NOT the evidenced next move after all.** That was the
  conclusion until the sitting landed. The knobs did exactly what the loss said
  they would and the output got no better to a person, so spending a bigger
  model on the same objective is buying more of something that has just been
  shown not to convert. The lever is more likely the objective — flat
  cross-entropy weights all eight codebooks equally while three of them carry no
  learned signal (0019) — or the tokenizer, than raw parameter count.
- **Rank checkpoints by ear, not by validation loss** — but with a bigger ear
  than this. A 0.164 nat improvement, clean and monotonic across five arms,
  produced no measurable audible gain. Loss stays useful for catching breakage
  and has now failed once as a proxy for quality.
- **A single listener across two sittings is a confounded instrument.** Eight
  points moved on identical weights between an evening and a morning, which was
  larger than the model effect under test. Interleave both checkpoints in one
  sitting, or carry a same-session control. This nearly produced a wrong
  conclusion in this very file, and the objection came from Ben rather than from
  the analysis.

## Re-running

```bash
crowgpt/.venv/bin/python experiments/0023-is-the-model-underfit/run.py
```

About 7 hours for all five arms; each writes its own folder under
`crowgpt/results/sweep-0023/` and is skipped if already present, so an
interrupted night resumes rather than restarts.
