# 0052 — Are continuous latents perceptually forgiving in a way code indices are not?

**Status: answered, both halves. Sat 2026-08-05, 120 trials in 17m38s.**

**A continuous latent is forgiving of error that a code index is not.** Twenty
percent per-channel error is inaudible (10/25, below chance); eighty percent is
unmistakable (21/25, p = 0.0005). The wall 0035 hit is a property of the
**encoding**, not of the audio, and the continuous route is open.

## The question

A discrete code is either right or wrong, and a wrong one is a blip. A continuous
latent can be *approximately* right. Is approximately right inaudible?

That single question decides whether the wall 0035 hit is a property of the
**encoding** or of the **audio**. 0035 measured DAC's stages 8–23 at 9.935 bits
of 10 — unpredictable as symbol indices, because RVQ scatters near-neighbour
vectors across arbitrary integers — and an extender handed the true coarse codes
recovered 0.034 bits and scored 0/24 blind. That wall is real and permanent *in
code space*. It says nothing about whether the underlying vectors are
predictable, and until now nobody had asked.

## Why this, after six modelling nulls

0045 closed with *"the modelling route is exhausted — anything further needs a
genuinely new class of idea"*, after nulls on capacity (0023, 0038), data (0048,
0049, 0050), sequence length (0038), token layout (0045), tokenizer config
(0028–0037), filtering (0027) and the fine-stage extender (0035).

Every one of those varied **which** discrete tokens. Not one varied **whether**
discrete tokens. The shape of the null set is the argument: when capacity, data,
length, layout and codec are all neutral, what is left is the representation and
the objective.

There is a mechanism to go with it. Codebook 0 must commit, every 13 ms, to one
of 1024 spectral shapes — there is no "slightly brighter". Real audio's stage-0
code changes on 86.8% of frames (0046) because the signal drifts smoothly across
cell boundaries; a symbol predictor can only say *same* or *different*, and
cross-entropy pays it to hold the modal symbol, so it sits at 0.801. 0027's best
description of the defect is *"structure is learned, timbre is not"*, and timbre
is the continuous part.

## The bench — measured, 40 held-out American Crow bouts

`python run.py --bench`. Mean log-mel distance from raw. **Lower is closer.**

| representation | distance | |
|---|---|---|
| `cont32` | **0.2588** | 256-d continuous cascade, no codebook anywhere |
| `cont32+noise0.05` | 0.2771 | |
| `dac_quantized_32cb` | 0.3004 | |
| `cont32+noise0.10` | 0.3168 | |
| **`dac_quantized_24cb`** | **0.3686** | ← 0039 proved this ABX-transparent |
| `cont32+noise0.20` | 0.4235 | |
| `dac_raw_z_no_quantizer` | 0.5492 | the 1024-d encoder output, decoded |
| `cont32+noise0.40` | 0.6951 | |
| **`encodec_6kbps`** | **0.7387** | ← 0039 could not resolve this by ABX either |
| `cont32+noise0.80` | 1.3306 | |
| `lowpass_2k` | 4.1432 | 0039: ABX 0.85, unmistakable |

Two things fall out, and the second one was not expected.

**The continuous representation beats the codec setting already proven
transparent.** `cont32` at 0.2588 against `dac_quantized_24cb` at 0.3686. A model
10% wrong per channel (0.3168) is *still* closer to raw than that codec. A model
40% wrong (0.6951) lands on EnCodec-6k (0.7387), which 0039 also could not
resolve. Offline, the error budget looks wide.

**Decoding the raw 1024-d encoder output is worse than decoding a rank-256
approximation of it** — 0.5492 against 0.2588, despite carrying strictly more
information. DAC's decoder was trained on quantizer output, so un-quantized `z`
is off-manifold for it. This is useful rather than merely curious: it rules out
"just model `z`", names the 256-d `latents` as the modelling target, and that
target is also 4× smaller.

**One trap worth recording.** `quantizer.from_latents()` reads like the
continuous path — its docstring begins *"given the unquantized latents"* — and it
is not. It calls `decode_latents`, a nearest-neighbour codebook search. Anything
routed through it is quantized, and would have measured the discrete path under a
continuous name. The cascade in `Latent.encode`/`Latent.decode` is written out by
hand for that reason.

### What the bench does not establish

Log-mel distance ranks; it does not locate the audible boundary. This
implementation does not reproduce 0039's absolutes either — it puts EnCodec-6k at
0.739 against 0039's 0.716 (close) and DAC-24 at 0.369 against 0.617 (not) — so
the anchors order arms within this file and nothing more. 0028 already recorded
that cheap instruments rank correctly and cannot find the perceptual threshold.
That is what the sitting is for.

## The sitting — sat 2026-08-05

120 trials in 17m38s, one session, every trial answered.

