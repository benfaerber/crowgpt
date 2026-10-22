# 0028 — What does each additional EnCodec codebook actually buy?

**2026-08-01** · 200 held-out American Crow bouts, one per recording · no model anywhere

WP1 of the timbre plan (since deleted), plus the cheapest available kill gate
for WP2.
Three measurements without ears, and two listening pages left built for the
morning.

## The question

0024 Part 3 established by ear that the 6 kbps round-trip is audibly scratchy
against raw — *"through the codec it makes it scratchy and worse"* — which
reopened the tokenizer and is the founding evidence for the whole timbre plan.
Nobody has since asked the obvious follow-up: **how many codebooks before a
listener stops hearing it?** PLAN-TIMBRE spends most of its length on the branch
where the answer is 16 or fewer.

There was also a contradiction worth resolving first. 0024 Part 1 found that
replacing codebooks 5–7 with noise from the codec's own marginals is
**inaudible**, and concluded the artefact lives in codebooks 0–4. If the last
three of eight rows carry nothing a listener can hear, rows 8–31 — a strictly
smaller residual — should carry less still, and no amount of bandwidth would fix
the scratch.

## Results

### 1. Truncating a high-bandwidth encode is exact

A 6 kbps encode is **bit-identical** to the first 8 rows of a 24 kbps encode,
across every frame tested — 0 mismatched frames. EnCodec's RVQ is
greedy-sequential, so stage *k* cannot depend on a later stage, and that is now
checked rather than assumed.

This is what makes `Codec(keep=K)` safe, and it is what lets the ladder below
compare rungs that are not native bandwidths (12 and 24 codebooks) against ones
that are.

### 2. The ladder is monotone, and it plateaus well short of transparent

| K | kbps | STFT to raw | 95% CI | as % of ceiling | AST FAD | above floor |
|---|---|---|---|---|---|---|
| 8 | 6 | 1.165 | [1.149, 1.182] | 37.7% | 40.13 | 16.54 |
| 12 | 9 | 1.110 | [1.094, 1.127] | 35.9% | 35.27 | 11.68 |
| 16 | 12 | 1.077 | [1.060, 1.095] | 34.9% | 32.89 | 9.31 |
| 24 | 18 | 1.046 | [1.029, 1.064] | 33.9% | 30.79 | 7.20 |
| 32 | 24 | 1.035 | [1.018, 1.054] | 33.5% | 30.27 | 6.68 |

Every rung beats K=8 by a paired-bootstrap interval that excludes zero, so the
improvement is real and not noise. It is also **small, and it stops.** Between
K=24 and K=32 the spectral distance moves 0.011 — a quarter of the K=8→K=12
step — for another 6 kbps.

**Two controls make those numbers readable**, and without them they are not:

- **Ceiling, 3.090** — the STFT distance between a raw bout and a *different*
  raw bout. That is what this metric reads for two unrelated crow recordings.
- **Floor, 23.58** — the AST Fréchet distance between two disjoint halves of the
  raw set. Same distribution on both sides, so this is pure sampling noise.
  Every FAD here is 100-vs-100; matching *n* is what makes the floor a floor,
  because Fréchet distance on 768-dimensional embeddings is badly biased upward
  at these sample sizes and the bias depends on *n*.

Against those: **at maximum bandwidth the round-trip still sits a third of the
way to an unrelated recording**, and still 6.7 FAD above the noise floor. The
curve is flattening toward something that is not zero. EnCodec has no rung above
K=32 to offer.

### 3. The fine stages are nearly white

Per-stage marginal entropy, of a possible 10 bits, pooled over 200 recordings:

| stages | bits |
|---|---|
| 0–7 | 7.57, 8.37, 8.86, 9.19, 9.39, 9.49, 9.55, 9.55 |
| 8–15 | 9.63, 9.58, 9.58, 9.56, 9.50, 9.47, 9.43, 9.38 |
| 16–31 | 9.25 → 8.78, drifting down |

