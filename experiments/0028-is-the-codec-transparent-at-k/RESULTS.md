# 0028 — What does each additional EnCodec codebook actually buy?

## Overview

Experiment 0024 established by ear that the audio codec's round-trip at 6 kbps is audibly "scratchy" against raw audio, which reopened the tokenizer as a suspect for the generator's synthetic sound. This experiment asked the obvious follow-up: how many codec codebooks does it take before a listener stops hearing the degradation? On 200 held-out American Crow bouts with no model anywhere, both automated instruments show quality improving monotonically with codebook count but plateauing well short of transparency — at maximum bandwidth the round-trip still sits a third of the way to an unrelated recording. A blinded sitting confirmed the founding claim (raw beats the 8-codebook round-trip by 40 points of good-rate, interval excluding zero) but could not resolve where the perceptual threshold lies, so the experiment ends with an ordering and without a transparency point — and with the implication that more bandwidth is not the lever.

## In depth

Run 2026-08-01 on 200 held-out American Crow bouts, one per recording, no model anywhere. This was WP1 of the timbre plan (since deleted), plus the cheapest available kill gate for its WP2. There was also a contradiction to resolve first: 0024 Part 1 found that replacing codebooks 5–7 with noise is inaudible and located the artefact in codebooks 0–4 — and if the last three of eight rows carry nothing audible, rows 8–31, a strictly smaller residual, should carry less still.

### 1. Truncating a high-bandwidth encode is exact

A 6 kbps encode is bit-identical to the first 8 rows of a 24 kbps encode, across every frame tested — 0 mismatched frames. EnCodec's RVQ is greedy-sequential, so stage *k* cannot depend on a later stage; this is now checked rather than assumed, which makes `Codec(keep=K)` safe and lets the ladder compare non-native rungs (12 and 24 codebooks) against native ones.

### 2. The ladder is monotone, and it plateaus well short of transparent

| K | kbps | STFT to raw | 95% CI | as % of ceiling | AST FAD | above floor |
|---|---|---|---|---|---|---|
| 8 | 6 | 1.165 | [1.149, 1.182] | 37.7% | 40.13 | 16.54 |
| 12 | 9 | 1.110 | [1.094, 1.127] | 35.9% | 35.27 | 11.68 |
| 16 | 12 | 1.077 | [1.060, 1.095] | 34.9% | 32.89 | 9.31 |
| 24 | 18 | 1.046 | [1.029, 1.064] | 33.9% | 30.79 | 7.20 |
| 32 | 24 | 1.035 | [1.018, 1.054] | 33.5% | 30.27 | 6.68 |

Every rung beats K=8 by a paired-bootstrap interval that excludes zero, so the improvement is real. It is also small, and it stops: between K=24 and K=32 the spectral distance moves 0.011 — a quarter of the K=8→K=12 step — for another 6 kbps.

Two controls make those numbers readable. The **ceiling, 3.090**, is the STFT distance between a raw bout and a *different* raw bout — what the metric reads for two unrelated crow recordings. The **floor, 23.58**, is the AST Fréchet distance between two disjoint halves of the raw set — pure sampling noise, comparable because every FAD here is 100-vs-100 (Fréchet distance on 768-d embeddings is badly biased upward at these sample sizes and the bias depends on *n*). Against those: at maximum bandwidth the round-trip still sits a third of the way to an unrelated recording and 6.7 FAD above the noise floor. The curve flattens toward something that is not zero, and EnCodec has no rung above K=32 to offer.

### 3. The fine stages are nearly white

Per-stage marginal entropy, of a possible 10 bits, pooled over 200 recordings: stages 0–7 run 7.57, 8.37, 8.86, 9.19, 9.39, 9.49, 9.55, 9.55; stages 8–15 sit at 9.38–9.63; stages 16–31 drift down from 9.25 to 8.78. Stages 8–15 at about 9.5 bits of 10 — 95% of uniform — are exactly the stages WP2 proposed training a second model to predict from coarse context, with a gate of "beat the codec marginal by more than 0.3 bits". Predicting a near-white residual is a hard ask by construction, and this is precisely the outcome `stages.py`'s own docstring warns about: high fine-stage entropy feels like confirmation while being the opposite. It does not kill WP2 on its own, but the prior is now unfavourable and measured.

