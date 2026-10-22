# 0032 — Where is the perceptual knee, blind?

## Overview

Earlier blind listening (experiment 0028) tested the audio codec only up to 16 codebooks, because the plan assumed transparency would arrive at or below that rung. Then Ben, browsing an unblinded ladder, reported that the 24- and 32-codebook versions sounded much better — an impression worth exactly one blinded sitting to check. The blind test confirmed and sharpened it: 32 codebooks is the only rung a listener could not distinguish from raw audio, while 24 and 16 codebooks are both audibly worse. This moved the answer to "what codec setting is transparent" up to K=32, which lands the plan on its escalate branch — a 3-second bout at that rate is 7,200 tokens, more than a flat sequence model has ever handled well.

## In depth

### Method

2026-08-02, 120 blinded trials, four arms — raw / K=16 / K=24 / K=32 — at 30 disjoint bouts each, none reused from experiment 0028, so nothing was heard twice across the two sittings. No model anywhere; this rates codec round-trips only. The prompt was Ben's unblinded impression: "K=8 major robot vibes. K=16 is similar to K=8. K=24 is pretty good. K=32 less but still a little. K=32 is the superior one."

### Results

| arm | good | rate | 95% CI |
|---|---|---|---|
| raw | 26/30 | 0.87 | [0.73, 0.97] |
| K=32 | 24/30 | 0.80 | [0.63, 0.93] |
| K=24 | 19/30 | 0.63 | [0.47, 0.80] |
| K=16 | 17/30 | 0.57 | [0.40, 0.73] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − K=32 | +0.07 | [−0.13, +0.27] | not resolved |
| raw − K=24 | +0.23 | [+0.03, +0.43] | resolved |
| raw − K=16 | +0.30 | [+0.10, +0.50] | resolved |
| K=32 − K=24 | +0.17 | [−0.07, +0.40] | not resolved |
| K=24 − K=16 | +0.07 | [−0.17, +0.30] | not resolved |

The impression survived blinding and moved the knee one rung higher than the labelled reading suggested. The ordering is raw ≈ K=32 > K=24 ≈ K=16, and Ben's own note refined to exactly that: "k32 far superior most of the times. k24 can keep up most of the time but fails."

### What this does not say

K=32 is not proven transparent. "Not resolved" is not "equivalent" — the interval on raw − K=32 runs to +27 points, and this sitting could not have detected anything under about 25 points. The genuinely informative part is the asymmetry: at identical power, differences were detected for K=16 and K=24 and not for K=32. A real equivalence claim at ±10 points would need roughly 200 trials per arm, now worth considering for K=32 specifically and only for K=32.

### Short clips were noise

Ben spotted it live: "clips under ~1 second were very hard to grade." Twenty-one of the 120 clips were under a second. Excluding them:

| arm | all 120 | ≥ 1.0 s |
|---|---|---|
| raw | 0.87 (26/30) | 0.96 (24/25) |
| K=32 | 0.80 (24/30) | 0.84 (21/25) |
| K=24 | 0.63 (19/30) | 0.67 (18/27) |
| K=16 | 0.57 (17/30) | 0.68 (15/22) |

The raw arm tightens to 0.96 — nearly every long real clip is called good, which is what a healthy control should look like. Conclusions do not change (raw − K=32 stays unresolved at +0.12, raw − K=24 stays resolved at +0.29). Future sittings should filter bouts under 1 s at build time, since a too-short clip contributes a near-coin-flip to every arm, and post-hoc filtering makes the arm sizes uneven (25/25/27/22).

### Caveats

This measures the codec pipeline on corpus bouts, not anything about crows. The bouts are drawn from the corpus, which is mostly seeded archive audio; the finding is about how many codebooks the codec needs to be perceptually clean, and does not depend on which recordings are genuine field captures.

### What this changed

- WP1 has an answer: K* = 32, not "≤ 16" as the plan's branch structure assumed. Every rung below 32 is audibly worse than raw.
- The plan lands on its escalate branch: at 32 codebooks a 3-second bout is 7,200 tokens, and experiment 0030 already showed a flat model at 3,619 tokens does not beat one at 1,811. Flat sequence modelling at K* is dead, now measured from both ends rather than assumed.
- WP2's coarse-plus-extender went from doubtful to the main candidate: the audible difference lives between 24 and 32 codebooks, and that architecture is the only route to that bitrate that does not ask a generator for 7,200 tokens.
- Both automated instruments (STFT distance and AST embeddings) rank the rungs correctly but locate no knee — STFT moves 1.046 → 1.035 between 24 and 32, its smallest step. They can choose which rungs deserve a sitting; they cannot say where audibility breaks.
- A mechanism worth testing was noted: coarse RVQ produces a metallic warble that disappears above a threshold rather than fading smoothly — a low-energy, high-salience artefact that spectral distance and mean-pooled embeddings underweight, which would explain a sharp perceptual knee under two smooth instrument curves.
