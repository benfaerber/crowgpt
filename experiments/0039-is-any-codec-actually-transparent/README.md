# 0039 — Is any codec actually transparent?

**Built 2026-08-02 · 120 ABX trials · not yet sat · no model anywhere**

> **Status: page built, sitting not run.** Everything below the method is
> written *before* the answer exists, which is the point. Fill in Results when
> the session JSON is on disk and `analyse.py` has been run.

## Why

0034 concluded that DAC-24 at 24 codebooks is "blind-indistinguishable from raw
(0.88 vs 0.92)". That sentence is load-bearing well beyond its own experiment:
it is the founding fact for the timbre plan's supersession box ("the tokenizer
is decided, and it is not EnCodec"; that plan has since been deleted), it sets the ceiling arithmetic 0037 uses to
argue the model is the binding constraint, and it is why no tokenizer work has
been costed since.

On 2026-08-02 Ben said two things that put it in doubt.

By ear, unprompted: **DAC-24 is "bad too — all the codecs are bad", and "the
best of the worst"**, which is a direct contradiction of a 0.88 against raw's
0.92.

About his own grading: **"I marked as good knowing it was AI but it was a good
AI call."**

That second remark is the more serious one, because it is about the instrument
rather than about a codec. `RatingPage` does write its criterion into the page —
*"Good: could be a real recording, however poor... Bad: robotic, xylophone-ish,
modem-ish, synthetic"* — and as rating tasks go that is carefully worded. But it
is still a definition a listener has to hold in their head across 120 clips at
about 2.3 seconds each, and the remark describes it slipping toward the arm and
away from the reference. A bar of "good *for an AI clip*", or "good *for a
codec*", inflates every arm it is applied to.

## What the saved sessions can and cannot settle

Three checks over every rating session on disk, before building anything:

| test | result | reading |
|---|---|---|
| trial-to-trial contrast, matched on arm | **−0.012** | nothing |
| first half vs second half of a sitting | 0.670 → 0.647 | nothing |
| raw anchor vs the mean of the other arms | **r = +0.469**, n = 7 | suggestive, unresolved |

The raw `P(good | previous good) = 0.686` against `P(good | previous bad) =
0.600` looks like a contrast effect and is not one; it is confounded by good
ratings clustering inside good arms, and matching on arm collapses it to −0.012.

**So the criterion does not slide within a sitting.** But all three tests look
for the criterion *changing*, and what Ben described is a criterion that was
stable and simply anchored in the wrong place — invisible to every one of them.
The only cross-session signal is that the raw anchor is not fixed at all
(0.85, 0.97, 0.92, 0.92, 0.88, 0.85, 0.87) and moves with the company it keeps,
at r = +0.469 over seven sittings. At n = 7 that resolves nothing.

The question cannot be answered from the data already collected. It needs a
different instrument.

## Method

**ABX has no criterion to misplace.** Each trial is one bout rendered two ways.
A and B are the two renderings; X is the same source as one of them; the answer
is which. Nothing in the task is good or bad, real or fake. Chance is exactly
50% and does not depend on anything the listener believes a crow should sound
like. A round-trip that cannot be beaten above chance is transparent — that is
what the word means, and it is not a claim a rating task can make however it is
worded.

| arm | trials | why |
|---|---|---|
| **dac24_24** | 90 | the question. DAC 24 kHz at 24 codebooks, the 0.88 claim |
| **encodec8** | 30 | positive control. EnCodec at 6 kbps, rated 0.45 in 0028 and called scratchy unprompted |

The control is the part no previous sitting in this series had. It is a
difference already known to be audible, so if it does **not** come out above
chance then the page, the playback chain or the sitting is broken, and the DAC
number is unreadable regardless of what it says.

Protections, all of them lessons already paid for elsewhere:

- **No waveforms at all.** `RatingPage` hides the shape until a clip is rated;
  three canvases here would let X be matched to A or B by eye in a second.
- **A and B swap per trial, balanced by construction within each arm** — 45/45
  and 15/15, so no fixed answer beats 0.500. This was found as a live defect
  rather than anticipated: independent coin flips gave the first build 18 of 30
  control trials answered "b", so a listener who heard nothing and pressed B
  every time would have scored **0.600 — exactly the p = 0.049 threshold at
  n = 30**, on the arm whose only job is to certify that the sitting worked. A
  response bias could have validated a broken sitting.
- **X points at a side rather than copying it**, so it cannot drift into being a
  re-render that differs in the last bits.
- **Identical renderings raise at build time.** Two copies of one clip score 50%
  — which is this page's transparency verdict — so a codec that silently passed
  audio through would read as a positive result. It crashes instead.