**Stages 8–15 sit at about 9.5 bits of 10 — 95% of uniform.** These are exactly
the stages WP2 proposes training a second model to predict from coarse context,
and its gate is "beat the codec marginal by more than 0.3 bits". Predicting a
near-white residual is a hard ask by construction: RVQ residuals are *designed*
to be decorrelated from what precedes them.

This is precisely the outcome `stages.py` warns about in its own docstring —
*"if a fine stage's cross-entropy already equals its own predictive entropy and
both sit at the codec's marginal, the model is not blurry there — the residual is
genuinely unpredictable given the context… THIS IS THE OUTCOME TO WATCH FOR,
because high fine-stage entropy feels like confirmation while being the
opposite."* It does not kill WP2 on its own — only a trained extender's
`StageProfile` can do that — but the prior is now unfavourable and measured.

**These marginals are not `stages.CODEC_MARGINAL_BITS`.** That table is 0014's,
measured on BirdNET-gated windows, and reads about 1.5 bits lower because gated
windows are denser and more stereotyped. 0017 documented the same disagreement
about codebook capacity (74% vs 92%) and concluded both numbers were correct
about their own sample and only one was a statement about the codec. The shared
constant was deliberately left alone: changing it would silently move every
StageProfile number 0019, 0023 and 0027 ever reported.

## The sitting — rated 2026-08-02, blind

60 trials, waveform hidden, 20 disjoint bouts per arm.
`crowgpt/results/listening/codec-blind-0028/`.

| arm | good | rate | 95% CI |
|---|---|---|---|
| raw | 17/20 | 0.85 | [0.70, 1.00] |
| K=16 | 13/20 | 0.65 | [0.45, 0.85] |
| K=8 | 9/20 | 0.45 | [0.25, 0.65] |

| comparison | difference | 95% CI | |
|---|---|---|---|
| raw − K=8 | **+0.40** | [+0.10, +0.65] | **resolved** |
| raw − K=16 | +0.20 | [−0.05, +0.45] | not resolved |
| K=8 − K=16 | −0.20 | [−0.50, +0.10] | not resolved |

**The founding claim survives blinding.** 0024's "through the codec it makes it
scratchy and worse" was said about a labelled page. Collected blind, against a
raw control, the 6 kbps round-trip costs 40 points of good-rate and the interval
excludes zero. PLAN-TIMBRE's motivating premise is real and is no longer resting
on an unblinded verdict.

**But K\* cannot be named, and that was predictable.** K=16 sits between its two
neighbours and is not resolved against either. The ordering matches the direction
of the spectral and AST ladders above — raw > K=16 > K=8, monotone — but at 20
trials an arm this sitting can only resolve the 40-point gap, not the two
20-point ones. Sizing the follow-up honestly: separating raw from K=16 at 80%
power needs about **70 trials per arm**, and separating K=8 from K=16 about
**95** — three to five more sittings.

So WP1's gate returns *unresolved*, not *transparent*. Ben's note — *"Some were
quite good on k16. It fools me for a low quality crow audio"* — is the same
finding in words: K=16 is good enough to pass sometimes, which is exactly what a
0.65 good-rate against raw's 0.85 looks like from the inside.

**Pace, recorded rather than corrected:** median 1.37 s to decide, 54 of 60 clips
played once, 51 of 60 decisions under two seconds. These ratings are dominated by
clip onset. That is not obviously wrong — codec artefacts live in the attack —
but it is a property of the measurement and the second sitting was run the same
way on purpose.

## The labelled ladder, browsed after the blinded sitting

Ben on `compare-codebook-ladder.html`, 2026-08-02, **unblinded** — he could see
which rung was which, and it was read only after the blinded sitting above was
already saved:

> K=8 major robot vibes. K=16 is similar to K=8. K=24 is pretty good. K=32 less
> [robot] but still a little. K=32 is the superior one.

**This relocates the interesting region, and the blinded sitting above did not
test it.** The plan's branch structure assumed K\* ≤ 16 and so the blinded page
was built as raw / K=8 / K=16 — none of which, on this reading, is where the
threshold lives. K=8 ≈ K=16 is also perfectly consistent with the blinded data,
where their 20-point gap was *not resolved*; hearing them A/B on the same bout
is more sensitive to a within-bout difference than rating disjoint clips, and it
says the gap is small.

