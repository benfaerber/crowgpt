# 0097 — Is it the size or the steps?

**2026-11-16** · GPU 3 h 50 min · **answer: mostly the steps. A
CrowGPT2-sized model on the 60k schedule reaches 4.690; the larger model
reached 4.668. About five-sixths of 0096's gain needs no extra size.**

## The question

0096's larger model (43.9M parameters) passed CrowGPT2 on validation once
it trained for 60,000 steps, 4.668 against 4.793. But CrowGPT2 itself only
ever had 30,000 steps, so 0096 could not say whether the larger size or the
longer schedule did it. This is the control: CrowGPT2's size, 0096's
schedule.

## Method

`run.py` runs 0096's `LongSchedule` with one change, the model:
d384/L8/H4, 18.7M parameters. Same trainer, fixed panels, seed, batch
order, batch 8, 60,000 steps, and the same two peak learning rates. Every
snapshot is scored on all 5,033 canonical American Crow validation bouts
by the same code, beside 0096's two final snapshots.

## Results

Full American Crow validation cross entropy, lower is better:

| step | small, lr 0.0003 | small, lr 0.0006 | larger, lr 0.0003 | larger, lr 0.0006 |
|---:|---:|---:|---:|---:|
| 10,000 | 5.158 | 5.111 | 5.149 | 5.146 |
| 20,000 | 4.962 | 4.931 | 4.942 | 4.940 |
| 30,000 | 4.870 | 4.847 | 4.849 | 4.842 |
| 40,000 | 4.804 | 4.772 | 4.780 | 4.759 |
| 50,000 | 4.759 | 4.718 | 4.732 | 4.699 |
| 60,000 | 4.736 | **4.690** | 4.707 | **4.668** |

CrowGPT2 as released (30,000 steps): 4.793.

- **Steps:** the small model gains 0.103 over CrowGPT2 from the longer
  schedule alone (4.793 to 4.690).
- **Size:** at equal schedule and rate the larger model is ahead by 0.022
  (lr 0.0006) and 0.029 (lr 0.0003), and only from step 40,000 on. One seed
  per cell, so that is a small, consistent difference, not a proven one.
- **Rate:** 0.0006 beats 0.0003 at both sizes, by 0.04 to 0.05.
- The small model's curve had not flattened either, and its
  train/validation gap on the fixed panels at the end is 0.15, the same as
  the larger model's.
- The small model trains in 2 hours per 60,000 steps against 3 h 40 min.

## Caveats

- Loss only. Nothing here was listened to; the sitting open on the larger
  model (capacity-0096) is the test of whether any of this is audible.
- One seed per cell. The 0.02 to 0.03 for size is within what a second
  seed could move.
- Validation was used to compare snapshots; these are selection scores.

## What it changed

- **0096's result is a training-length result, not a capacity result.**
  CrowGPT2 was undertrained too. The capacity question stays where 0085
  and 0086 left it: a small edge on loss at most, at nearly twice the
  training cost.
- **Peak learning rate 0.0006 and 60,000 steps replace 0.0003 and 30,000**
  as the recipe to compare against, at either size.
- **If capacity-0096 comes back in the candidate's favour**, the cheaper
  model to release is probably this one
  (`crowgpt/results/control-0097/60k-lr-6e-4/step-60000.pt`), and it would
  need its own sitting against the larger one. If the sitting is a tie,
  loss at this scale is not buying anything audible and longer runs are
  not the lever.
- Not started: 120,000 steps on the small model, which is now the cheaper
  way to ask whether the curve keeps going.
- Weights are local only. Nothing was released.
