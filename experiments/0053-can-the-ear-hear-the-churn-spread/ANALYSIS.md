# 0053 — the analysis plan, written before any result was read

**Written 2026-08-05 at 50 of 120 trials answered.** Nobody involved has seen a
grade, a per-arm rate or any outcome from this pool. That is the only moment a
plan like this is worth anything: chosen after the numbers are visible, every
decision below becomes a way of dressing up whatever happened to show.

Ben asked "is it still too early to get results?" The answer is yes, and the
reason is not the guard — it is power. At 15 trials per pair even a strong effect
is more likely to come back unresolved than resolved, and an unresolved look is
the thing that tempts the next look.

## What the pool can and cannot resolve

Power computed from the design alone, no data. Tie rate assumed 35% (he marked
13% "too close to call" on the old forced-choice rig, and this scale actively
invites "the same", so the real rate is higher). Sign test on non-tied trials,
α = 0.05 two-sided. `p` is how often the better-sounding arm is chosen when he
does choose.

**The widest pair (channel-000 vs channel-081, 0.205 churn apart):**

| p | 15/pair (now) | 23/pair (at 70) | 36/pair (at 120) |
|---|---|---|---|
| 0.70 | 0.15 | 0.26 | 0.41 |
| 0.80 | 0.36 | 0.59 | **0.82** |
| 0.90 | 0.69 | 0.90 | **0.99** |
| 0.99 | 0.97 | 1.00 | 1.00 |

**The trend across all three pairs**, Cochran–Armitage with the churn gap as the
score — does preference strengthen as the gap widens:

| slope | p at 0.205 | p at 0.068 | 15/pair | 23/pair | 36/pair |
|---|---|---|---|---|---|
| 1.0 | 0.70 | 0.57 | 0.10 | 0.13 | 0.16 |
| 1.5 | 0.81 | 0.60 | 0.17 | 0.23 | 0.34 |
| 2.0 | 0.91 | 0.64 | 0.30 | 0.43 | **0.64** |
| 2.5 | 0.99 | 0.67 | 0.48 | 0.69 | **0.89** |

**Read honestly, that says two things and one of them is uncomfortable.** The
pool is well powered for its headline question — "is the widest churn gap audible
at all" reaches 0.82 at p = 0.80 and 0.99 at p = 0.90. It is **not** well powered
for a moderate preference (p = 0.70 tops out at 0.41 even at 120) and only
detects a steep dose-response. So a null on the trend will be weak evidence and
must be reported as such, while a null on the widest pair at 120 will be real.

These are lower bounds. The graded response carries magnitude and a signed-rank
test on −2…+2 uses it, so the actual tests will do somewhat better than the sign
test simulated here. The sign test is pre-specified anyway because it is the one
that cannot be talked into a better answer afterwards.

*(A first attempt at the trend power used Spearman over three tied x-values with a
5-level outcome, which is not a valid test and produced ~0.10 power everywhere.
Recorded because the wrong number was nearly written into this plan as a finding
about the design.)*

## Pre-specified analysis

**Primary.** channel-000 vs channel-081 — the widest churn gap. Sign test on
non-tied trials, two-sided, `H0: P(prefer the arm nearer real churn) = 0.5`. This
is the question "can the ear hear churn at all", and it is the only contrast the
pool can answer well.

**Secondary.** Cochran–Armitage trend across the three pairs with the churn gap
(0.205 / 0.137 / 0.068) as the score. Answers "does the effect scale with the
gap", which is what calibrating churn against the ear would require.

**Tertiary, descriptive only, no thresholds.** Per-pair preference rates; the tie
rate; `engaged_ms` distribution; defect tags by arm; free-text notes.

**Sign convention.** `grade` is signed toward the first clip *heard*, and
presentation order was randomised at build. `ListeningStore.rows()` resolves it to
`preferred_arm`; no analysis may work from `grade` and side directly.

**Catch trials are excluded from every test and are the validity gate.** If catch
accuracy over the pool falls below 80% the sitting is reported as invalid rather
than as a result — his history is 67/70 across every saved sitting, so this should
never fire, and it means something is wrong with the rig if it does.

## One interim look, and one only

Pre-registered here, before any data: **a single interim analysis at 70 trials
answered** — one more dose of 20 from where this was written — with the remainder
of the pool graded only if it does not stop.

Boundaries by an O'Brien–Fleming-style split at information fraction 70/120 =
0.583, rounded conservatively:

| look | n | primary threshold |
|---|---|---|
| interim | 70 | **p < 0.015** |
| final | 120 | **p < 0.045** |

Applied to the **primary** contrast only. The trend test is evaluated once, at
120, and never at the interim.

- **Stop at 70** only if the primary clears p < 0.015. That needs a near-perfect
  result at 23 trials per pair, which is the point: stopping early is for an
  effect nobody could argue with.
- **Otherwise finish all 120**, and the final threshold stays 0.045 rather than
  0.05 because a look was spent.
- **The interim is one look, not a licence.** If it does not stop, no further
  reading happens until 120. Every look must be recorded in the log below at the
  time it is taken.

`reveal_at` stays at 120 in the database, so the API keeps refusing results and
the interim is a deliberate, logged act through the store rather than something
the page can be talked into.

## Amendment, 2026-08-06: stopping at 110, and why it costs almost nothing

Written **before any result was read.** Ben, at 110 of 120: *"we got 10 trials
left. Can we call it now?"* Yes, and the accounting is unusually clean:

