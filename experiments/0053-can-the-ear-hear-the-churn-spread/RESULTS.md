# Can the ear hear the churn spread?

## Overview

The project's cheap offline instrument for grading generated crow calls is "churn" — how often the generator changes its coarse codec code frame to frame, compared with real audio. Experiment 0051 showed that the choice of pinned channel bucket moves churn across a 0.215 range inside one model checkpoint, but churn had a poor record as a predictor of what a listener actually hears. This experiment built a blind, dose-based listening pool spanning three buckets across that whole range and asked whether Ben's ear hears the ordering churn predicts. It does, and as a dose-response: the widest churn gap was preferred at 0.92 (p < 0.0001), the middle gap at 0.82 (p = 0.0043), and the narrowest was not resolved, with a significant trend across the three. This is the first time an offline instrument in this project has predicted a listening result at power. What it does not establish is that real audio's churn value is the exact target — the data reads as "undershooting real churn is audible, overshooting it is free".

## In depth

**Question.** Experiment 0051 found the pinned channel bucket moves stage-0 churn across a 0.215 range inside one checkpoint, and that experiment 0044 had pinned the worst bucket of thirteen. Churn was triage only — experiment 0049 put it at 1 for 2 as a ranker and demoted it — so the finding earned a sitting but settled nothing alone. Does the ear hear the ordering churn predicts?

**Design: built for spread, not for a shipping decision.** Experiments 0044 through 0050 each asked "which of these two" about arms differing by almost nothing, and four of five came back unresolved; Ben's own summary was *"It is hard to grade because most are so close it is hard to pick."* So the three arms span the whole measured range and every pair is carried equally, putting three points on the churn-versus-audibility curve:

| arm | stage-0 churn | what it is |
|---|---|---|
| channel-000 | 0.927 | the bucket 0044 pinned; the fallback sink, overshoots |
| channel-205 | 0.859 | the on-target bucket, −0.009 from real audio |
| channel-081 | 0.722 | nobody would ship this; the calibration point |
| *real audio* | *0.868* | *from experiment 0046* |

The pool held 120 trials — 36 per pair plus 12 catch trials (real against generated), in 12 balanced blocks of 10. Both outcomes would have been answers: if the widest pair were inaudible, churn would be finished as a predictor; if the ordering came through, churn would be calibrated against the ear for the first time.

**The instrument is new, and that was most of the work.** Compared with the old forced-choice rig: a signed five-point grade with "the same" in the middle instead of left/right; a real held-out bout as a reference in every trial; resumable server-held doses instead of one 50–60 trial sitting; a server-enforced 30-minute cooldown between doses (asked for by Ben); and results withheld by the server until the pool completes — the API answers 409 until then, which is the guard against optional stopping. Blocks of 10 hold all three pairs at 3 each plus one catch, because experiment 0038 measured 8.3 points of drift between sessions and a dose is a session. The old rig's left/right response was measured as costing about 45% of statistical power: P(chose left) = 0.628, CI [0.575, 0.681], over all 317 saved non-catch pairwise trials, while first-heard was null at 0.495 — position, not primacy.

Two corrections from along the way are worth keeping. A claim that the new response format made Ben listen 30× longer was retracted: `decision_ms` counts wall-clock from render to answer, so it measures the tab sitting open, not judgement; the replacement `engaged_ms` (measured from first play, paused while the tab is hidden) gave a median of 10.0 s, matching Ben's own "5-10 per". And the first pool build was contaminated — 121 of its 132 reference bouts had already been played to Ben, which could have inflated catch accuracy by recognition. It was caught before a single trial was graded and rebuilt with a bout ledger (`spent_bouts` over both saved sittings and built pools) replacing the hardcoded offset constant that caused it; the rebuilt pool overlapped previously-heard bouts by 0.

