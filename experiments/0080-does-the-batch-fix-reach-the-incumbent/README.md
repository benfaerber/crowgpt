# 0080 — does the batch fix reach the incumbent?

**2026-08-19, predictions before results** · build: train ~4 h (GPU, booked) +
validation ~30 m · **answer: pending**

## The question

0075 proved the silent batch-8 clip was costing the conditioned model real
quality (val −0.092, alarm dust 0.275 → 0.080). The incumbent
`model-longctx` — the CrowGPT2 checkpoint behind the chat button, the
galleries and the release — still carries the clipped batch. This retrains
its exact recipe (tokens-6s, unconditioned + units, 30k steps) at a true
effective 32, and doubles as 0079's deconfounding arm: with
`model-longctx-b32` in hand, long9 vs longctx-b32 compares the 9 s window at
matched batch, separating "window hurt" from "batch moved the profile".

## Predictions

- Val beats 4.686 by roughly 0075's margin; dust collapses the same way
  (0.297 → ~0.1).
- Structure holds or improves against the 6 s real reference.
- The 0079 re-read: if longctx-b32's units also drop toward long9's 3.70, the
  9 s "regression" was the batch profile, not the window, and the ladder
  verdict softens; if longctx-b32 holds ~4.4+, the ladder stays closed.

## Build

`crowgpt/tools/night_0080.sh`: train `--steps 30000 --n-embd 384 --n-layer 8
--dropout 0 --batch-size 8 --accumulate 4 --token-dir tokens-6s --out
results/model-longctx-b32`, then the 0067/0079 structure instruments: arms
longctx vs longctx-b32 (both 460 frames, T 1.1 / k 200, finetuned decoder)
against 200 real 6 s test bouts, dust on the same draws, seeds 45000+.

## Gate (decided before results)

Nothing swaps automatically — the incumbent is a **release** (crowgpt2), and
a release recipe never changes under its name. If val improves and structure
holds, longctx-b32 becomes the natural base for any crowgpt3-unconditioned
discussion and a candidate for Ben's ear in chat; the release decision is his
and separate.

## Result — no: the batch fix does not reach the incumbent

Val went the wrong way: 4.766 against the incumbent's 4.686 on the identical
token stream. Structure tied (4.15 vs 4.24 units, gaps 3.36 vs 3.44 — noise),
dust nominally worse but inside the seed-batch wobble this instrument shows
across runs. The incumbent keeps its recipe and its slot; longctx-b32 is a
recorded arm, not a candidate.

The finding with legs: **the batch effect is not universal.** The same
correction that bought the conditioned stream 0.092 of val (0075) costs the
unconditioned stream 0.080. Whatever effective batch 8's gradient noise was
doing, the two token streams wanted opposite doses of it, and "always train
at the batch the flag claims" is now known to be recipe-specific rather than
a law.

The 0079 deconfound also lands: longctx-b32 holds ~4.2 units, nowhere near
long9's 3.70 — so the 9 s regression was the window, not the batch, and the
ladder stays closed at 6 s.

## What it changed

- crowgpt2's recipe stands untouched; no release discussion follows.
- The batch rule is downgraded from "always 32" to "measure per stream":
  conditioned 6 s wants 32 (0075), unconditioned 6 s wants 8 (this).
- 0079's asterisk resolves against the window; 12 s stays struck.
