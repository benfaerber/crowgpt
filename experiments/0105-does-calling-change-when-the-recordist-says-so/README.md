# 0105 — Does the calling change when the recordist says it does?

**2026-11-21** · CPU, seconds · **answer: no, not reliably — caw rate moved the described way at 4 of 6 moments (p = 0.34), a null by the rule set in advance**

## The question

0102 and 0103 compare one recording against another, so every difference they
find is tangled with who recorded it, on what, how far away, and which birds.
A handful of Xeno-canto and Macaulay Library remarks say *when* inside the
recording something changed: "crowd really gets going at about 1:02", "the
crows become somewhat quieter". The same birds, the same microphone and the
same place sit on both sides of that moment. If a simple, label-free measure
of calling intensity moves the way the recordist's words say it should, that
measure is tracking something a person on the spot could hear — which is what
0107 needs before it proposes urgency as the axis worth reporting.

## Pre-registration (written before any audio was measured)

- **Events.** `events.json`, coded from remark text alone. Tier A is an event
  where the recordist's own words describe a change in calling at a stated
  time. There are **six**, from all 62 timestamped remarks in 0102's
  `labels.json`. Tier B events (a stated time, no described change in calling)
  are listed with the reason each was left out and are not tested.
- **Measure.** Caw rate in caws per second: peaks of the 700–4500 Hz RMS
  envelope (100 Hz frame rate, 3-frame smoothing), scaled by the whole
  recording's 10th and 98th percentiles, minimum spacing 120 ms, prominence
  0.18, height 0.25. The scaling is per recording, not per window, so a quiet
  stretch is not stretched up to look busy. No BirdNET, no labels.
- **Windows.** Before = `[t−30, t−3]` s, after = `[t+3, t+30]` s, clipped to
  the recording; an event needs at least 8 s on each side. The 3 s guard is
  for "at about".
- **Primary result.** The number of tier-A events whose change in caw rate
  (after − before) has the sign the recordist's words predict, with a
  one-sided sign test. With six events the smallest possible p is 0.016, and
  five of six gives 0.109, so only six of six can be called significant.
- **Secondary, declared now.** (1) The same with recording 35068 removed: its
  remark describes the birds "getting closer", and a peak count rises with
  loudness. (2) Where the stated moment's change ranks among every other
  moment of the same recording on a 1 s grid — the fraction of other moments
  with a change at least as large in the predicted direction. (3) Duty cycle
  (fraction of envelope frames above 0.25 of the scaled range) over the same
  windows.
- **What would count as a null.** Four or fewer of six in the predicted
  direction.

## Results

| Recording | Moment | Recordist's words (short) | Expected | Caws/s before → after | As described? | Other moments in the recording with a change at least as large |
|---|---:|---|---|---:|---|---:|
| 23031 | 2:20 | owl hops, "some ruckus" | up | 1.30 → 2.19 | yes | 8% |
| 25516 | 1:02 | "crowd really gets going" | up | 2.59 → 2.04 | **no** | 48% |
| 26329 | 1:18 | "become somewhat quieter" | down | 2.85 → 1.52 | yes | 10% |
| 397 | 0:50 | "gets louder" | up | 1.37 → 0.82 | **no** | 75% |
| 35068 | 1:00 | "they were battling" (also "getting closer") | up | 1.70 → 2.63 | yes | 22% |
| 25139 | 0:44 | "calls continuously while flying" | up | 0.37 → 1.23 | yes | 4% |

- **Primary (caw rate): 4 of 6 in the described direction, one-sided sign test
  p = 0.34.** By the rule written beforehand this is a null.
- **Without 35068** (the "getting closer" recording): 3 of 5, p = 0.50.
- **Duty cycle** (secondary): 5 of 6, p = 0.11. Not significant either, and
  six events cannot make it so short of six of six.
- **Rank within the recording** (secondary): at the four moments that agreed,
  between 4% and 22% of the recording's other moments showed a change as
  large. None is rare enough to stand on its own.

Read after the fact, and therefore not evidence: the two misses are the two
remarks about a *crowd* ("crowd really gets going", "gets louder"). A peak
counter cannot count more caws once several birds overlap — the envelope stops
dipping between calls — so a mob that gets busier can read as slower. Duty
cycle does not have that ceiling and went the described way at one of the two.
That is a reason to prefer a duty-cycle or energy-based measure over a caw
count for mobs, and a hypothesis for a larger sample, not a finding of this
one.

## Limits

- Six events is every tier-A moment in 62 timestamped remarks. The archive has
  no more to give this design.
- "At about" timestamps are loose; the 3 s guard and 27 s windows were fixed
  in advance and not tuned.
- The measure rises with loudness, so a bird flying toward the microphone
  looks like a bird calling more.

## What it changed

- **Caw rate from an envelope peak count is not validated as an intensity
  measure, and should not be used as one for mobs.** 0102's "owls are called
  at 2.67 caws/s against 2.00 for hawks" rests on the same kind of counter;
  that number describes the envelope, and this experiment could not show it
  tracks what a person on the spot hears as intensity.
- **0107 does not get to lean on this as its validation.** It has to carry
  its own check, and it should define urgency on duty cycle or band energy
  rather than on a caw count alone.
- The within-recording design is the right one — same birds, same microphone —
  and is starved of events, not wrong. A camera on the roof station
  (`phases/roof-station.md`) produces timestamped events by the dozen; the
  code here runs unchanged on them.
