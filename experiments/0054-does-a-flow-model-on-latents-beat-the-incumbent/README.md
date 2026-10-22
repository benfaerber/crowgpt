# 0054 — Does a flow model on continuous latents beat the incumbent?

**Status: built and training. No sitting yet, no verdict.** Everything below the
line marked *pending* is a plan, not a result.

## The question

0052 established the precondition: a continuous DAC latent tolerates 20%
per-channel error inaudibly (10/25, below chance) while 80% is unmistakable
(21/25, p = 0.0005). So a model that is merely *close* can sound right, which is
not true of a codebook index. Does a model built on that actually beat
`model-fair-k8` by ear?

This is the first generator in the project that does not predict a symbol.

## Why this and not a seventh variant of the incumbent

0045 closed with *"the modelling route is exhausted — anything further needs a
genuinely new class of idea"*, on six nulls:

| lever | verdict | source |
|---|---|---|
| capacity | 0.164 nats bought 0.000 audible difference | 0023, 0038 |
| training data | flat past 50%; next doubling ≈ +0.017 nats | 0048 |
| more species | 0.42 [0.28, 0.57], neutral | 0049 |
| bigger corpus by ear | 0.51 [0.36, 0.67], dead heat | 0050 |
| sequence length | −0.38 resolved, *worse* | 0038 |
| token layout (delay) | 0.53 [0.39, 0.67] | 0045 |
| fine-stage extender | 0/24, structurally dead on DAC | 0035 |

Every one varied **which** discrete tokens. None varied **whether**. When
capacity, data, length, layout and codec are all neutral, what is left is the
representation and the objective — and that is what this changes.

## What is different, mechanically

**Three measured defects, three reasons to expect movement.** These are
predictions, written before the sitting, and they are falsifiable.

1. **Churn (0046).** Stage-0 churn is 0.801 generated against 0.868 real, and
   only the coarse book that carries structure and pitch is sticky. Cross-entropy
   pays a symbol model to hold the modal code; half the gap is top-k and the
   other half is the model's, reachable by no sampling change. A velocity field
   has no mode to collapse onto and no top-k. **Prediction: churn moves toward
   0.868 without any sampling knob.**
2. **Blips.** *"A single blip"*, *"either pretty good or pretty bad"* — that is
   autoregressive exposure bias, and a committed token cannot be revised.
   Attention here is bidirectional and every one of the 32 steps sees the whole
   bout. **Prediction: the bimodality Ben reported, and the confidence histogram
   confirmed at 28% near-zero / 25% strong, narrows.**
3. **The fine stages (0035).** 9.935 bits of 10 as symbols, unreachable by any
   capacity. As vectors they are a small residual, and a flow model asked for a
   near-white residual emits smooth noise of the right magnitude rather than an
   independent 1024-way draw per frame — which is what a modem sounds like.

**And the length argument, which is the one nobody can argue with.** DAC-24 at 24
codebooks is transparent (0039, ABX 0.522) and costs **5,400 tokens** for a
3-second bout. No autoregressive model here can afford that, which is why the
generator has been stuck at k=8 — the setting Ben calls the robot problem. The
same three seconds is **225 continuous positions**. Full transparent fidelity at
a sequence length shorter than what the incumbent already runs.

## Build

American Crow only, which 0049 licenses: 46 species against 1 came back neutral
(0.42, CI [0.28, 0.57]) on the only species anyone judges, and American Crow is
70.6% of the corpus anyway. Halves the disk and the encode for no measured loss.

| | |
|---|---|
| corpus | 59,654 bouts → 50,108 train / val / test, grouped split, seed 0 |
| latents | 8,332,469 frames × 256 dims, float16, **4.27 GB** |
| representation | DAC-24 kHz, 32-stage continuous cascade, no codebook |
| model | 22.1M parameters, d384 / L8 / H6, adaLN-Zero DiT |
| objective | rectified flow, uniform t, masked velocity MSE |
| sampling | 32 Euler steps; length drawn from the corpus, floored at 1.0 s |

Storage is frame-major and float16 — 0052 measured float16's error at ~1e-3 of a
channel's spread, two hundred times inside the 20% budget, and `check_precision`
asserts it rather than trusting it.

## Pending — what will decide it

**Not validation loss.** 0027 trained two identically-sized models 0.15 nats
apart and the listener rated them 1/12 and 1/12; 0023's 0.164 nats bought exactly
0.000 audible difference. Loss here detects a broken run and nothing else.

