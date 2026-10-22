# 0066 — does unit-count conditioning restore the caw count?

**2026-08-10, predictions before results** · overnight train · **answer:
pending**

## The defect, measured long before the fix

0024: generated bouts carry **1.37 caws where real bouts carry 3.37** (median
1 vs 4, 70% single-caw, Mann-Whitney p = 0.0008) — "the model makes one caw
where the corpus makes four." 0047 showed no sampling setting reaches real
churn, so the fix has to be trained, not tuned. 0064 closed corpus volume as
a lever, which leaves structure: this is the first structure experiment.

## The tweak

A **units-per-bout bucket token** (1 / 2 / 3 / 4–5 / 6+) in the conditioning
prefix, exactly parallel to the duration bucket: counted by the segmenter at
tokenize time (the same 12 dB instrument 0024 measured the defect with, so
signal and gate share numerics), sampled by the model at generation so
counts come from the corpus's own distribution. Implementation threads the
`_prefix`/`prefix_len` seam — the one TODO says produced the same silent bug
twice — and closes it: samplers now count from the sequence they actually
built, the vocabulary owns `sampled_slots`, and the exotic paths
(`complete_fine`, `continue_from`) refuse unit vocabularies loudly instead
of shifting silently. 42 tests across the seam-adjacent suites.

## Predictions

- **If conditioning is the missing signal:** generated unit distribution
  moves decisively toward real's (mean ≥ 2.5, single-caw share well under
  50%), and the same page-worth of clips sounds more like sequences and less
  like blips.
- **The null shape:** the model learns the token (val loss on the slot near
  the empirical bucket entropy) but generation still collapses to singles —
  which would say the defect lives in maintaining coherence ACROSS caws, and
  points the follow-up squarely at context length (the 0064 leftover), not
  conditioning.

## The gate, no ears required

0024's own instrument over ~100 draws from `model-units` vs the same from
`model-v3-scrape` (its unconditioned twin on the same corpus) vs real
held-out bouts: unit-count distributions, single-caw share, mean units.
Ears only if the numbers move.

## Build

`tokens-v4-units` (12-minute tokenize + segmenter counting), then the
standard recipe (d384/L8/H6, 30k steps) to `results/model-units`, chained
under unit `crowgpt-units`. Same corpus as v3, so v3 is the control for
free.

## Result — the defect had already mostly healed, and the token nudges the rest

| arm | mean units | single-caw | MW vs real |
|---|---|---|---|
| real (200 test bouts) | 3.73 | 0.14 | — |
| **model-units** | **3.29** | **0.19** | **p = 0.081 — not distinguishable** |
| model-v3-scrape (twin) | 3.15 | 0.21 | p = 0.009 — still distinguishable |

units vs twin head-to-head: p = 0.53, unresolved at n=100.

The headline is what happened to the baseline: 0024 measured 1.37 mean and
70% single-caw; the unconditioned v3 twin now draws 3.15 and 21% with no
conditioning at all. The defect collapsed somewhere between fair-k8 and
here — the corpus rebuild, and very plausibly the decoder: 0063 measured
the frozen decoder losing bursts (unit Δ −0.19) that the finetuned one
preserves exactly, and every historical count was made through the frozen
one. The scratch's fingerprints, one more time.

**What it changed:** the units token stays as a standing corpus feature —
zero loss cost (val 4.8171 vs 4.8192), and the only arm consistent with
real — but it is a nudge, not the fix; the fix mostly arrived with v3 +
the decoder. No sitting warranted at this effect size. The seam-closure
refactor stands on its own merits regardless.
