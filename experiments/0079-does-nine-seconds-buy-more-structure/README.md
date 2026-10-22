# 0079 — does nine seconds buy more structure?

**2026-08-17, predictions before results** · build: tokenize ~25 m + preflight +
train ~6 h (GPU, booked) + validation · **answer: pending**

## The question

0067 doubled the window to 6 s and closed most of the structure gap; its
"What it changed" names the 9–12 s rung as next, before capacity. The 9 s
corpus has been ready since the 0075 night (145,030 bouts, 116.5 h, zero
errors). This trains the rung: the longctx recipe (units, no call types — the
voice question stays cleanly separated in 0078) on bouts-9s at a true
effective batch 32 from the start, the correction 0075 earned.

First genuinely novel block size in the project: ~5,470 tokens needs
`--block-size` past the 4096 default, and the memory budget will clip the
micro-batch to ~4 — so a 50-step preflight goes ahead of the train, and the
chain stops there if the card cannot carry it.

## Predictions

- By 0067's extension: the 9 s real reference will show more units and more
  gaps than the 6 s one, and model-long9 closes toward it the way longctx
  closed toward 6 s real — most of the gap, not all.
- The null: 0068 already found the 6 s window's extra reach thin; nine
  seconds may buy arrangement the corpus cannot teach (only ~? bouts actually
  reach past 6 s — the tokenize manifest will say), and the metrics land on
  top of longctx's. A null here closes the window ladder cheaply.

## Build

`crowgpt/tools/night_0079.sh`: tokenize `--units --variants 2 --bouts
bouts-9s --out tokens-9s` → manifest assert (call_types [], units 5) →
50-step preflight at `--block-size 6000 --batch-size 4 --accumulate 8` →
full train, same flags, `--steps 30000 --out results/model-long9` →
structure validation: model-long9 @ 690 frames vs model-longctx @ 460, both
through the finetuned decoder at T 1.1 / k 200, against 200 real 9 s test
bouts (the reference moves with the cap or the comparison is a category
error — 0067's rule).

## Gate (decided before results)

Nothing adopts tonight. The rung is worth keeping if model-long9 beats
longctx on units/bout and gaps/clip against the 9 s reference by more than
noise; it is a recorded null if the arms land together. Either way the
result feeds the ladder decision (12 s or stop) and nothing else.

## Result — the ladder closes: nine seconds bought nothing

Against the 9 s real reference (5.69 units/bout, 4.75 gaps/clip), model-long9
landed at 3.70 / 2.78 — **farther from real than the 6 s incumbent** (4.42 /
3.51 drawn at 460 frames). The extra window did not buy arrangement; on these
instruments it cost some. The 12 s rung is not worth a night on this recipe.

One confound, named rather than hidden: long9 trained at true batch 32 while
the incumbent trained at the clipped 8, so "window hurt" and "batch changed
the structure profile" are entangled — long9's dust rate is 0.087 against the
incumbent's 0.297, the same collapse batch 32 produced in 0075. The
deconfounding arm is the incumbent recipe at batch 32, which 0080 trains for
its own reasons; read the two together when it lands.

## What it changed

- The window ladder (0067's "9–12 s before capacity") closes at 6 s: the 6 s
  corpus remains the standing choice, and 12 s is struck without being run.
- bouts-9s and tokens-9s stay on disk as the record; model-long9 is an
  experiment, not a candidate for anything.