Three instruments, in increasing cost and increasing authority:

1. **Churn (0046), free.** Two minutes, no listener. Target 0.868, scored as
   `|stage-0 − 0.868|`. It is **triage only** — 1-for-2 against the ear (0049) —
   and cannot rank a checkpoint or move a default. It can say a run is broken
   before an ear-hour is spent on it. *Complication worth stating now:* churn is
   defined on codec **indices**, so scoring this model means quantizing its
   output to read a number its objective never saw. That is legitimate as triage
   and would be circular as a target.
2. **BirdNET four-arm judgement.** Carries the standing circularity caveat from
   0022 — BirdNET selected the training corpus — so it is a sanity check, never
   the verdict.
3. **A blind forced-choice sitting against `model-fair-k8`.** The verdict.
   Design it for spread rather than for two adjacent arms: 0044 through 0050 each
   asked "which of these two" about arms differing by almost nothing and four of
   five came back unresolved. Use `ABXPage`, which carries no left-button bias
   (0.433 [0.366, 0.500] over 210 trials, against 0.628 for pairwise), or fix
   `PairPage` first.

**Bouts are a scarce resource and the ledger is currently broken.** See the
`TODO.txt` entry: `pool.py`'s `held_out_reals` reads no session files and is
guarded only by a hand-maintained `REAL_OFFSET`, which is why 0053's pool drew
117 of the 120 bouts 0052 had just spent. Resolve that before this experiment
builds a page, or it will spend bouts nobody can account for.

## Where it ended up

Three runs, identical except for one variable each. **The model can refine and
could not originate**, and moving the training signal to the part of the path
where structure is invented more than doubled it.

| run | change | C detected | share of ceiling |
|---|---|---|---|
| `model-flow` | uniform t, per-channel norm | 25.0% | 27% |
| `model-flow-global` | global norm | 22.2% | 24% |
| `model-flow-lognorm` | logit-normal t, mean −0.5 | 52.8% | 58% |
| **`model-flow-t15`** | **logit-normal t, mean −1.5** | **52.8%** | **58%** |
| `model-flow-t20` | logit-normal t, mean −2.0 | 41.7% | 45% |

**Five full 30k runs. One thing moved the number and it was the shape of the
timestep distribution, not its parameters.** Uniform → logit-normal doubled
detection; every mean from −0.5 to −1.5 lands identically; −2.0 is worse;
normalisation did nothing.

Still behind the incumbent's 94.4%, and that gap is the honest headline. The route
is not dead, the remaining failure has an address, and the cheap levers are now
spent.

## The ear settled it, and then located the defect

Ben, 2026-08-06, unprompted, on `flow-clips-best`:

> *"these flows are pretty bad. It doesnt sound like the caw at all. more like
> static"*

**That is the verdict, and it agrees with the judge rather than overturning it.**
52.8% against the incumbent's 94.4% was not BirdNET being unfair to a new model
class; the model really is bad. Worth recording plainly, because the circularity
caveat (0022) was a live reason to distrust the low score and it turned out not
to be the explanation.

And then the word did what Ben's words keep doing. "Static" is a claim about
temporal structure, and it is measurable:

| | real | flow | marginal control |
|---|---|---|---|
| per-stage std ratio | — | **0.90–1.08** | — |
| lag-1 correlation | 0.1346 | **0.0700** | 0.0013 |
| lag-2 | 0.1013 | 0.0654 | 0.0008 |
| lag-8 | 0.0480 | 0.0426 | −0.0009 |
| **lag-16** | **0.0030** | **0.0296** | 0.0007 |

**The marginals are essentially perfect and the arrangement in time is not.**
Every per-stage standard deviation matches real audio to within 10%, so the model
has learned *what values a crow latent takes*. It has not learned *what order they
come in*.

The shape of the error is the specific part. Real audio has sharp short-range
correlation that has died to nothing by lag 16 — about 0.2 seconds, roughly a caw.
The flow model has **half the short-range correlation and ten times the
long-range**. It is simultaneously too rough frame-to-frame and too smooth across
a bout: slow blurry drift where there should be crisp onsets. That is what static
with a wobble is, and it is the profile of a mode-averaged generator.

