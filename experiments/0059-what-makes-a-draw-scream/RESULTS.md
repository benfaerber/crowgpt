# 0059 — what makes a draw scream?

## Overview

Experiment 0057 ended with Ben's decomposition — "codec makes it scratchy, generated makes it scream" — and a single tagged exemplar: the generated clip from seed 4, which he called "a clear example" of a scream, against five same-model draws that were not. This experiment asked the instruments what "scream" is, measuring eight acoustic and token statistics across all six clips. One statistic separates the tagged clip cleanly: the screaming draw spends only 0.142 of its time in caw-like bursts in the corvid band (its "duty cycle"), half the nearest neighbour's and outside the 0.292–0.603 range of everything else. With n = 6 and one positive, this is a nominated signature, not yet a finding — a planned 30-draw blind tagging pass will either confirm it or kill it.

## In depth

### The question

Experiment 0046 turned "modem" from a description into a stuck coarse codebook by measuring what the described defect looks like in the instruments; this does the same for "scream". The six clips are model-fair-k8 seeds 2–7 from experiment 0057's page, and all six regenerate bit-exactly (durations match 0057's manifest), so these are the clips Ben heard.

### Result

| seed | s | churn0 | longest run (s) | units | units/s | duty | crest dB | HF share | tag |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 2.39 | 0.713 | 0.107 | 5 | 2.09 | 0.507 | 14.1 | 0.015 | C+ "coarse" |
| 3 | 1.12 | 0.964 | 0.027 | 3 | 2.68 | 0.292 | 15.9 | 0.105 | D+ |
| **4** | **2.76** | **0.859** | 0.080 | 4 | **1.45** | **0.142** | **16.1** | 0.064 | **SCREAM** |
| 5 | 1.51 | 0.911 | 0.040 | 2 | 1.33 | 0.531 | 14.6 | 0.041 | D+ |
| 6 | 2.28 | 0.853 | 0.040 | 6 | 2.63 | 0.470 | 14.7 | 0.013 | C-/C+ |
| 7 | 1.49 | 0.721 | 0.067 | 3 | 2.01 | 0.603 | 14.2 | 0.008 | D+ |

References: real audio churn0 = 0.868 (experiment 0046); real bouts mean 3.37 units (experiment 0024). Duty is the fraction of envelope frames inside an experiment-0013-detector burst, corvid band, 12 dB over the adaptive floor.

**Duty cycle separates the scream cleanly: 0.142 against a 0.292–0.603 range for everything else** — half the nearest neighbour, no overlap. The tagged clip is also the longest, the highest-crest, and the sparsest in units per second, which composes into a physical picture: seed 4 spends the least of its time being a caw-burst in the corvid band, while whatever fills the rest of its 2.76 seconds is loud enough to raise the adaptive floor. Sustained non-caw energy wearing a caw's length — a fair acoustic sketch of a scream.

**What does not flag it matters as much.** Seed 4's stage-0 churn is 0.859 — nearly exactly real audio's 0.868. The statistic that caught the "modem" defect is blind to the scream, and experiment 0053's "undershoot is audible, overshoot free" instrument would wave seed 4 straight through. The scream is a different defect from the modem at the token level, not just by ear.

Seed 3 is a second kind of bad for the record — churn 0.964 overshoot, HF share 0.105, over in 1.12 s — and Ben graded it D+ without calling it a scream. Two D+ clips, two different failure shapes.

### Honest limits

n = 6 with one positive. Duty cycle is nominated, not established — one clip's separation on one of eight statistics, after looking at the table, is exactly the shape of thing that dies on fresh data.

### What would settle it

Tag-then-correlate, the experiment 0046 route: generate about 30 fresh draws, have Ben tag scream / no-scream blind (a page with tags, not a graded sitting), and duty cycle either predicts the tags or dies. If it holds, the generator gets a cheap scream filter for free — the experiment 0055 shortlist already computes churn at pick time, and duty would sit beside it. If it dies, the scream has no signature in the coarse statistics measured here, which points at the fine stages or the decode — a real result either way.

### What the answer changed

Nothing yet — this nominates, the 30-draw tag decides. Written down so the candidate and its exact threshold context survive until then.
