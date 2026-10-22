# 0032 — Where is the perceptual knee, blind?

**2026-08-02** · 120 blinded trials · raw / K=16 / K=24 / K=32 · no model anywhere

## The question

0028 ran its blinded sitting as raw / K=8 / K=16, because PLAN-TIMBRE's branch
structure assumed K\* would be 16 or below. It came back raw 0.85, K=16 0.65,
K=8 0.45 — only the K=8 gap resolved.

Then Ben browsed the **labelled** ladder and said something that page could not
have caught, because it never played the upper rungs:

> K=8 major robot vibes. K=16 is similar to K=8. K=24 is pretty good. K=32 less
> but still a little. K=32 is the superior one.

Unblinded, in the direction the labels invite, and against two automated
instruments that show no knee anywhere near there. Worth exactly one blinded
sitting.

Four arms at 30 disjoint bouts each, none of them reused from 0028, so nothing
was heard twice across the two sittings.

## Results

| arm | good | rate | 95% CI |
|---|---|---|---|
| raw | 26/30 | 0.87 | [0.73, 0.97] |
| K=32 | 24/30 | 0.80 | [0.63, 0.93] |
| K=24 | 19/30 | 0.63 | [0.47, 0.80] |
| K=16 | 17/30 | 0.57 | [0.40, 0.73] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − K=32 | +0.07 | [−0.13, +0.27] | not resolved |
| raw − K=24 | **+0.23** | [+0.03, +0.43] | **resolved** |
| raw − K=16 | **+0.30** | [+0.10, +0.50] | **resolved** |
| K=32 − K=24 | +0.17 | [−0.07, +0.40] | not resolved |
| K=24 − K=16 | +0.07 | [−0.17, +0.30] | not resolved |

**The impression survived blinding, and it moved the knee one rung further up
than the labelled reading suggested.** K=32 is the only arm not distinguishable
from raw. K=24 and K=16 are both resolved *below* raw and are indistinguishable
from each other. So the ordering is **raw ≈ K=32 > K=24 ≈ K=16**, and Ben's own
note refines his earlier reading to exactly that: *"k32 far superior most of the
times. k24 can keep up most of the time but fails."*

### The one thing this does not say

**K=32 is not proven transparent.** "Not resolved" is not "equivalent" — the
interval on raw − K=32 runs to +27 points, and this sitting could not have
detected anything under about 25. What is genuinely informative is the
*asymmetry*: at identical power, differences were detected for K=16 and K=24 and
not for K=32. That is evidence about where the threshold sits, not a
demonstration that the codec has become inaudible.

A real equivalence claim at ±10 points needs roughly 200 trials per arm. On this
result that is now worth considering for K=32 specifically, and only for K=32.

### Short clips were noise, and Ben spotted it live

His note: *"clips under ~1 second were very hard to grade."* Twenty-one of the
120 clips were under a second. Excluding them:

| arm | all 120 | ≥ 1.0 s |
|---|---|---|
| raw | 0.87 (26/30) | **0.96 (24/25)** |
| K=32 | 0.80 (24/30) | 0.84 (21/25) |
| K=24 | 0.63 (19/30) | 0.67 (18/27) |
| K=16 | 0.57 (17/30) | 0.68 (15/22) |

The raw arm tightens from 0.87 to 0.96 — nearly every long real clip is called
good, which is what a healthy control should look like. The conclusions do not
change (raw − K=32 stays unresolved at +0.12, raw − K=24 stays resolved at
+0.29), but the ceiling gets much cleaner.

**Filter bouts under 1 s out of future sittings.** A clip too short to judge
contributes a near-coin-flip to every arm and costs power in all of them. The
arm sizes go uneven when filtering after the fact (25/25/27/22), which is the
other reason to do it at build time instead.

## What this changed

- **WP1 has an answer: K\* = 32.** Not "≤ 16", which is what PLAN-TIMBRE's
  branch structure was built around and what 0028's sitting was designed to
  test. Every rung below 32 is audibly worse than raw.
- **PLAN-TIMBRE lands on its escalate branch**, the one it gives three lines to:
  *"K\* = 32 → stop and escalate. The sequence-model route is likely dead."* At
  32 codebooks a 3-second bout is 7,200 tokens, and 0030 already showed a flat
  model at 3,619 tokens does not beat one at 1,811. **Flat sequence modelling at
  K\* is dead, and that is now measured from both ends rather than assumed.**
- **WP2's extender goes from doubtful to the main candidate.** This morning's
  argument against it — fine stages recover ~1.2 bits, below the band 0024
  proved inaudible — was about stages 8–15, and this sitting agrees with it:
  K=16 buys nothing audible over K=8. But the audible difference does live
  somewhere between 24 and 32, and a coarse-plus-extender architecture is the
  only route to that bitrate that does not ask a generator for 7,200 tokens.
  The argument I made this morning was right about its own stages and wrong as a
  verdict on the plan.
- **Both instruments rank correctly and locate nothing.** STFT and AST agreed on
  the ordering of all five rungs, and neither shows a knee between 24 and 32 —
  STFT moves 1.046 → 1.035 there, its smallest step. They can *choose which
  rungs deserve a sitting*; they cannot say where audibility breaks. That is
  worth knowing before either is used as a gate again.
- **A mechanism worth testing.** Coarse RVQ produces a metallic warble that
  disappears above a threshold rather than fading smoothly. That is a
  low-energy, high-salience artefact — precisely what spectral distance and mean
  pooled embeddings underweight — and it would explain a sharp perceptual knee
  under two smooth curves.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0032-where-is-the-knee-between-16-and-24/run.py
```

About 90 seconds. Writes `clips.json` here and the page into `crowgpt/results/`.
Session in `crowgpt/results/listening/upper-rungs-0032/`.