**This also corrects my own under-reading of churn.** I wrote that churn was
"blind" to the change that doubled detection because it moved +0.0188 → +0.0182.
It was not blind — the churn *overshoot* IS this defect. Less short-range
correlation means more adjacent frames differ, which is exactly a churn above
real. Churn had been reporting the core problem the whole time and I read it as a
minor overshoot because I was watching detection instead.

## The timestep sweep — and a short-run ranking that did not survive

`-0.5` was a first guess. Five arms at 12,000 steps said it was badly
conservative; five full runs said it did not matter. **Both halves are the
result.**

| t_mean | median t | 12k steps | **30k steps** | mean conf @30k |
|---|---|---|---|---|
| +0.0 | 0.500 | 11.1% | — | — |
| −0.5 | 0.378 | 11.1% | **52.8%** | 0.3177 |
| −1.0 | 0.269 | 13.9% | — | — |
| **−1.5** | 0.182 | **27.8%** | **52.8%** | **0.3742** |
| −2.0 | 0.119 | 22.2% | 41.7% | 0.3237 |

At 12k the sweep looked decisive: a clean monotone climb, with −1.5 beating −0.5
by 2.5×. **At 30k they are identical.** Pushing training mass toward the noise end
buys *convergence speed*, not a better endpoint, and past −1.5 it starts costing
real quality (−2.0 loses 11 points).

**This is the pre-registered risk firing.** `sweep.py` says it in its own
docstring — *"a ranking at 12k need not hold at 30k; the full run is what settles
it"* — and it did not hold. Recorded prominently because the short-run sweep is
an attractive way to explore this space cheaply and it mis-ranked the two arms
that mattered. Anyone reaching for a 12k sweep here should treat it as a filter
for *obviously bad* settings and nothing finer.

**What actually mattered was the shape, not the amount.** Uniform → logit-normal
took 25.0% → 52.8%. Everything inside the logit-normal family from −0.5 to −1.5
lands in the same place. Mean confidence favours −1.5 (0.3742 against 0.3177) on
a tied detection rate, which is a modest and unresolved edge; `-1.5` is kept as
the default on that, not on the sweep.

## The diagnostic that found it

Start the ODE from a **real** latent, partially noised, and integrate to t=1. If
the model can finish a bout it was handed most of, the velocity field is fine and
the problem is elsewhere.

| start from | uniform-t model | logit-normal model |
|---|---|---|
| t=0.0 (pure noise) | 8.3% | **41.7%** |
| t=0.3 | 75.0% | **100%** |
| t=0.5 | 100% (conf 0.919) | 100% (conf 0.930) |
| t=0.9 | 100% | — |

**The velocity field was learned correctly all along.** Given 30% of a real signal
the first model already reconstructed to 100% detection at confidence 0.919 —
*above* real audio's 0.749 and above the codec ceiling's 0.765. The entire failure
lived in the earliest, noise-dominated stretch where global structure is decided.

Uniform t spends the same budget on t=0.9, where the answer is nearly given, as on
t=0.05, where everything has to be invented. `logit_normal` draws
t = sigmoid(N(m, s)) and a negative m pulls mass toward the noise end. **The sign
is the opposite of SD3's** — their convention puts t=0 at the data end — and
getting it backwards would train harder on the region that already works. Pinned
by a test.

**The gain landed exactly where the signal moved**, which is what makes this a
mechanism rather than a lucky hyperparameter: t=0.0 went 8.3% → 41.7%, t=0.3 went
75% → 100%, and t=0.5 was already saturated and did not move.

## A measured null, recorded because it was my hypothesis and it was wrong

Per-channel normalisation whitens away the RVQ's natural variance decay — stage 0
has 9.9× the spread of stage 31, stages 0–3 hold 32.7% of total variance and
stages 16–31 hold 8.7% — and that decay is the perceptual importance ordering
(0024's inaudible fine codebooks, 0035's 9.935 bits). So a plain MSE was spending
half its budget on stages known to be inaudible.

The argument is sound. **The prediction failed:** 22.2% against 25.0% at n=36
(±15 points) is indistinguishable. Global normalisation remains the default on the
argument, not on any result, and anyone reaching for it as an explanation later
should know it has already been tried and bought nothing measurable here.

## Churn, on the best model

60 clips per side, DAC reference measured here because 0046's 0.868 is an EnCodec
constant that does not transfer:

| | real | generated | gap |
|---|---|---|---|
| stage 0 | 0.9547 | 0.9729 | **+0.0182** |
| stages 1–7 | 0.996–0.999 | 0.998–0.999 | ≈0 |