- **The interim look at 70 was never taken.** No look has happened at all — the
  API refused throughout and nobody read a grade. Alpha inflation comes from
  *multiple* looks, so a single analysis at 110 is one test and **α = 0.05 stands**.
  The 0.045 reserved for a spent look is unspent, so this is if anything stricter
  than the plan required.
- **The stopping decision is independent of the data.** He is stopping because ten
  more trials are a chore, not because the numbers look good — he cannot see them.
  That is precisely the condition under which stopping early is harmless. Had a
  look been taken and *then* a decision made to stop, this paragraph could not be
  written.
- **The design's balance is exactly intact.** 110 answered is **11 complete blocks
  of 10, no partial block**, giving **33 comparison trials per pair** and 11 catch
  trials. Every block holds all three pairs evenly, so dropping block 11 removes a
  balanced tenth and unbalances nothing.
- **The power cost is trivial.** 33 per pair against the planned 36: the widest
  pair goes from 0.82 to roughly 0.79 power at p = 0.80.

So the pre-specified analysis below runs unchanged, at 33 per pair, at α = 0.05.
The only amendment is n.

## Log of looks

| when | n | what was read | outcome |
|---|---|---|---|
| 2026-08-06 | 110 | the full pre-specified analysis, once | both tests resolved |

## RESULT

**Validity: catch 10/11 = 91%**, clear of the 80% gate. Tie rate came in at 22%
against the 35% assumed in the power calculation, so the pool was better powered
than planned — which partly offsets stopping at 33 per pair instead of 36.

Preference scored toward the arm whose churn sits nearer real audio's 0.868:

| pair | churn apart | n | ties | k/m | rate | 95% CI | p |
|---|---|---|---|---|---|---|---|
| 000 vs 081 → 000 | 0.205 | 33 | 7 | 24/26 | **0.92** | [0.76, 0.98] | **<0.0001** |
| 205 vs 081 → 205 | 0.137 | 33 | 11 | 18/22 | **0.82** | [0.61, 0.93] | **0.0043** |
| 000 vs 205 → 205 | 0.068 | 33 | 4 | 16/29 | 0.55 | [0.38, 0.72] | 0.71 |

**PRIMARY: resolved.** 24 of 26 decided trials on the widest gap, p < 0.0001.

**SECONDARY: resolved.** Cochran–Armitage trend on the churn gap, z = +3.215,
p = 0.0013. Preference strengthens monotonically as the gap widens: 0.92, 0.82,
0.55 for gaps of 0.205, 0.137, 0.068.

### What this establishes, and what it does not

**Established: churn predicts an audible difference.** This is the first time in
the project that an offline instrument has predicted a listening result at power,
and it is a dose-response rather than a single hit. Churn is promoted from triage
to a predictor of *discriminability*.

**Established: 0044's channel null is void, and the channel token matters.** Bucket
choice moves stage-0 churn 0.215 within one checkpoint (0051) and this shows that
range is plainly audible. The arm 0044 pinned was the fallback sink, and the null
it produced said nothing about the hypothesis.

**NOT established: that 0.868 is the target.** The two rival readings — "nearer
real churn wins" and "higher churn wins" — make identical predictions on both
resolved pairs and differ only on `000 vs 205`, which is the pair that tied
(16/29 one way, 13/29 the other). So the data cannot separate them.

What the three arms do say is narrower and more useful: **channel-081 at 0.722, well
below real, loses decisively to both others; channel-000 at 0.927 and channel-205
at 0.859 are indistinguishable from each other.** The economical reading is that
**undershooting real churn is audible and overshooting it is free** — 000 sits
0.059 above real and pays nothing for it, while 081 sits 0.146 below and pays
heavily.

A caution on the trend test, since it is the more quotable number. Three arms give
three pairs, and "gap size" is nearly collinear with "involves 081": the two
resolved pairs both contain 081 and the null pair does not. The two 081 pairs do
differ in the predicted direction (0.92 vs 0.82), which is genuine independent
evidence for a graded effect, but a four-arm design would have separated these
properly and this one cannot.

### Consequences

- **Pin a channel bucket at or above real churn.** Both 000 and 205 qualify; a
  bucket like 081 is audibly worse. 0051's quiet-frame flatness predictor, which
  predicts churn without BirdNET and without audio, becomes a usable pre-gate for
  choosing one.
- **Hear `repeat_penalty = 1.05` next.** 0047 shortlisted it at churn 0.8655
  against the default's 0.8194 — a 0.046 move, between the 0.068 that tied and the
  0.137 that resolved, so it sits right at the edge of what this instrument says is
  audible. That makes it a real test of the threshold rather than another coin flip.
- **Stop targeting 0.868 exactly.** Aim at or above it. That is a change to how
  0047's shortlist should be read: `repeat 1.15` at 0.930 was scored worse than
  `repeat 1.05` at 0.8655 by |gap|, and this result says the overshoot may cost
  nothing.

## What is already known without unblinding

Process facts, none of them an outcome:

- **50 of 120 answered**, five blocks of ten, and the pairs are exactly balanced
  at 15 each. The blocking is doing its job.
- **`engaged_ms` median 10.0 s, range 7.4–21.3 s** over the 30 trials since the
  timer was fixed. That matches Ben's own estimate of "5-10 per" closely enough
  to call the new instrument working, and it is the number that replaces the
  retracted 121 s.
- **The defect tags are being used after all** — `choppy` and `modem` once each.
  The earlier "0 of 20, dead UI" note was premature; they were not used in the
  first two doses and have been since.
- Catch trials so far are part of the 50 and are excluded from everything above.
