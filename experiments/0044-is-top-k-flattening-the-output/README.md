# 0044 — Is top-k flattening the output?

**2026-08-04 · two sittings, 120 forced-choice trials · answer: top_k=200 WINS,
resolved and replicated — the offline instrument pointed the wrong way, and the
sitting found something bigger about every sitting before it**

> The method below was written before either sitting. The Results section was
> added after, and the outcome mapping it is read against is unchanged from what
> was pre-registered.

## Why

`top_k=200` has been the sampling default for the whole project and it has never
been judged by ear at the temperature the project ships. Two independent code
audits landed on it the same day, and the reason it matters is that **it is not
a uniform truncation.**

Measured per stage on `model-fair-k8`, top-200 of 1024 retains:

| codebook | 0 | 3 | 6 | 7 |
|---|---|---|---|---|
| probability mass kept | **0.981** | 0.889 | 0.805 | **0.782** |

So it is very nearly a no-op on the coarse structure and it discards about a
fifth of the fine residual, renormalising onto whichever 200 codes the model
happens to rank highest. Structurally that is the same operation as cooling the
fine stages — which `stages.py` pre-registered as the thing that would *"make
the sampler re-pick the same arbitrary residual code over and over, which is
periodic, and periodic is what 'robotic' sounds like."*

**Why it was never caught.** 0019 closed per-stage *temperature* on calibration
grounds (every stage calibrates at exactly 1.00) and checked top-k only against
EOS, never against mass — a different question with a different answer. 0015
swept top-k on and off at five temperatures and found turning it off hurt at
every temperature **except 1.00**, which is precisely the setting the project
now ships; and its evidence was BirdNET detection, which 0014 established cannot
hear quality at all.

**What 0043 measured offline.** Turning top-k off puts frame-to-frame timbre
change at 0.0422 against real audio's 0.0413, and within-clip spread at 0.0620
against 0.0572 — neither resolved from real, where `top_k=200` sits resolved
*below* both. That instrument says the timbre moves like real timbre. It cannot
say the clip sounds like a crow, and it reversed sign between two checkpoints of
the same model, so it does not get to decide this alone. Hence a sitting.

## The second question, riding along

`model-channel256` is `model-fair-k8`'s exact recipe — d384 / L8 / H6, effective
batch 18, dropout 0, 30,000 steps — plus one prefix token naming which of 256
background-spectrum buckets the recording came from. Best val 4.5834 against the
incumbent's 4.5874, which is not a comparable quantity (the vocabulary is larger)
and would not be trusted if it were.

It exists because 0042 measured the microphone moving timbre **6.2x** further
than everything inside one recording combined, with no token naming it. 0043's
prompted arm moved between-clip variety the predicted way and did not resolve, so
this is an honest arm rather than a confirmed one. Both sides of the pairing run
at `top_k=200`, so the model is the only difference and the answer survives
whichever way the top-k question goes.

Sampling **pins one bucket**. Drawing it per clip would hand back exactly the
averaging the token exists to remove.

## Method

`PairPage`, from Ben's 0041. Forced choice, one question — which of two clips is
less robotic — with no criterion to misplace and no company to grade against.

| pairing | n | what it asks |
|---|---|---|
| top_k=200 vs top_k=None | 30 | the open question |
| fairk8 vs channel256 | 20 | does the channel token help |
| real vs generated | 10 | catch trials, scored separately |

Protections, each one already paid for elsewhere:

- **Both test pairings are model against model.** Real appears only as catch
  trials and is excluded from every comparison — Ben's objection, and right:
  real rates 0.85–0.97 against generated's 0.22, so pairing them tests only
  whether the listener is awake.
- **Sides are balanced within each pairing, not randomised.** 0041 measured Ben
  choosing the left clip on 65% of decided trials, CI [0.53, 0.75] — a side
  effect as large as the model effect under test.
- **Distinct seed blocks per arm.** Pairing a clip against the same draw with
  one knob changed would compare near-copies and understate every difference.
