# 0030 — Does flat-at-12-kbps still lose once the two known bugs are gone?

**Started 2026-08-01, overnight** · two training arms, identical recipe, one
difference · results below fill in when the run lands

## The question

PLAN-TIMBRE's diagnosis point 4 rests on 0018's ladder: flat training at 12 kbps
detected 41.7% against 66.7% at 6 kbps, and that number has been quoted ever
since as *higher bandwidth costs more in sequence length than it returns in
ceiling*. 0023 later showed that run carried two defaults the project has since
disowned:

- the batch was **silently clipped to about 4** by the `memory_budget` constant
  (`240_000_000 // (3607 × 16420)`), not the 32 that was asked for;
- **dropout was 0.25**, which 0023 measured as wrong for this corpus.

So a fair flat-at-high-bandwidth attempt has never actually run, and a
load-bearing claim rests on a run nobody would repeat. Even a failure here is
information, which is what makes it worth a night.

**It is also WP2's prerequisite**, which is why it went first rather than after
the WP1 listening gate. The extender in WP2 trains on exactly this token stream
at exactly this block size; if a K=16 model cannot be trained well at all on this
hardware, the extender inherits that before it inherits anything else.

## Why there are two arms

The incumbent `model-d384-6k` trained at dropout 0.25 and effective batch 16.
This run is dropout 0 at effective batch 18. Comparing flat-K16 against the
incumbent would therefore move **bandwidth, dropout and batch size together**,
and any difference could be credited to the wrong one.

That is the trap 0027 closed owing a control for — *"a same-size control is owed
before this result is quoted as 'filtering does not work' rather than 'filtering
at 45% of the data does not work'"*. So `model-fair-k8` is the identical recipe
at eight codebooks, and **bandwidth is the only thing that differs**.

| | flat-k16 | fair-k8 (control) | incumbent (for reference) |
|---|---|---|---|
| codebooks | 16 (12 kbps) | 8 (6 kbps) | 8 (6 kbps) |
| architecture | d384 L8 H6 | d384 L8 H6 | d384 L8 H6 |
| effective batch | 18 (6 × 3) | 18 (18 × 1) | 16 |
| dropout | 0 | 0 | 0.25 |
| steps | 30,000 | 30,000 | — |

A guard aborts the run if the `memory_budget` heuristic clips either arm off the
shared effective batch of 18. The whole point of the control is that one number
differs; if the batch drifted, it does not.

## Two things measuring this taught us about the tooling

**Gradient accumulation had to be built first.** The logits tensor is
`[batch, time, vocab]` and both time and vocab double with the codebook count, so
it grows fourfold from 6 to 12 kbps. Measured on the 4070 Ti: the d384/L8 shape
fits a micro-batch of **6** at K=16 and OOMs at 8. PLAN-TIMBRE's own command —
`--batch-size 16 --memory-budget 1000000000` — does not fit. Without
accumulation, a bandwidth comparison is also a batch-size comparison.

**The synthetic benchmark was wrong by 3×, usefully.** Timing a full
3,619-token block said 1.11 s a step and would have forced a much smaller step
budget. `Batcher` pads to the longest sequence *in the batch*, not to
`block_size`, and the median bout is about a third of the block — so real steps
are roughly three times cheaper. The step budget came off the live run instead.

## Results

**Ran 2026-08-01 21:07 → 00:55, 3.8 h.** K=16 took 2.7 h, the K=8 control 61 m.
Both arms ran the full 30,000 steps without early stopping, and both found their
best validation loss around step 26,500–27,000 and then oscillated — so the step
budget was adequate and neither arm is meaningfully undertrained. That was not
guaranteed and it is what makes the comparison readable.

**Validation loss is not compared across the arms, and must not be.** K=8 and
K=16 have different vocabularies and different sequence lengths, so 4.5874 and
5.1346 are different quantities that happen to share a unit.

### Bits recovered over the codec marginal

