# 0077 — does matching the calltype recipe close the gap?

**2026-08-17, predictions before results** · build: train ~5.5 h (GPU, booked) +
validation ~40 m · **answer: pending**

## The question

Ben's ear ranks model-calltype above the b32 candidate, and 0076 eliminated
every environmental suspect: no contamination, corpus ear-tested null at 3 s
(0064), window ear-tied unconditioned (0067). What remains includes the one
gap with a paper trail — model-calltype trained ~38k steps with n_head 6 at a
true batch 32; the candidate got 30k steps with n_head 4. This closes that
gap on the candidate's own corpus: n_head 6, 40k steps, effective batch 32
(8×4), everything else identical to model-longctx-ct-b32. If optimisation was
the deficit, this model closes on model-calltype's sound; if Ben still hears
the same wrongness, the deficit is the conditioning×window interaction (or
the units token), and the arbiter becomes a pool sitting.

## Predictions

- Val beats 4.689 (more steps, more heads, same data — it should).
- The ear gap narrows but the honest null is live: 0064/0067 both found the
  recipe robust to axes that "should" matter, and the rare-class recall
  numbers have said label-bound all along. Ben's stake from 0075 carries: if
  val improves again while his ear stays unhappy, val is measuring something
  his ear does not care about, which is itself worth writing down.

## Build

`train.py` via the Trainer API (n_head has no CLI flag; 0027's pattern):
tokens-6s-ct → `results/model-longctx-ct2`, steps 40_000, n_embd 384,
n_layer 8, n_head 6, dropout 0, batch_size 8, accumulate 4. Then
`validate.py`: the 0075 harness re-pointed, paired seeds (41000+), with b32's
results as baseline. Chained by `crowgpt/tools/night_0077.sh` (emails on
failure). If gates hold, ct2 replaces b32 as the chat candidate.

## Gate (decided before results)

- Val < 4.689 expected; report regardless.
- ct2 replaces b32 in the chat picker iff alarm recall ≥ 86% (b32 − 5) and
  alarm serving structure within 15% of b32's on units/gaps.
- The question 0077 exists for — the ear — is answered by Ben in chat
  afterwards, and his verdict goes here whatever it is.

## Result — six heads diverge, and b32 keeps the slot

ct2 never reached 40k: val bottomed early and then **rose** — 4.93 at 5k,
5.31 by 16k — and the early stop fired at 18k with best_val 4.773, worse than
b32's 4.689. Same LR, same everything but heads: at this scale the recipe's
learning rate is tuned to its head count, and n_head 6 destabilised what
n_head 4 trained cleanly. The "more steps" half of the optimisation-gap
theory never got tested — divergence took it off the table first.

The gate held: ct2_becomes_candidate = False (alarm structure regressed,
units 3.28 vs b32's 4.72). Worth the page anyway: ct2's alarm recall hit
96.1% and song 50% — the instruments now disagree **among themselves**
(better recall, worse val, worse structure), which strengthens 0075's
suspicion that none of them is measuring what Ben's ear measures.

## What it changed

- b32 stays the crowgpt3 candidate; nothing was swapped.
- The optimisation-gap explanation for the ear deficit is now mostly dead:
  batch was real (0075), heads are negative, steps are untested-but-unlikely
  to be the voice. What remains standing is the conditioning×window
  interaction and the units token — and the arbiter for those is a pool
  sitting of model-calltype vs b32, not another train.
- A steps-only arm (b32 recipe at 40k) stays available as a cheap follow-up,
  but it is a val chase, and 0075 already showed val moving without the ear
  moving.
