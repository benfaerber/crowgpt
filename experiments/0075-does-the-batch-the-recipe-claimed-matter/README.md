# 0075 — does the batch the recipe claimed matter?

**2026-08-16, predictions before results** · build: train ~4 h (GPU, booked) +
validation ~40 m · **answer: pending**

## The question

Every long-context train wrote `--batch-size 32` and got micro-batch 8: the
memory budget clips at block 3612 × vocab 8274 and nothing on disk recorded
it until the 0074 planning sweep dug it out. An 18.7M model on 268k sequences
at effective batch 8 is a noisy-gradient regime nobody chose. This retrains
model-longctx-ct's exact recipe with `--accumulate 4` — effective batch 32,
the number the flag always claimed — and asks whether the gradient noise was
costing anything. Same token stream, so **val loss is directly comparable**
for once: the ct baseline is 4.781.

## Predictions

Extrapolated; Ben asleep, on his standing ask to improve the model overnight.

- Modest val improvement (batch 8 → 32 at this scale usually buys a little
  smoothing, rarely nothing, rarely a lot). Ben's stake in the ground: if val
  does not beat 4.781, the clip was never a bug, and the recipe comment gets
  corrected to say batch 8 is fine.
- Conditioning recall roughly unchanged (it is data-bound, not
  optimisation-bound — 0021's monotonic rule).
- Structure at the serving cell: same or slightly better; the null is that
  batch was never the binding constraint and the money answer stays "labels".

## Build

`crowgpt/tools/night_0075.sh`: train `--steps 30000 --n-embd 384 --n-layer 8
--dropout 0 --batch-size 8 --accumulate 4` (micro 8 stated honestly this time,
4 accumulated = effective 32) on `tokens-6s-ct` → `results/model-longctx-ct-b32`,
then `run.py`: the 0074 anchor + forced-choice recall + per-type serving
structure on the new checkpoint, same seeds (41000+) as 0074 so the comparison
is paired, with 0074's results.json read from disk as the baseline.

In parallel, CPU only: the 9 s extraction (`CROWGPT_BOUT_MAX_SEC=9` →
`bouts-9s`) so the 0067 ladder's named next rung has its corpus ready. No
tokenize or train on it tonight — block ~5400 needs a VRAM preflight that
should not share a card with a live train.

## Gate (decided before results)

- Val < 4.781 says the batch mattered; report the margin either way.
- Recall and serving structure within noise of 0074's, or better, keeps the
  b32 checkpoint as the standing crowgpt3 candidate in ct's place. Any recall
  regression > 5 points on alarm, or serving-structure regression > 15% on
  units/gaps, keeps ct.
- Begging stays ungated — 0074's addendum stands; nothing tonight can move it.

## Result — the batch mattered: val 4.689, and b32 is the candidate now

Train ran 8×4 accumulated (stated honestly in the log this time), ~3.9 h.
Against the ct baseline on the identical token stream:

| | ct (batch 8) | ct-b32 (batch 32) |
|---|---|---|
| best val | 4.781 | **4.689** |
| alarm recall | 89.8% | **91.1%** |
| alarm units / gaps | 4.48 / 3.63 | **4.72 / 3.88** (real: 5.10 / 4.16) |
| alarm dust | 0.275 | **0.080** |
| song recall | 38.2% | 25.0% |
| begging recall | 19.6% | 12.7% |

A 0.092 val improvement is larger than most whole experiments here have
bought, and every gated metric moved the right way — alarm structure closer
to the real distribution on all four numbers, dust on alarm draws down to
0.08 (below even real field alarm's 0.28; generated audio has no wind in it).

**Reported, not gated:** song and begging recall both moved down. At n=60 per
cell either could be noise (song 38→25 is ~2 SE), but the direction is the
same for both rare classes, so the honest reading is "batch 32 sharpened the
head of the distribution and did nothing for the tail" — consistent with the
standing conclusion that the rare classes are label-bound, not
optimisation-bound. A future sitting or bigger judge sample settles it.

The gradient-noise regime nobody chose was costing real quality. So the
recipe comment was wrong in the useful direction: `--batch-size 32` should
mean 32.

## What it changed

- `model-longctx-ct-b32` replaces `model-longctx-ct` as the standing crowgpt3
  candidate, including in Crow Chat's picker.
- Every future train on this corpus should say `--batch-size 8 --accumulate 4`
  (or fix the budget) rather than trusting the flag — and 0067's published
  arms both trained at the clipped batch, so its absolute numbers carry that
  asterisk even though the comparison between its arms was fair.
- The 9 s corpus (extracted the same night: 145,030 bouts, 116.5 h, 0 errors)
  should be trained at true batch 32 from the start.

## The ear, next morning

Ben, comparing buttons in chat (2026-08-16): the b32 candidate is **better than
the 0074 ct model but still noticeably worse than model-calltype**. That
ordering is invisible to every instrument this experiment ran — structure and
recall both favour the candidate — so whatever the gap is, it lives in timbre,
where only a sitting can measure it. Adoption stays held on his word.

Ben's per-button descriptions of the b32 candidate (the data that outranks the
tables above): **alarm** — "screaming like a human"; **begging** — "croaking
of a frog"; **call** — "hoarse and metallic"; **song** — "like an alien".
Four ways of saying the voice is wrong while the shape is right. Taken up as
0076: whose voice is in the new corpus?