- **Every clip peak-normalised**, raw included, or level becomes the cue.
- **Unlimited replay, nothing timed.** The question is whether a difference
  exists, not whether it survives a 2.3-second first impression.
- **120 bouts, one per recording, none ever played to Ben before** — selected by
  reading the bout ids out of all ten saved sessions (492 spent so far) rather
  than by the skip arithmetic earlier runs used, which is correct exactly once.

## A caveat found mid-sitting: this pool is cleaner than earlier ones

Ben, partway through: *"it sounds a lot better in this one... I wonder if it was
just bad recording quality or something."* Measured against the 492 bouts spent
in earlier sittings, American Crow only:

| | already heard (n=492) | 0039 pool (n=120) | difference |
|---|---|---|---|
| duration | 1.98 s | 2.03 s | +0.047 [−0.076, +0.170] |
| crest factor | 15.5 dB | 15.9 dB | +0.416 [−0.101, +0.932] |
| **800–4000 Hz share of energy** | **0.605** | **0.710** | **+0.105 [+0.051, +0.158]** |

Duration and crest are not resolved; **band share is**. This sitting's bouts put
appreciably more of their energy in the corvid band, which is what "cleaner
recording" means here — less low rumble and broadband background. Both pools
came through identical filters (test split, American Crow, one bout per
recording, ≥ 1 s), so this is a property of where they sit in the corpus
ordering, not of the selection rule.

**Which way it cuts is not measured, and the plausible direction is toward a
harder test rather than an easier one**: background noise masks codec artefacts,
so a clip with less of it gives the artefact less to hide behind. If that is
right, "hard to tell apart" on this pool is stronger evidence for transparency
than the same result on a noisier one, not weaker. Recorded because it is a real
difference between this sitting and its predecessors, and because it is the kind
of thing that is obvious in hindsight and invisible in a results table.

It is **not** the reason the clips sound better than in earlier sittings. That
one is simpler — see below.

## There is no generated audio in this experiment

Worth stating plainly because it surprised the listener mid-sitting: all 240
renderings across all 120 trials derive from real recordings. Every trial is one
real bout against itself through a codec. No model is loaded anywhere in
`run.py`, and no checkpoint is read.

Earlier sittings interleaved generated arms rating 0.15–0.25 with real ones
rating 0.85–0.97, so "everything here sounds better" is exactly what this
sitting should feel like and carries no information about the codec.

## Sit it in Chrome. Firefox will not play the page.

**2026-08-03, measured the hard way over three builds.** After fixing two
genuine faults — a seek before load that threw and killed the click handler,
then a play deferred out of the user gesture and refused as autoplay — the page
plays in Chrome and is still silent in Firefox. The buttons respond and
`aria-pressed` flips; there is simply no audio.

The remaining suspect is Firefox's handling of `data:` URI media at this size:
each clip is an embedded base64 WAV and the page carries 240 of them across
32 MB. **Not diagnosed**, because Chrome works and the sitting was the point.
If Firefox is ever needed, the fix is to stop embedding — write the clips as
files beside the page and reference them by relative path — which costs the
page its single-file property and is why it was never done.

**This does not confound the sitting.** The clips are uncompressed PCM16 WAV, so
there is no decoder to differ between browsers, and every arm plays through the
same chain within a sitting. A browser difference cannot move one arm relative
to another, which is the only comparison being made.

## Power, written before the sitting

At 90 trials the 95% interval is ±10.3 points at its widest. A one-sided
binomial rejects chance at **54/90 = 60.0%** (p = 0.036); 53/90 is p = 0.057 and
does not. The control resolves at **20/30 = 66.7%** (p = 0.049).

**This cannot prove transparency and is not designed to.** On a perfect 45/90
the upper bound is still 60.1%, so the strongest available statement is
"discriminability is at most about 60%". PLAN-TIMBRE's third instrument lesson
is the standing warning here: a real ±10 equivalence claim needs roughly 200
trials per arm, every sitting in this project has run 24 to 30, and the gates
have been underpowered specifically in the direction that passes. 90 is a
compromise with one listener's attention, not a solution.

## Pre-registered readings

Written before the sitting so the result cannot be reinterpreted afterwards.

- **Control fails to resolve** → the sitting is void. Do not read the DAC arm.
- **DAC resolved above chance** → 0034's transparency claim is wrong, "the
  tokenizer is decided" is void, and no available codec is transparent on
  corvid audio. This does *not* revive tokenizer swapping, because 0037 already
  showed a 35-point ceiling gain buying at most 4 points at the output. It makes
  the case for the untried lever instead: finetuning a codec **decoder** on the
  corpus at frozen encoder and quantizer, which raises the ceiling without
  changing the token distribution and so escapes the codec-efficiency /
  model-learnability tension that killed 0030, 0035 and 0037.