| arm | correct | rate | 95% CI | p(chance) | reading |
|---|---|---|---|---|---|
| `cont32` | 11 / 25 | 0.440 | [0.267, 0.629] | 0.788 | not resolved — at most 62.9% |
| `cont32+noise0.20` | 10 / 25 | 0.400 | [0.234, 0.593] | 0.885 | not resolved — at most 59.3% |
| `cont32+noise0.40` | 14 / 25 | 0.560 | [0.371, 0.733] | 0.345 | not resolved — at most 73.3% |
| **`cont32+noise0.80`** | **21 / 25** | **0.840** | [0.653, 0.936] | **0.0005** | **AUDIBLE** |
| **`lowpass_2k`** (anchor) | **15 / 20** | **0.750** | [0.531, 0.888] | **0.021** | **AUDIBLE** |

> *"most of the cont sound pretty ok. Low pass really bad."*

**PASS**, on the pre-registered reading. The anchor resolved, so the page and the
playback chain worked. The ceiling arm is clean. Twenty percent per-channel error
is clean — and both those arms sit *below* chance at 0.440 and 0.400, which is
what genuinely no signal looks like.

**The 0.80 arm earned its place.** Without it, four arms at chance would have
been exactly as consistent with "the representation is forgiving" as with "this
page cannot see latent noise", and nothing else could have separated them. It
resolved at p = 0.0005, so the nulls above are real nulls.

**The nulls survive effort, which is the check that matters most.** ABX reveals
the answer each trial, so a difference findable only by hunting is still a
difference — 0039 found 1-play trials at 0.506 and 4+-play trials at 0.615.
Restricted to trials he played four or more times:

| arm | 4+ plays |
|---|---|
| `cont32` | 5 / 8 |
| `cont32+noise0.20` | 5 / 12 — still below chance |
| `cont32+noise0.80` | 7 / 8 |
| `lowpass_2k` | 7 / 7 |

The effort gradient runs the right way for exactly the arms that should have one.
He could not find 20% error by working at it, and he never missed the anchor when
he worked at it.

### The three misclicks

Ben reported trials 11, 13 and 75 as wrong-button presses. All three were scored
incorrect and all three answered "b" against a truth of "a" — a consistent slip.
Two are anchor trials, one is `+0.80`.

**They are kept in the primary analysis**, and the reason is a bias argument
rather than a purity one. ABX reveals the answer each trial, so a misclick that
happened to land correct is one nobody notices or reports; only the wrong ones
get remembered. Excluding self-reported misclicks can therefore only move scores
up, and is not a correction.

It changes nothing here. None of the three fall in a null arm, so every null is
untouched, and dropping them only strengthens what already resolved:
`+0.80` 21/25 → 21/24 (p 0.0005 → 0.0001), anchor 15/20 → 15/18 (p 0.021 →
0.004). The verdict is identical either way.

### Where the budget actually sits

Inaudible at 0.20, unmistakable at 0.80. The 0.40 rung is **unresolved with its
point estimate above chance** (14/25, 0.560, upper bound 73.3%), so the knee is
somewhere between 0.20 and 0.80 and probably nearer 0.40 than to either end. This
sitting was not built to locate it more precisely and does not.

The working budget for a flow model is therefore **20% per-channel error, with
40% a coin-toss and 80% out of the question** — and 20% is a soft target, since
what it really says is "at least 20%, and not resolved above it".

## The design, as pre-registered

`python run.py` → `crowgpt/results/abx-continuous-latent.html`. 120 trials, 120
distinct bouts from 120 distinct recordings, held-out American Crow, every one
never played to Ben before. ABX, so there is no criterion to misplace.

| arm | n | why |
|---|---|---|
| `cont32` | 25 | the ceiling. Audible here and the route is dead before budgets matter |
| `cont32+noise0.20` | 25 | a model 20% wrong per channel — the realistic case |
| `cont32+noise0.40` | 25 | 40% wrong; offline this sits on EnCodec-6k |
| `cont32+noise0.80` | 25 | 80% wrong — **the second control**, see below |
| `lowpass_2k` | 20 | the anchor, carried from 0039 unchanged |

The bench moved these. The first draft tested 10% and 20%; both land closer to
raw than a codec already proven transparent, so both were near-certain passes and
would have spent 60 of a scarce resource confirming a foregone conclusion. The
arms now bracket the knee.

**Why 80% is a control and not just a rung.** If every noise arm reads chance,
there are two explanations that no other arm can separate: the representation is
genuinely forgiving, or the page cannot see latent noise at all. An arm that is
clear of every codec ever measured here distinguishes them. This is 0039's lesson
applied inside the representation — a control must be validated by something
other than the instrument it controls.

Noise is scaled by the **pool-wide** per-channel standard deviation, not each
clip's own. A model's error is a fixed magnitude in latent space; per-clip scaling
would give quiet bouts quiet error and hide the case where error is loudest
relative to signal.

