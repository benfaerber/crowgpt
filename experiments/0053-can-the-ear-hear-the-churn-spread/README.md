# 0053 — can the ear hear the churn spread?

**Status: ANSWERED, 2026-08-06.** Called at 110 of 120 — 11 complete blocks, 33
comparison trials per pair — with one look and α unspent. Catch 10/11 = 91%.

**Yes, the ear hears it, and as a dose-response.** Preference for the arm nearer
real audio's churn was **0.92** at a 0.205 gap (p < 0.0001), **0.82** at 0.137
(p = 0.0043) and **0.55** at 0.068 (not resolved), with a Cochran–Armitage trend
of z = +3.215, p = 0.0013. **The first time an offline instrument in this project
has predicted a listening result at power.**

What it does *not* establish is that 0.868 is the target: "nearer real wins" and
"higher churn wins" differ only on the pair that tied. The economical reading is
that **undershooting real churn is audible and overshooting it is free**. Full
numbers, the collinearity caveat and the consequences are in
[`ANALYSIS.md`](ANALYSIS.md).

*(Numbered 0053 because 0052 was taken by "are continuous latents perceptually
forgiving" while this was being written. There are already two 0017s, two 0018s,
two 0025s and two 0027s; this stepped aside rather than adding a fifth.)*

**Question.** 0051 found the pinned channel bucket moves stage-0 churn across a
0.215 range inside one checkpoint, and that 0044 had pinned the worst bucket of
thirteen. Churn is triage — 0049 put it at 1 for 2 as a ranker and demoted it —
so that earns a sitting and settles nothing alone. Does the ear hear the ordering
churn predicts?

## Built for spread, not for a shipping decision

0044 through 0050 each asked "which of these two" about arms differing by almost
nothing, and four of five came back unresolved. Ben's own summary of the
experience: *"It is hard to grade because most are so close it is hard to pick."*
So the three arms span the whole measured range and every pair is carried
equally, putting three points on the churn-versus-audibility curve rather than
one.

| arm | stage-0 churn | what it is |
|---|---|---|
| channel-000 | 0.927 | the bucket 0044 pinned; the fallback sink, overshoots |
| channel-205 | 0.859 | the on-target bucket, −0.009 from real audio |
| channel-081 | 0.722 | nobody would ship this; the calibration point |
| *real audio* | *0.868* | *0046* |

| pair | churn apart | trials |
|---|---|---|
| 000 vs 081 | 0.205 | 36 |
| 205 vs 081 | 0.137 | 36 |
| 205 vs 000 | 0.068 | 36 |

Plus 12 catch trials, one per block, real against generated.

**Both outcomes are answers.** If the widest pair is inaudible, churn is finished
as a predictor of what a listener hears, and that is decisive for two minutes of
GPU per future arm. If the ordering comes through, churn is calibrated against
his ear for the first time and every later arm can be pre-screened for free.

## The instrument is new, and that is most of the work

| | old rig | this |
|---|---|---|
| response | left / right | signed five-point grade, "the same" in the middle |
| reference | none in the trial | a real held-out bout in every trial |
| session | one sitting of 50–60 | doses of 10, resumable, server-held |
| pacing | grade until you stop | 20 per dose, 30-minute cooldown, enforced server-side |
| results | visible as you go | withheld until all 120 are answered |

**A block is the balance unit; the dose size is just the appetite.** Raised from
10 to 20 after three doses, on Ben's ask. They are deliberately different numbers:
a block holds all three pairs evenly and any whole number of balanced blocks is
itself balanced, so a dose of 20 serves two blocks with the guarantee untouched.
`dose()` takes whole blocks only — an appetite of 15 on blocks of ten still serves
ten, which is honest under-serving rather than a silent half-block that would put
an uneven arm mix in one sitting. A part-graded block is always finished before
the next is started.

**The cooldown was asked for as enforcement, and that was the right instinct.**
After the first dose: *"can you also add a timeout to enforce it. Only let me do
10 every 30 minutes."* The dose design already assumed he would come back later
and nothing made him. It is enforced in the store rather than by a timer in the
page, because a timer survives neither a reload nor the phone, and the same pool
is graded from both. The clock runs from the last stored **answer**, not from when
a dose was served, so reloading costs nothing; and a part-graded block stays
reachable, because locking someone out of the dose they are halfway through is a
bug rather than a rule. `cooldown_minutes` is per pool and nullable, so pools
registered before it existed are unaffected.

**RETRACTED — `decision_ms` is not a decision time.** It was reported here as
"median 121 s per trial against the old rig's 3,971 ms, about 30× longer" and
read as evidence that the graded response was making him listen harder. Ben,
2026-08-05: *"yeah i musta just forgot. Its not real. I prolly spent like 5-10
per."* The field measures wall-clock from the trial rendering to the answer being
submitted, so it counts the tab sitting open, and 121 s is a walk away rather
than a judgement.

Everything that rested on it is withdrawn, in both directions: the first dose is
**not** evidence the new response helps, and dose 2's fall from 113 s to 64 s is
**not** a fatigue or fluency signal. Both numbers are idle time. What survives is
weaker and still worth having: the reference was played on 10 of 10 trials in both
doses and both clips on every trial, where two trials in the old saved corpus were
answered with zero plays at all.

A wrong number in a README becomes a premise, which is why this stays as a
retraction rather than being deleted — and the whole reason the note is here is
that the same field is what produced the engagement gradient cited below, so that
is now caveated too.

**So the timer is being fixed rather than dropped.** Difficulty is exactly what
this pool is about — "most are so close it is hard to pick" — so time-per-trial is
worth measuring properly. `engaged_ms` is added alongside: measured from the
**first play** rather than from render, and paused while the tab is hidden. The 20
trials already graded have no `engaged_ms`, and their `decision_ms` should be
treated as unusable rather than as a baseline.

