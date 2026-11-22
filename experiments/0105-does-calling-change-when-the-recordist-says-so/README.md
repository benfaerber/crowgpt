# 0105 — Does the calling change when the recordist says it does?

**2026-11-21** · CPU, seconds · **answer: see Results**

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

_Filled in after `run.py`._