### The instrument is not the one carrying the side bias — measured

The pairwise sittings lose about 45% of their power to a resolved left-button
bias (P(left) = 0.628 over 317 trials), and the standing advice is to fix
`PairPage` before spending another sitting. That does not gate this one, and the
reason is measured rather than assumed. Over all **210 saved ABX trials**:

| | |
|---|---|
| P(answer = A) | **0.433, CI [0.366, 0.500]** — no left bias; if anything a slight lean to B |
| P(truth = A) | 0.505 — the page balances correctly |
| P(reference side = A) | 0.505 |

So ABX does not inherit the defect, and the 25-trial arms are worth their
nominal power rather than half of it. The plausible reason is that ABX asks a
matching question with an explicit referent rather than a preference, so a guess
is a real coin flip instead of a fallback to the nicer-looking button.

Two further alignments, both accidental and worth keeping: **every trial here
contains an untouched real bout as one of its two clips**, which is the one
comparison Ben is reliably good at (67/70 on catch trials), and the page already
asks *"what did the difference sound like, when you could hear one?"* — the
describe-mode prompt that produced "xylophone" (0024) and "crow + modem" (0046).
If an arm comes back audible, that free text is the most valuable thing the
sitting produces, because it says what kind of error a flow model must avoid.

### Pre-registered reading

| outcome | verdict |
|---|---|
| anchor at or near chance | sitting **VOID**, fix the page |
| `cont32` audible | route **dead**, stop |
| every noise arm at chance *including 0.80* | **no power**, not a pass — believe nothing else on the page |
| `cont32` and `+0.20` at chance, `+0.80` audible | the intended **pass**; budget is real and lies between |
| `+0.20` audible | budget is **tight**; the model becomes the risk rather than the representation |

**25 trials resolves ±19.6 points**; a one-sided binomial rejects chance from
17/25. This cannot resolve a 60% tell from 50%, and is not meant to — 0039 records
that equivalence needs ~200 trials. A pass means "not obviously broken, proceed",
never "transparent".

### What this is not

Gaussian noise is a **stand-in** for model error, not model error. A trained
flow model's residual is correlated across time and channel and may be
systematically biased in ways white noise is not. So this measures whether the
*representation* is forgiving, which is a precondition, not whether any
particular model will succeed. A pass does not predict a good generator; a fail
kills the route outright. That asymmetry is the entire reason to run it first and
cheap.

## What this changed

**The modelling route is reopened, and it is the first thing to reopen it since
0045 declared it exhausted.** Six ideas had produced six nulls, all of them
varying *which* discrete tokens. This varied *whether*, and it is not a null.

1. **0035's wall is an encoding artifact, not a fact about the audio.** DAC's fine
   stages carry 9.935 bits of 10 *as symbol indices* and no capacity extracts
   them — that stands. But the same information, carried as continuous vectors,
   tolerates 20% per-channel corruption inaudibly. "Unpredictable as a symbol"
   and "unpredictable as a sound" are different claims, and only the first was
   ever measured.
2. **A flow model over the 256-d latent has a real error budget**: at least 20%
   per channel, in units of the corpus's own per-channel spread. That is a
   quantity a training run can be checked against directly, which no previous
   generator target here has had.
3. **The modelling target is the 256-d `latents`, not the 1024-d `z`** — `z`
   decodes *worse* (0.5492 vs 0.2588) despite carrying strictly more information,
   because DAC's decoder was trained on quantizer output and raw `z` is
   off-manifold. Anyone starting this route reaches for `z` first. It is also 4×
   smaller.
4. **`from_latents` is off-limits** for any continuous measurement: its docstring
   says "given the unquantized latents" and it then runs a nearest-neighbour
   codebook search. Written down before it cost a result.
5. **ABX does not carry PairPage's left-button bias** (0.433 [0.366, 0.500] over
   210 saved trials, against 0.628 pairwise), so the standing "fix PairPage before
   spending another sitting" does not gate ABX sittings.

### What it does not license

**This is not a demonstration that a flow model will work.** Gaussian noise is a
stand-in for model error: a trained model's residual is correlated across time and
channel and may be biased in ways white noise is not. The precondition is met;
the model is now the risk, and it is a real one.

**Nothing here says "transparent".** At n=25 the upper bounds are 62.9% and
59.3%; equivalence needs ~200 trials (0039). The honest statement is "not
resolved, at most about 60%", and the offline log-mel table must not be quoted as
evidence of audibility either way — 0028 and 0039 both record instruments that
ranked correctly and were wrong about the threshold.

**The knee is not located.** 0.40 sits unresolved with its point estimate above
chance. If the budget ever needs to be tight, that rung is where to spend trials.