**The defect tags went unused in the first two doses and are being used since** —
`choppy` and `modem` once each by trial 50, so the "dead UI" reading was premature.
The design fault it pointed at is still real though: tags attach to the trial, not
to a clip, so the interesting label — "the *second* one was scratchy" — cannot be
recorded, and his one free-text note (*"2nd is quite good"*) is exactly that shape.
Worth fixing, no longer urgent.

**The analysis is pre-registered in [`ANALYSIS.md`](ANALYSIS.md)**, written at 50
of 120 with nothing read. It fixes the primary contrast, one interim look at 70
with an O'Brien-Fleming-style boundary, and the uncomfortable half of the power
calculation: this pool resolves "is the widest churn gap audible" well (0.82 power
at p = 0.80) and a moderate preference badly (0.41 at p = 0.70).

**The button was costing about 45% of the power.** Pooled over all 317 non-catch
pairwise trials ever saved, P(chose left) = 0.628, CI [0.575, 0.681] — resolved —
while P(chose first-heard) = 0.495, CI [0.430, 0.561] — null. The side bias holds
at 0.609 and 0.616 *inside* both order conditions, so it is position and not
primacy. Under the simplest model (a fraction λ of trials answered by button,
λ = 2(P(left) − 0.5) = 0.256) a true preference is attenuated to 0.744× and
effective n falls to 55% of actual. A 50-trial sitting resolved like 28; 0044's
20-trial channel arm resolved like 11. So the response here is a judgement with no
side attached to it.

**Blocks, because a dose is a session.** 0038 measured 8.3 points of drift between
evening and morning on identical weights. Twenty doses are twenty sessions, so if
a dose carried one arm drift would become the dominant variable and this would be
*worse* than one sitting. Every block of 10 holds all three pairs at 3 each plus
one catch, both arms of a comparison sit inside one trial, and the store serves
whole blocks only — never part of one. Verified on the registered
pool: 12 blocks of exactly 10, 36 trials per pair, 360 distinct clips, no
generated clip reused, every anchor a different recording.

**Results are withheld, and this is the guard most easily lost.** A page you
return to invites reading the running total and stopping when it looks resolved.
That is optional stopping, and a nominal 5% test checked repeatedly runs at
20–30%. `/api/listening/pools/1/results` answers 409 with the number of trials
remaining until all 120 are in; the progress payload carries counts and no score;
the page shows neither.

**A graded scale also buys a claim this project has never been able to make.** A
real ±10-point equivalence claim needs roughly 200 trials per arm, which is why so
many results are phrased as "not resolved" — no single sitting could afford it.
Accumulating doses can.

## What is here

| | |
|---|---|
| `run.py` | builds the clips and `pool.json` (~9 min GPU, no listener) |
| `pool.json` | 120 trials, blocked and randomised, ready to register |
| `crowgpt/src/crowgpt/pool.py` | `ClipWriter`, `BlockedPool`, `held_out_reals` |
| `fieldserver` `0024_listening_doses` | the three tables and why they are shaped that way |
| `fieldserver/tools/register_pool.py` | puts a `pool.json` in the database |
| `/listen/` | the page, served by fieldserver |

Registration goes through a tool in fieldserver's own venv rather than an HTTP
POST, so a pool can be built by a script that never holds the operator secret.
The route exists too, for anything that already has a session.

## What this changed

Nothing about the model yet — the measurement is pending. What it changed already
is the instrument: **`PairPage`'s left/right response is superseded for any new
sitting**, the withheld-results rule is enforced by the server rather than by
discipline, and a sitting no longer has to be graded in one evening. The
`MIN_GRADEABLE_SECONDS` guard from 0044 is applied at build time to every arm
including the anchors, by `ClipWriter`, which raises rather than dropping — the
one-sided version of that filter is what corrupted six experiments.

## The first build was contaminated, and the fix is the durable part

Built once with an `offset` constant for "how many bouts earlier sittings spent",
set to 0 because 0050's v2 rebuild had invalidated the running count. Recomputing
the draw found **121 of its 132 reference bouts had already been played to Ben**,
most through ABX sittings that reveal the answer every trial — so its catch trials
could have been passed by recognition instead of by ear, inflating the one number
that says the sitting was readable. Nothing was lost: it was caught before a
single trial was graded, and the pool was replaced.

0039's docstring had already named the bug class — *"three hardcoded constants
deep, each one meaning 'however many the last experiment happened to take'. That
is correct exactly once."* — and `pool.py` reintroduced it. So the constant is
deleted rather than raised:

- `spent_bouts(sessions, pools)` unions the two ledgers on disk, and
  `held_out_reals(..., exclude=...)` takes the first `count` unheard bouts.
- **Both ledgers, because the two systems were blind to each other.** Saved
  sittings record a `bout` per trial. A dose pool commits its bouts when it is
  *built* and may sit ungraded for weeks, so `claim_bouts` writes `bouts.json`
  beside its clips at build time. Neither system could see the other before.
- The pool now records `spec.bout_of`, so the next audit reads which bouts it took
  instead of recomputing the draw — the first build recorded no mapping at all,
  which is why the contamination had to be found the hard way.
- `register_pool.py --replace` drops an unheard pool and **refuses one with any
  answered trial**, which is the 0039 rule ("a rebuild must not cost bouts") in
  code rather than in a docstring.

Rebuilt: overlap with previously-heard bouts is **0**, 489 unheard held-out
recordings remain, and 132 are claimed by this pool. Pinned by
`crowgpt/tests/test_pool_ledger.py`.