| stage | K=16 arm | K=8 control | | stage | K=16 arm |
|---|---|---|---|---|---|
| 0 | 3.423 | 3.278 | | 8 | 1.527 |
| 1 | 2.854 | 2.765 | | 9 | 1.438 |
| 2 | 2.801 | 2.688 | | 10 | 1.314 |
| 3 | 2.443 | 2.403 | | 11 | 1.245 |
| 4 | 2.208 | 2.119 | | 12 | 1.183 |
| 5 | 2.001 | 1.883 | | 13 | 1.072 |
| 6 | 1.818 | 1.677 | | 14 | 1.024 |
| 7 | 1.661 | 1.460 | | 15 | 0.939 |

Coarse mean +2.401, fine mean **+1.218**.

**WP2's gate 1 passes on bits, and the prediction from 0028 was wrong.** 0028
measured the fine-stage marginal at ~9.5 bits of a possible 10 and inferred that
a near-white residual would be hard to model. It is not: the model recovers 0.94
to 1.53 bits in stages 8–15, comfortably over the plan's "+0.3 bits" bar. Writing
that down because the inference was mine and it did not survive contact.

### …but the gate it passes cannot mean what the plan wants it to mean

The K=8 control is what makes this legible, and it is the reason the control was
worth a GPU-hour. **At K=8 the model recovers 1.883, 1.677 and 1.460 bits in
codebooks 5, 6 and 7 — and 0024 established by ear that replacing exactly those
three codebooks with draws from the codec's own marginals is inaudible.**

So a stage can recover ~1.5–1.9 bits and still carry nothing a listener can hear.
"Beats the codec marginal by more than 0.3 bits" is therefore not evidence about
audibility; it is comfortably satisfied by stages already proven inaudible.

And WP2's target stages recover **0.94–1.53 bits — a band lying entirely below
the one already shown to be inaudible.**

The honest counter-argument, which this does not close: 0024 removed three
stages, and WP2 would be adding eight. Bits recovered per stage is not obviously
additive in perceptual terms, and eight stages at ~1.2 bits each is ~9.8 bits of
recovered information rather than ~5. Whether that sums to something audible is
exactly what `rate-flat-k16.html` is for. What can be said now is that the
plan's *automated* gate has lost its ability to discriminate — it would wave
through a model whose stages are individually below the known-inaudible
threshold.

### Calibration is flat, at K=16 as well

Cross-entropy equals predictive entropy at every one of the 16 stages
(overconfidence between −0.05 and +0.02) and the loss-minimising temperature is
**1.00 at every stage**. The model is not blurry in the fine codebooks; it is
*correctly uncertain* there. Both arms return `StageProfile`'s own verdict —
*"flat calibration — a per-stage temperature is a global one in a costume, and
the idea is dead"* — which 0019 found at 8 codebooks and which now also holds at
16.

This is the outcome `stages.py` flags as the one to watch for, *"because high
fine-stage entropy feels like confirmation while being the opposite."*

### Density: mostly a training-recipe artefact, not a modelling defect

Units per bout, 20 clips per arm, same `Segmenter` at the shipped 12 dB:

| arm | mean units | single-unit share |
|---|---|---|
| real | 3.70 | 20% |
| flat-k16 | 2.60 | 35% |
| fair-k8 | 2.35 | 30% |
| incumbent (0024) | 1.37 | 70% |

**The gap 0024 measured has roughly halved without anyone touching the loss.**
The incumbent sat at 1.37 units against real audio's 3.37 and was 70%
single-caw; the same architecture at dropout 0, effective batch 18 and 30,000
steps sits at 2.35–2.60 and 30–35%. Nothing here weights silence — this is
0023's recipe correction alone.

WP4 proposes a burst-weighted loss to close that gap. Most of it has already
closed, which changes what WP4 would be measuring. n=20 per arm, so flat-k16
against fair-k8 (2.60 vs 2.35) is not a difference this can resolve.

## What this changed

- **WP2's automated kill gate is dead as a discriminator, and the control is
  what killed it.** "+0.3 bits over the marginal" is passed comfortably by
  codebooks 0024 already proved inaudible. Any future version of that gate has
  to be calibrated against a listening result, not against zero. The number to
  beat is not 0.3 bits — it is whatever 1.9 bits failed to buy.
- **A prediction of mine did not survive.** From 0028's near-white marginal I
  argued the fine stages would be hard to model. They are not. The entropy of a
  residual says little about how much of it is predictable from context, and I
  should not have reasoned from one to the other.