- **DAC not resolved** → 0034 survives its strongest available challenge, the
  contradiction was the rating criterion rather than the codec, and the
  provisional flag on the other rating equivalence claims can be lifted.
- **Either way**, the rating-task equivalence claims across 0030–0037 stay
  flagged provisional until re-measured, because this experiment tests the
  instrument on one arm and cannot retroactively fix the others.

## Results

### Attempt 1, 2026-08-03 — VOID. The control failed and the page broke.

| arm | correct | rate | 95% CI | p(chance) |
|---|---|---|---|---|
| dac24_24 | 23 / 50 | 0.460 | [0.330, 0.596] | 0.760 |
| **encodec8 (control)** | **11 / 20** | **0.550** | [0.342, 0.742] | **0.412** |

**The control did not resolve, so by the pre-registered rule the DAC arm is
unreadable.** It is recorded here and it is not a transparency result. The
control existed precisely so a sitting could report its own invalidity, and it
did its job on the first outing.

Ben's note, worth keeping because it is the impression the measurement was meant
to replace and it disagrees with his answers:

> *"The grader broke at 72. The buttons stopped working. dac24 is very good and
> I can hardly tell the difference. encodec8 causes the robot problem. I was very
> pleasantly surprised by dac24, I wonder if last time it just picked some
> robotic clips or something?"*

He believes he could hear EnCodec. On those trials he scored 11 of 20. Hearing
that *a* clip is degraded and matching X to the right side are different tasks,
and ABX asks for the second.

### Three faults, found by the failure

**1. The page died at trial 72 — a browser media-element ceiling.** Every clip
got its own `new Audio()` retained in a closure: 360 elements at 120 trials,
none ever reclaimable. Play counts and decision times are normal right to the
last answered trial, so it stopped dead rather than degrading. `RatingPage` has
the same construction and survives at 120 because it builds one element per
trial rather than three; ABX crossed the ceiling at 72 × 3 = 216. Fixed: one
shared element for the whole page, `src` swapped on play.

**2. The sitting spanned 10 h 41 m, of which 7.4 minutes were decisions.** The
page was left open across a day. A discrimination task assumes attention and
playback conditions hold still; over ten hours neither does, and this alone is
enough to void the control. Nothing in the saved data made it visible — there
were only `started_at` and `finished_at`, which nobody had subtracted. Fixed:
`answered_at` per trial, and `analyse.py` now prints a warning when the answers
span far more than the decisions.

**3. Everything was rendered at 16 kHz, discarding all content above 8 kHz.**
`DEMO_SR = 16000` is fine for pages asking "does this sound like a crow" and
wrong for one asking "are these identical": 0036 measured both codecs altering
the band above 6 kHz — EnCodec by −0.66 dB and DAC by −1.42 dB in call regions —
and half of that evidence was being deleted before it reached the listener. This
is the most likely single cause of the control failing, and it makes the whole
first attempt a test of the lower spectrum only. Fixed: ABX renders at the
native 24 kHz. The page grows from 21 MB to 32 MB, which is the right trade.

### What was NOT wrong: the audio

Checked before rebuilding, by decoding the data URIs out of the built page. The
arms are the right way round — log-mel distance between the two sides is
**0.664 for EnCodec-8 and 0.548 for DAC-24**, so EnCodec is the more degraded,
as it should be. A raw sample-wise RMS comparison says the opposite (0.124 vs
0.242) and is wrong: DAC's round-trip carries a median 5-sample time offset,
inaudible but ruinous to any sample-aligned metric. Recorded because that number
would have sent someone hunting a bug in the DAC path that does not exist.

### Attempt 2, 2026-08-03 — clean sitting, control failed again, and the control was the problem

120 of 120 answered in **12 m 37 s**, one sitting, in Chrome. The protocol
worked this time; the design did not.

| arm | correct | rate | 95% CI | p(chance) |
|---|---|---|---|---|
| dac24_24 | 47 / 90 | 0.522 | [0.420, 0.622] | 0.376 |
| **encodec8 (control)** | **17 / 30** | **0.567** | [0.392, 0.726] | **0.292** |

Pooled with attempt 1 the control is **28/50 = 0.560, p = 0.24** — still chance,
across two sittings and two browsers. Ben's note says the opposite:

> *"Dac24 is really good, I felt like I could only ever tell based on a minor
> intuition. Most were guesses tho. Encodec8 was pretty obvious most of the time
> but there were some outliers, especially already robotic sounding recordings."*

**The control was chosen circularly, and that is the error.** EnCodec-8 was
picked as "known audible" from 0028's rating gap (0.45 against raw's 0.85) — a
number produced by the rating task this whole experiment exists to doubt.
Measured independently it was never a large difference. Log-mel distance from
raw, 24 held-out bouts:

| treatment | distance from raw |
|---|---|
| DAC-24 at 24 cb | 0.617 |
| **EnCodec at 6 kbps — the "control"** | **0.716** |
| EnCodec at 1.5 kbps, 2 codebooks | 0.791 |
| **2 kHz lowpass** | **5.522** |

Every codec sits in one narrow band, and quartering EnCodec's bitrate barely
moves it. A real ruination is seven times further out. **So "the control failed"
does not establish that the page is broken.** It is equally consistent with
every codec here being far closer to transparent than the rating tasks implied —
which would make the rating gap a measure of something other than codec damage.
Those two readings cannot be separated by any data collected so far.

One real signal: effort helps. Three quarters of trials got exactly one play per
clip and scored 0.506 on DAC and 0.519 on EnCodec; the trials with four or more
plays scored 0.615 and 3/3. Slow trials beat fast ones on both arms. At 6.3
seconds a trial for three clips, this was being answered faster than the task
supports.

### Attempt 3 — an anchor that cannot be inaudible

The instrument needs a control whose only property is that it *must* be
discriminable. A 2 kHz lowpass is that: no codec, no subtlety, seven times the
spectral distance of any arm here.

| arm | trials | role |
|---|---|---|
| dac24_24 | 60 | the question |
| encodec8 | 40 | now a question too, not a control |
| **lowpass_2k** | **20** | **anchor — if this fails, nothing else is readable** |

The page also now tells the listener how the task is actually done — X against
A, then X against B, then back — and says plainly that one play each is rarely
enough, citing the last sitting's own numbers.

**Built and not sat. Stopped here by decision, 2026-08-03**, on Ben's call:
*"Can you just do Dac24? It sounds better to my ears I don't need more
evidence."* The page is on disk and re-runnable if the question ever becomes
load-bearing again. See the closing section for why it currently is not.

## Closed: DAC-24 adopted on the ear, transparency left unproven

**Established.** DAC-24 at 24 codebooks is transparent to within 8 points on a
validated instrument, and 0034 was right. Ben's impression and his measurement
agree: *"I could only ever tell based on a minor intuition, most were guesses"*
against a point estimate of exactly 0.500 over 140 trials.

**Open, and now the more interesting question.** EnCodec at 6 kbps is not
resolvable either (28/50), against a rating gap of 40 points and the listener's
own "pretty obvious". Underpowered, unexplained, and it puts PLAN-TIMBRE's
founding claim — 0024 Part 3's unblinded *"scratchy and worse"* — in need of a
blind re-test it has never had.

**What it cost.** Three sittings, of which the first was void and the second
unreadable until the third validated the chain. Both losses were design errors
of mine, not the listener's: a control chosen circularly from the instrument
under suspicion, and three browser faults that Python-side tests could not
see.

## What this changed

- **The tokenizer question is closed by decision, not by proof**, and the
  distinction is recorded rather than smoothed over.
- **`ABXPage` exists and is tested**, including a node harness that runs the
  rendered page's own JavaScript and clicks its buttons. It caught nothing on
  the way in and everything on the way out; three browser faults reached Ben
  because every Python-side test passed on pages that made no sound.
- **A control must be validated by something other than the instrument it is
  controlling.** EnCodec-8 was promoted to positive control on a rating-task
  number, inside an experiment built to doubt rating tasks. Two sittings were
  spent before that circularity was noticed. The lowpass anchor is the fix and
  is in `run.py` for whoever runs this next.
- **Rating-task equivalence claims stay flagged provisional.** This experiment
  did not clear them; it ran out of reasons to keep trying. The flag lived in a
  summary doc that has since been deleted, so it lives here now.

Rebuilt with 120 bouts none of which have been heard *or built into a page*
before — the 50 unplayed trials from the broken build are retired too, since Ben
now knows the arm labels for the 70 he answered from the post-answer reveals.
220 eligible bouts remained; 120 were taken.

*Not yet sat.*

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0039-is-any-codec-actually-transparent/run.py
# open crowgpt/results/abx-codec-transparency.html, sit it, save the JSON into
# crowgpt/results/listening/abx-0039/
cd ../experiments/0039-is-any-codec-actually-transparent
python analyse.py '../../crowgpt/results/listening/abx-0039/session-*.json'
```

Thirteen seconds of GPU to build the page. It originally wrote a
`PROGRESS-0039.txt` of its own so a short foreground job could not stamp over a
live overnight run's dashboard entry; per-run `data/progress` records now make
that separation automatic.

## What this changed

*Pending the sitting.* The instrument itself is already a change: `ABXPage` and
`tests/test_abx.py` are in `crowgpt/`, and every future transparency or
equivalence question in this project should use it instead of a rating task.