**The analysis was pre-registered** in `ANALYSIS.md` at 50 of 120 trials answered, with nothing read: a sign test on the widest pair as primary, a Cochran–Armitage trend across the three churn gaps as secondary, one optional interim look at 70 (never taken), and catch accuracy below 80% voiding the sitting. Ben stopped at 110 of 120 ("we got 10 trials left. Can we call it now?"); the amendment was written before any result was read, and the accounting is clean — no look had ever happened, so a single analysis at 110 is one test and α = 0.05 stands; 110 is 11 complete blocks with no partial block, so the balance is exactly intact at 33 comparison trials per pair; the power cost is roughly 0.82 to 0.79 on the widest pair.

**Result.** Validity: catch 10/11 = 91%, clear of the 80% gate. Tie rate 22% against the 35% assumed in the power calculation. Preference scored toward the arm whose churn sits nearer real audio's 0.868:

| pair | churn apart | n | ties | k/m | rate | 95% CI | p |
|---|---|---|---|---|---|---|---|
| 000 vs 081 → 000 | 0.205 | 33 | 7 | 24/26 | **0.92** | [0.76, 0.98] | **<0.0001** |
| 205 vs 081 → 205 | 0.137 | 33 | 11 | 18/22 | **0.82** | [0.61, 0.93] | **0.0043** |
| 000 vs 205 → 205 | 0.068 | 33 | 4 | 16/29 | 0.55 | [0.38, 0.72] | 0.71 |

The primary contrast resolved at 24 of 26 decided trials, p < 0.0001. The secondary trend resolved too: Cochran–Armitage on the churn gap, z = +3.215, p = 0.0013, with preference strengthening monotonically as the gap widens.

**What this establishes, and what it does not.** Established: churn predicts an audible difference — the first time an offline instrument here has predicted a listening result at power, and as a dose-response rather than a single hit, so churn is promoted from triage to a predictor of discriminability. Also established: experiment 0044's channel null is void, and the channel token matters, since the 0.215 churn range bucket choice spans is plainly audible and the arm 0044 pinned was the fallback sink.

Not established: that 0.868 is the target. The rival readings "nearer real churn wins" and "higher churn wins" make identical predictions on both resolved pairs and differ only on the pair that tied. What the three arms do say is narrower and more useful: channel-081 at 0.722, well below real, loses decisively to both others, while channel-000 at 0.927 and channel-205 at 0.859 are indistinguishable from each other — so the economical reading is that undershooting real churn is audible and overshooting it is free. A caution on the trend test, since it is the more quotable number: with three arms, "gap size" is nearly collinear with "involves 081" — the two resolved pairs both contain 081. The two 081 pairs do differ in the predicted direction (0.92 versus 0.82), which is genuine independent evidence for a graded effect, but a four-arm design would have separated these properly and this one cannot.

**What this changed:**

- **Pin a channel bucket at or above real churn.** Both channel-000 and channel-205 qualify; a bucket like channel-081 is audibly worse. Experiment 0051's quiet-frame flatness predictor, which predicts churn without BirdNET and without audio, becomes a usable pre-gate for choosing one.
- **Hear `repeat_penalty = 1.05` next.** Experiment 0047 shortlisted it at churn 0.8655 against the default's 0.8194 — a 0.046 move, between the 0.068 gap that tied and the 0.137 that resolved, so it sits right at the edge of what this instrument says is audible and is a real test of the threshold rather than another coin flip.
- **Stop targeting 0.868 exactly; aim at or above it.** This changes how 0047's shortlist should be read: `repeat 1.15` at 0.930 was scored worse than `repeat 1.05` by absolute gap, and this result says the overshoot may cost nothing.
- **The instrument itself:** `PairPage`'s left/right response is superseded for any new sitting, the withheld-results rule is enforced by the server rather than by discipline, a sitting no longer has to be graded in one evening, and the bout ledger prevents the contamination class that nearly cost this pool.

The full pre-registration, power tables, the interim-look policy, and the log of looks are in `ANALYSIS.md`; the computed numbers are in `result.json`. (The folder is numbered 0053 because 0052 was taken while this was being written.)