Essentially unchanged from the first run (+0.0188), while detection doubled —
which is a useful demonstration of churn's limits. It is **triage, 1-for-2 against
the ear** (0049), and here it was flat across a change that mattered a great deal.
The registered prediction that churn moves toward real without a sampling knob
holds: the flow model **overshoots** by +0.018 where the incumbent **undershoots**
by −0.066 in EnCodec terms. Opposite failure modes — too jittery rather than too
sticky.

## First run — trained, and it is a long way behind

30,000 steps, best val 0.9072. **Not comparable to the incumbent's 4.587**: that
is cross-entropy in nats over a 1024-way softmax, this is mean squared error on a
velocity field. There is no ratio between them that means anything.

### The four-arm judge, plus the incumbent in the same run

36 clips per arm, one BirdNET invocation, one ambience object, all five arms
built in the same process.

| arm | n | detected | mean conf |
|---|---|---|---|
| A · real held-out | 36 | 94.4% | 0.7486 |
| **B · real through the continuous cascade** | 36 | **91.7%** | 0.7650 |
| **C · flow model** | 36 | **25.0%** | 0.1501 |
| D · per-channel marginal control | 36 | **0.0%** | 0.0000 |
| **E · incumbent `model-fair-k8`** | 36 | **94.4%** | 0.8601 |

**E is why this run happened twice.** Comparing C against the README's
38.9%/61.1%/66.7% would have been a cross-sitting comparison against numbers from
a different corpus, a different codec and a different BirdNET invocation — the
mistake 0038 caught costing 33 points. The incumbent generated here, into this
ambience, scored by this judge. It is fair despite being a v1-token model, because
neither C nor E touches held-out audio and 0050 found v1 against v2 a dead heat by
ear (0.51, CI [0.36, 0.67]).

**Three things this says, and only the third is good news for the hypothesis.**

1. **The flow model loses badly.** 25.0% against 94.4%, same run, same judge.
   This is not a small gap and it should not be explained away.
2. **The representation is not the problem.** Arm B is 91.7% against real audio's
   94.4% — the continuous cascade throws away almost nothing, and comfortably
   beats the 80.6% EnCodec ceiling the original README recorded. 0052's finding
   holds. The loss is entirely the model.
3. **What the model does learn is real.** The marginal control scores exactly
   **0.0%**, so 25% is structure the model learned rather than an artefact of the
   ambience, the decoder or the 3-second framing. It is not noise.

### Two things ruled out before blaming the model

**Under-integration of the ODE.** Too few Euler steps leaves residual noise in the
latent, which would look exactly like a bad model. It does not:

| steps | 8 | 32 | 128 | 256 |
|---|---|---|---|---|
| detected (n=24) | 29.2% | 29.2% | 25.0% | 37.5% |

All within noise of each other at ±19 points. 32 steps is enough; the sampler is
not the problem.

**A broken decode path.** Arm B goes through the same decoder and scores 91.7%.

### The two instruments disagree, and that is the honest state

Churn triage, 60 clips per side, **with the DAC reference measured here rather
than borrowed** — 0046's 0.868 is an EnCodec constant and does not transfer:

| | real | generated | gap |
|---|---|---|---|
| stage 0 | 0.9547 | 0.9736 | **+0.0188** |
| stages 1–7 | 0.996–0.999 | 0.997–0.999 | ≈0 |

The flow model **overshoots** where the incumbent **undershoots** (−0.066 in
EnCodec terms, not comparable). Opposite failure modes: the autoregressive model
is too sticky, this one is slightly too jittery. That is the direction the
mechanism predicted — no mode to collapse onto, no top-k — and the registered
prediction "churn moves toward real without a sampling knob" is **confirmed**.

So churn says this model is close to real and BirdNET says it is nowhere near.
They cannot both be right, and neither is the verdict:

- **BirdNET is not neutral between these two arms.** The incumbent scores 94.4%
  with mean confidence **0.8601 — higher than real audio's 0.7486**. That is
  exactly the circularity symptom 0022 named: BirdNET selected the corpus, the
  incumbent was trained on tokens BirdNET chose, and it now agrees with itself.
  A model that beats real audio at being real audio is measuring agreement, not
  quality.
- **But circularity does not explain a 25-versus-94 gap.** It would have to be
  doing nearly all the work. The straightforward reading is that this model is
  genuinely worse right now, and that reading should be preferred until an ear
  says otherwise.