These marginals are deliberately not `stages.CODEC_MARGINAL_BITS`: that table is 0014's, measured on BirdNET-gated windows, and reads about 1.5 bits lower because gated windows are denser and more stereotyped. Changing the shared constant would silently move every StageProfile number experiments 0019, 0023 and 0027 ever reported, so it was left alone.

### The blinded sitting (rated 2026-08-02)

60 trials, waveform hidden, 20 disjoint bouts per arm.

| arm | good | rate | 95% CI |
|---|---|---|---|
| raw | 17/20 | 0.85 | [0.70, 1.00] |
| K=16 | 13/20 | 0.65 | [0.45, 0.85] |
| K=8 | 9/20 | 0.45 | [0.25, 0.65] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − K=8 | +0.40 | [+0.10, +0.65] | resolved |
| raw − K=16 | +0.20 | [−0.05, +0.45] | not resolved |
| K=8 − K=16 | −0.20 | [−0.50, +0.10] | not resolved |

The founding claim survives blinding: 0024's "scratchy" verdict was given on a labelled page, and collected blind against a raw control, the 6 kbps round-trip costs 40 points of good-rate with an interval excluding zero. But K\* cannot be named, and that was predictable: at 20 trials an arm the sitting can resolve the 40-point gap and not the two 20-point ones. Sizing the follow-up honestly, separating raw from K=16 at 80% power needs about 70 trials per arm, and K=8 from K=16 about 95 — three to five more sittings. Ben's note — "Some were quite good on k16. It fools me for a low quality crow audio" — is a 0.65 good-rate in words.

Pace, recorded rather than corrected: median 1.37 s to decide, 54 of 60 clips played once, 51 of 60 decisions under two seconds. The ratings are dominated by clip onset — not obviously wrong, since codec artefacts live in the attack, but a property of the measurement.

### The unblinded ladder, a hypothesis rather than a result

Browsed after the blinded sitting was saved, on a labelled page: "K=8 major robot vibes. K=16 is similar to K=8. K=24 is pretty good. K=32 less [robot] but still a little. K=32 is the superior one." This relocates the interesting region above K=16 — which the blinded page did not test, having been built on the plan's assumption that K\* ≤ 16. It is consistent with the blinded data (the K=8 vs K=16 gap was not resolved), but it is unblinded, the expected direction is what the labels suggest, and neither automated instrument shows a knee near K=24. It is also not the shape RVQ construction predicts — each successive stage carries a smaller residual. Experiment 0032 settles it blind.

### Caveats

- The bouts are held-out archive recordings, so these are pipeline measurements, not statements about particular field-recorded birds.
- The listening arms are 20 disjoint clips each, on purpose (a repeated bout is recognisable even blind), which caps the resolvable difference at about 20 points; a real 10-point equivalence test needs roughly 200 trials per arm.

### What this changed

- `Codec(keep=K)` is known-exact rather than assumed-exact, and the check runs in a second. WP2's truncation design is safe.
- The escalate branch became the likely one — the branch the timbre plan did not spec. The ladder plateaus by K=24 and never approaches transparency, so the scratch is in codebooks 0–4 or in the encoder/decoder pair, exactly where 0024 Part 1 located the artefact. More bandwidth is not the lever.
- WP2's prior got measurably worse: stages 8–15 at 95% of uniform are a poor target for a model gated at +0.3 bits over the marginal.
- DAC is back on the table and should not have been dropped. Experiment 0017 rejected it on retention at matched token count (0.483 at 1,813 tokens vs EnCodec's 0.973 at 1,800), but DAC 44 kHz/9cb won on spectral distance (1.013 vs 1.151) for 29% more tokens — and the matched-token constraint was load-bearing in a world where extra tokens are now affordable.
- The premise held and the gate did not: blind, the codec at 6 kbps really is audibly worse than raw, but WP1 ends with an ordering and without a K\*.
- The automated instruments predicted the ordering correctly (STFT and AST both ranked raw > K=32 > K=24 > K=16 > K=12 > K=8, and the ear agreed on the three rungs it was shown), so the cheap instruments can be used to choose which rungs are worth a sitting, even though they cannot say what a listener will call good.