**Two reasons to treat it as a hypothesis rather than a result.** It is
unblinded, and the expected direction is the one a listener would guess from the
labels. And neither automated instrument shows a knee anywhere near K=24 — STFT
runs 1.077 → 1.046 across that step and AST FAD 32.9 → 30.8, both smooth. So
either the instruments rank correctly while failing to locate the perceptual
threshold, or the impression is label-driven. **0032 settles it blind.**

It is also worth noticing what would be odd about it if true: in an RVQ each
successive stage carries a smaller residual, so stages 16–23 mattering while
8–15 do not is not the shape the codec's construction predicts. Perceptual
thresholds are nonlinear and a cumulative crossing is possible — but that is a
claim that needs the blinded number.

## What still needs ears

Two pages are built and unrated:

- `crowgpt/results/compare-codebook-ladder.html` — labelled, 12 bouts × (raw + 5
  rungs). The diagnostic, for browsing.
- `crowgpt/results/rate-codec-blind.html` — **the one that matters.** 60 trials,
  blinded, waveform hidden: 20 raw, 20 at K=8, 20 at K=16, on disjoint bouts.

Disjoint rather than paired on purpose — the same call heard three times in one
sitting is recognisable even with the waveform hidden, and a listener who
notices the repeat rates consistency instead of quality. The cost is power: at 20
per arm the standard error on a good-rate is about 11 points, so this **resolves
a 20-point difference and not the 10-point equivalence margin** PLAN-TIMBRE's
gates are written around. Read it as a screen. A real 10-point equivalence test
needs roughly 200 trials per arm — four sittings — and is only worth spending if
this one shows something.

It also collects, blind and for the first time, the founding claim of the whole
plan: 0024's "scratchy" verdict was given on a page whose arms were labelled
`RAW` and `through the codec`.

## What this changed

- **`Codec(keep=K)` is now known-exact, not assumed-exact**, and the check is
  five lines that run in a second. WP2's truncation design is safe.
- **The escalate branch is now the likely one, and it is the branch PLAN-TIMBRE
  does not spec.** The plan gives three lines to "K\*=32 or nothing is
  transparent → stop and escalate" and spends the rest assuming K\*≤16. On these
  numbers the ladder plateaus by K=24 and never approaches transparency, which
  means the scratch is in codebooks 0–4 or in the encoder/decoder pair — exactly
  where 0024 Part 1 said the artefact lives. More bandwidth is not the lever.
- **WP2's prior got worse, measurably.** Stages 8–15 at 95% of uniform are a
  poor target for a model whose gate is +0.3 bits over the marginal.
- **DAC is back on the table and should not have been dropped.** 0017 rejected it
  on retention *at matched token count* (0.483 at 1,813 tokens vs EnCodec's 0.973
  at 1,800), but DAC 44 kHz/9cb won on spectral distance (1.013 vs 1.151) for 29%
  more tokens. The matched-token constraint was load-bearing in that rejection
  and WP2's whole premise is that extra tokens are now affordable. If the ear
  agrees that nothing here is transparent, a DAC rung belongs in the next version
  of this ladder — `dac_codec.py` already exists.
- **The premise held and the gate did not.** Blind, the codec at 6 kbps really
  is audibly worse than raw (−40 points, resolved). K=16 really is better than
  K=8 in point estimate, in the same direction as both automated ladders — and
  neither of those 20-point steps is resolvable at 20 trials an arm. WP1 ends
  with an ordering and without a K\*.
- **The automated instruments predicted the ordering correctly.** STFT and AST
  both ranked raw > K=32 > K=24 > K=16 > K=12 > K=8, and the ear agreed on the
  three rungs it was shown. That is worth knowing: it means the cheap
  instruments can be used to *choose* which rungs are worth a sitting, even
  though they cannot say what a listener will call good.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0028-is-the-codec-transparent-at-k/run.py
```

About 90 seconds on the 4070 Ti. Writes `results.json` here and both pages into
`crowgpt/results/`.