- **Per-stage temperature is dead at 16 codebooks too.** Flat calibration at
  T=1.00 across every stage, in both arms. 0019 found this at 8; it is not a
  small-model artefact.
- **WP4 lost most of its premise to a training-recipe fix.** Units per bout went
  from 1.37 to 2.35–2.60 against real audio's 3.70, with no loss change at all.
  A burst-weighted loss would now be chasing a much smaller gap than 0024
  measured, and should be re-costed before it is built.
- **Diagnosis point 4 is closed, and WP3 with it.** Flat-at-12-kbps had its fair
  attempt against a matched control and still does not beat 6 kbps by ear.
  0018's conclusion was right; only its reasoning was accidental. WP3 should be
  struck from the plan as *done and null*, not carried as an available fallback.
- **The two defects are now sized against one scale**, and the codec is the
  bigger one: −40 points for the round-trip at 6 kbps against −20 more for the
  generator on top. Fixing either alone leaves the other's deficit standing,
  which is the thing PLAN-TIMBRE does not currently have a work package for.
- **Two trained checkpoints that are not the incumbent**, both at dropout 0 and
  effective batch 18: `results/model-flat-k16` and `results/model-fair-k8`.
  Neither is promoted; `results/model` is untouched.

## The sitting — rated 2026-08-02, blind

60 trials, waveform hidden, 20 clips per arm.
`crowgpt/results/listening/flat-k16-0030/`.

| arm | good | rate | 95% CI |
|---|---|---|---|
| real | 17/20 | 0.85 | [0.70, 1.00] |
| fair-k8 | 5/20 | 0.25 | [0.10, 0.45] |
| flat-k16 | 3/20 | 0.15 | [0.00, 0.35] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| real − flat-k16 | **+0.70** | [+0.45, +0.90] | **resolved** |
| real − fair-k8 | **+0.60** | [+0.35, +0.85] | **resolved** |
| flat-k16 − fair-k8 | −0.10 | [−0.35, +0.15] | not resolved |

**Twelve kbps does not beat six, at a matched recipe.** The difference is not
resolvable, and the point estimate runs the wrong way. Diagnosis point 4 is
closed: 0018's ladder reached the right conclusion, and it did so for a reason
that survives fixing the batch clip and the dropout. **WP3 has now been run —
it is not a fallback that remains available, it is a null that has been
collected.**

### Cross-sitting decomposition, licensed by the control

The two sittings ran back to back, which is the setup 0023 measured 8.3 points of
listener drift in, so comparing across them was pre-committed against. **The
control arm makes it legitimate anyway: real audio scored 17/20 in both.** With
the yardstick demonstrably unmoved, the arms line up on one scale:

| | good-rate | cost against real |
|---|---|---|
| real | 0.85 | — |
| codec K=16 (0028) | 0.65 | −0.20 |
| codec K=8 (0028) | 0.45 | −0.40 |
| model fair-k8 | 0.25 | −0.60 |
| model flat-k16 | 0.15 | −0.70 |

Both defects are real and **the codec is the larger single one.** Running real
audio through the codec at 6 kbps costs 40 points; the generator then costs a
further 20 on top (+0.20, CI [−0.10, +0.50] — same direction as the d′ = 1.34
interleaved result, not resolvable at this n).

The uncomfortable consequence: **fixing either one alone is not enough.** A
perfect generator on this tokenizer inherits a 40-point deficit, and a perfect
tokenizer under this generator still lands around 45. Nothing in PLAN-TIMBRE
currently addresses both, and WP2 was the piece meant to attack the codec half —
which 0028's plateau and this null between K=8 and K=16 both undercut.

## Still owed

Nothing on this experiment — both arms trained, profiled and rated.

What it hands to the next one: the 10-point gap between the two model arms and
the 20-point gaps in 0028 are all below what 20 trials an arm can resolve.
Anything that wants to settle them needs roughly **70–95 trials per arm**, which
is three to five sittings, and should only be spent once there is a candidate
worth that much of Ben's attention. On present evidence neither K=16 model is
one.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0030-a-fair-flat-run-at-k16/run.py
```

Resumable: every stage checks for its own output first, so a re-run skips the
16-minute tokenize and any finished arm. Nothing here writes to `results/model`,
which is what the published demo plays.