- **Real bouts are consumed, never reused.** `ALREADY_USED = 370` tracks what
  0033, 0034, 0035, 0037, 0038 and 0041 have already spent, so no catch trial
  carries audio Ben has judged in another context.
- Every clip peak-normalised, because level is a cue (0022).
- **Every clip at least 1.0 s, generated arms included.** The first build of
  this page applied `MIN_SECONDS` to the real catch bouts only, and Ben found
  0.1-second clips in the grader — the shortest was 0.08 s. PLAN-TIMBRE had
  already recorded the rule ("clips under 1 second are ungradeable; filtering
  them took a raw control from 0.87 to 0.96, so filter at build time, not
  after") and it had only ever been applied to real audio, which is the side
  that does not need it. Arms are now over-drawn to hold their stated n rather
  than shrinking silently.
- **Catch trials carry their own clips.** The first build reused the last ten
  `topk200` clips from the top-k pairing, so the listener would have seen them
  twice — a second look, not a second trial.

**The discard rate is itself a result and is recorded rather than swallowed.**
Clips drawn to get the stated n, at 1.0 s minimum:

| arm | kept / drawn | discarded |
|---|---|---|
| topk200 | 40 / 49 | 18% |
| notopk | 30 / 37 | 19% |
| fairk8 | 20 / 25 | 20% |
| **channel256** | 20 / 33 | **39%** |

`model-channel256` stops early **twice as often** as the incumbent, and its
median surviving clip is 1.92 s against 2.37–2.53 s for every other generated
arm. That is a length defect the channel token appears to have made worse, it
was not predicted, and it is worth reading beside whatever the sitting says
about how the arm sounds. Note that top-k makes almost no difference here
(18% against 19%), so early stopping is not what it is doing.

## Results

Two sittings, both 60/60 rated. The second is a **replication on fresh draws**,
not a re-test: the page was rebuilt with new seeds after the 1.0 s filter went
in, so pooling does not double-count a sample.

| | morning (unfiltered) | evening (filtered) | **pooled** |
|---|---|---|---|
| P(notopk preferred) | 0.400 [0.246, 0.577] | **0.300** [0.167, 0.479] | **0.350** [0.242, 0.476] |
| P(channel256 preferred) | 0.550 [0.342, 0.742] | 0.650 [0.433, 0.819] | 0.600 [0.446, 0.737] |
| catch, P(real) | 10/10 | 10/10 | **20/20** |
| side, P(left) | 0.600 | 0.450 | 0.525 |

**`top_k=200` is preferred, 39 of 60, p = 0.027, and it replicates.** Both
sittings point the same way and the filtered one points harder. This is the
opposite of what 0043 predicted offline.

**The controls hold.** Catch accuracy is 20/20 across both sittings — the
listener picks real out every single time, so the sitting is measuring
preference rather than noise. Side bias is 0.525 pooled and within 0.05 of even
inside each pairing, so `PairPage`'s per-pairing balancing did the job that
0041's 65% left bias made necessary. In the evening sitting the longer clip won
0.444 and 0.517 of decided trials by pairing, neither resolved, so length is not
answering the question there.

**`model-channel256` does not resolve.** 24 of 40 pooled, CI [0.446, 0.737],
covering 0.5. Directionally favourable in both sittings and never separated.

### What that costs the instrument

Per the mapping written before the sitting: **0043's measurement stops being
used to rank arms.** It said `top_k=None` put timbre statistics on top of real
audio and the shipped setting sat resolved below them. The ear says the shipped
setting is better, resolved, twice. So frame-to-frame and within-clip timbre
movement are measuring something real that does not correspond to what a
listener calls robotic. Together with 0042's sign reversal between checkpoints
this is now two independent failures of the same instrument, and it should be
read as descriptive of an arm and never as a ranking.

That is worth as much as the other direction would have been. The offline
pre-gate cost about four minutes of GPU and it was **wrong**, which is exactly
what the pre-gate was there to find out cheaply.

### The bigger finding: every sitting in this series has been unfair to the generated arm

Ben, after the first sitting: *"too short clips instantly loose. 0.1 second is
always worse. The vibe of the crow is there with some of them. It is starting to
grasp crow."*

Ben, after the second: *"that def removed many of the modem sounds! it still
sounds 'scratchy' not modem like. Before it had background beeps now it sounds
like a hoarse crow."*

The only difference between those two sittings is the 1.0 s filter. So a share
of what this project has called **"modem"** and **"background beeps"** for
thirty experiments was **sub-second clips in the grading pool**, not the model.

And it is systematic. In `0028`, `0033`, `0034`, `0037`, `0038` and `0041`,
`MIN_SECONDS = 1.0` is applied to `store.index[i]["n_samples"]` — the **real**
bout store — and to nothing else. Generated arms went in unfiltered. Measured
here, **18–20% of generated clips fall under one second** and the shortest was
0.08 s.

That is a **one-sided bias, not noise**: real arms were filtered, generated arms
were not, and by Ben's own account a sub-second clip loses on sight. Every
real-versus-generated number in this series is depressed on the generated side
by up to the share of clips too short to grade — against a generated good-rate
of 0.21–0.25, that is very large in relative terms. It does not touch
generated-vs-generated comparisons, where both arms carried the same handicap,
which is most of 0030 through 0038.

**What remains after the filter is "scratchy" and "hoarse", not "modem".** That
matters, because *scratchy* is the exact word Ben used for the **codec
round-trip** with no model involved (0024 Part 3: *"through the codec it makes
it scratchy and worse"*), confirmed blind at 40 points in 0028. So the defect
left standing may be the tokenizer's, and the model's share of it is smaller
than thirty experiments have assumed.

## What each outcome means

Written now, so the reading is not chosen after the numbers arrive.

- **top_k=None wins.** A sampling constant has been quietly degrading every
  generated clip in this project. Change the default in `sample.py`, re-run the
  0043 measurement as confirmation, and note that the one cell of 0015's sweep
  that did not condemn it was the cell the project lives in.
- **top_k=200 wins.** 0043's instrument is measuring something real that does
  not correspond to what a listener calls robotic, and it should stop being used
  to rank arms. That is a genuine result about the instrument and worth as much
  as the other direction.
- **Neither resolves at n=30.** A 30-pair forced choice resolves roughly a
  20-point difference. A null here means the effect is smaller than that, which
  given how cheap the change is still argues for taking the offline win — but it
  must be recorded as unresolved rather than as parity.
- **channel256 wins.** The channel hypothesis survives its first honest test and
  the retrain was worth it; next question is how many buckets and whether the
  bucket can be *chosen* for quality rather than pinned to the first.
- **channel256 loses or does not resolve.** 0042's mechanism is interesting and
  not actionable at this scale, and the token should be left in the code but off
  by default. Say so plainly — a measured null is the outcome this project
  values and three of the last six experiments have been one.

## What this changed

- **`top_k=200` stays.** The recommendation to change it is retracted. A
  one-line change with a clean offline story lost by ear, twice, and the offline
  story is the thing that was wrong.
- **0043's instrument is retired as a ranker**, on its own pre-registered terms.
- **The channel token stays in the code and off by default.** Unresolved at
  n=40, and it discards 39% of draws for being under a second against the
  incumbent's 18%, so it costs duration for a timbre gain nobody can measure.
- **Every listening page must filter generated arms by length, not just real
  ones.** This is the durable fix and it belongs in one place rather than in
  each experiment's `run.py`, where it has been got wrong six times.
- **Re-read the series' real-vs-generated gaps as upper bounds.** 0028, 0033,
  0034, 0037, 0038 and 0041 all graded filtered real audio against unfiltered
  generated audio.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0044-is-top-k-flattening-the-output/run.py
```

About four minutes on the 4070 Ti. Writes `crowgpt/results/rate-topk-blind.html`
and `pairs.json` here, and reports through its `data/progress` record. Open the page, answer
every trial, and save the session JSON into `crowgpt/results/listening/`.

```bash
python ../experiments/0044-is-top-k-flattening-the-output/analyse.py \
  ../crowgpt/results/listening/topk-0044/session-*.json
```

Pools every session given and writes `results.json` from the pooled counts.
