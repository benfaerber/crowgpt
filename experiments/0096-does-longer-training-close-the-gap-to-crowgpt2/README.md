# 0096 — Does longer training close the gap to CrowGPT2?

**2026-11-15 to 16** · GPU 7 h 15 min · **answer: yes, on validation loss.
The larger model on a 60k schedule scores 4.668 against CrowGPT2's 4.793,
and it was still improving when the schedule ended. Nobody has heard it.**

## The question

0086 trained the larger model (d512/L12/H4, 43.9M parameters) for 30,000
steps at batch 8 and it lost to the smaller CrowGPT2 on full validation,
4.869 against 4.793. But 30,000 steps at batch 8 is 240,000 sequences, and
the training set has 268,184: the larger model had not seen its data once.
So 0086 may have measured an unfinished model, not a worse one.

## Method

0086's own trainer, panels and scorer (`ControlledTrainer`, imported, not
copied), with one change: 60,000 steps, so 1.8 passes over the data. Two
arms, peak learning rate 0.0003 (0086's winner) and 0.0006. Same seed-0
initialisation, same batch order, batch 8, zero dropout, 200-step warmup,
cosine to a floor of 0.1, `tokens-6s`. Snapshots every 10,000 steps.

Every snapshot, CrowGPT2 and 0086's selected model were then scored on all
5,033 canonical American Crow validation bouts by the same code. The two
references reproduce 0086's published numbers exactly (4.7927, 4.8690).

No clips were generated and no listening pool was built.

## Results

Full American Crow validation cross entropy, lower is better:

| step | lr 0.0003 | lr 0.0006 |
|---:|---:|---:|
| 10,000 | 5.149 | 5.146 |
| 20,000 | 4.942 | 4.940 |
| 30,000 | 4.849 | 4.842 |
| 40,000 | 4.780 | 4.759 |
| 50,000 | 4.732 | 4.699 |
| 60,000 | 4.707 | **4.668** |

| reference | |
|---|---:|
| CrowGPT2 (30k steps) | 4.793 |
| 0086 selected (30k steps, lr 0.0003) | 4.869 |

- Both arms pass CrowGPT2 by step 40,000. The best is 0.125 below it, which
  is larger than the 0.076 by which 0086 lost.
- The higher learning rate wins from step 30,000 on. 0086 found 0.0003 best
  of 0.0001 to 0.0003 and never tried above it.
- Neither curve has flattened. In the last 5,000 steps, with the learning
  rate already near its floor, the 256-bout panel still fell by about 0.01.
- The gap between training and validation loss on the fixed panels grows
  slowly, 0.12 at step 10,000 to 0.16 at 60,000, while validation keeps
  falling. The model is not yet memorising.
- No arm failed or produced a non-finite loss.

## Caveats

- **Loss is not the ear.** 0086 required "a pass by ear, not lower cross
  entropy alone" for a release, and this project has several cases where
  lower loss was not heard. This result makes a candidate worth listening
  to and nothing more.
- **CrowGPT2 was not retrained.** It had 30,000 steps of its own recipe. A
  CrowGPT2-sized model on 60,000 steps might improve as well, so this does
  not show the larger size is what helped; it shows 0086's candidate was
  undertrained.
- One seed per arm. The 0.04 between the two learning rates is one draw.
- Validation was used to compare snapshots, so 4.668 is a selection score,
  not a test score.

## What it changed

- **0086's "the larger model is worse" no longer stands.** It was an
  unfinished model. The capacity question is open again, in the larger
  model's favour on loss.
- **30,000 steps at batch 8 is too short for this corpus**, for any model
  compared from here on. 60,000 is the new floor, and the curves say more
  would still help.
- **The candidate to hear next** is
  `crowgpt/results/longer-0096/60k-lr-6e-4/step-60000.pt`. No pool was
  built for it, because capacity-0086 (2 of 48 answered) asks the same
  question about a model this one supersedes. Ben's call: replace that
  sitting with one for this candidate, or finish it first.
- Two follow-ups, neither started: the same recipe at 120,000 steps, and
  CrowGPT2's size on 60,000 steps as the missing control.
- The weights are local only (`*.pt` is gitignored). Nothing was released.