- **Churn is 1-for-2 against the ear** (0049) and is triage, never a ranker.

### What this changed

**The representation question is settled and the model question is now open.**
0052 said a continuous latent is forgiving; this says the forgiveness is real
(B = 91.7%) and that having a good representation buys nothing on its own. The
risk moved exactly where 0052 predicted it would: *"a pass does not predict a good
generator; the model is now the risk, and it is a real one."*

**It does not retire the approach, and it does not yet justify one either.** This
is one untuned run — uniform timestep sampling, no logit-normal weighting, no
guidance, no conditioning of any kind, 22M parameters — against an incumbent with
roughly fifteen experiments of tuning behind it. Reading a first run as a verdict
on a model class would be the same error as reading 0022's LoRA run as a verdict
on pretrained bases, which at least had the excuse of being a fine-tune.

**Nothing here has been heard.** 24 clips are in `crowgpt/results/flow-clips/` for
an informal impression — they cost no held-out bouts, so they are free to listen
to. A real sitting still waits on 0053 closing and the bout ledger being fixed.

**Next, in order of what the evidence supports.** The diagnostic above is the
thing to keep using — it localises the failure along the path, which no other
instrument here can do.

1. ~~**Push further on the noise end.**~~ **Done, and null at convergence.** The
   sweep is above: every mean from −0.5 to −1.5 reaches 52.8%, −2.0 is worse.
   The timestep *shape* was worth 2×; its *parameter* is worth nothing. Do not
   re-run this.
2. **Classifier-free guidance** — the standard lever for weak global structure
   from noise, and the one remaining idea with a mechanism behind it rather than
   a hope. It needs something to condition on, so it wants the channel embedding
   (0040: recording identity outranks species 1.4–3.5× in embedding space) rather
   than the 256-way k-means bucket 0051 was fighting with.
3. **Capacity, last.** 0023 and 0038 ruled it out twice for the incumbent, and
   the reconstruction result argues the network is not the bottleneck here
   either — a model that reaches confidence 0.919 from t=0.5 is not short of
   parameters.

**And the target is now a number, not a vibe.** Any future run should be checked
against the autocorrelation profile before it is judged, let alone heard: lag-1
must roughly double toward 0.135 *and* lag-16 must fall by an order of magnitude
toward 0.003. A run that raises detection without moving those has not fixed the
thing Ben heard. That check costs seconds and needs no listener, and unlike churn
it distinguishes the two halves of the error.

## Honest status

**The representation works and the generator does not.** 0052 proved a continuous
latent tolerates 20% error inaudibly; arm B here confirms it end-to-end at 91.7%
against real audio's 94.4%, comfortably past EnCodec's 80.6% ceiling. Everything
downstream of that is the model, and the model currently produces static.

**Five 30k runs, one real gain.** Uniform → logit-normal timesteps doubled
detection. Normalisation: null. Timestep mean: null at convergence. The cheap
levers are spent, and 52.8% against 94.4% is a loss by both instruments and by
ear.

**What was actually learned, and it is not nothing:**

- the continuous route's precondition holds end-to-end, measured twice
- the failure has a precise, cheap, listener-free signature — the autocorrelation
  profile above — which no instrument in this project could produce before
- the model refines superbly and cannot originate (100% detection, confidence
  0.919 from t=0.5, *above real audio*), so the network is not short of capacity
- three methodological traps are now written down: a 12k sweep that mis-ranked
  the arms that mattered, a churn reading I got wrong, and an EnCodec constant
  that does not transfer to DAC

**Whether to continue is a judgement call and it belongs to Ben, not to me.**
The one remaining idea with a mechanism behind it is classifier-free guidance,
which is the standard fix for exactly a mode-averaged generator and which needs
something to condition on. Everything else on the list is hope.

**Not conditioning, which was on this list and should come off.** The incumbent's
species token is moot here — this is an American-Crow-only model — and its
duration bucket is strictly weaker than handing the flow model an exact frame
count. The conditioning asymmetry I claimed as an excuse for the first run's loss
does not exist.

**Nothing here has been heard.** 24 clips from the best model are in
`crowgpt/results/flow-clips-lognorm/`, and 24 from the first in
`crowgpt/results/flow-clips/`. They cost no held-out bouts, so an informal
impression is free — but after 0038 anything said while knowing which is which is
a hypothesis, not a reading. A real sitting still waits on 0053 closing and the
bout ledger being fixed.
