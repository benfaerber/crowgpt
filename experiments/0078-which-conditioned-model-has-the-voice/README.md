# 0078 — which conditioned model has the voice?

**2026-08-17, predictions before results** · build: ~20 m draws + registration ·
**answer: pending, in Ben's doses**

## The question

Ben's ear ranks model-calltype above the b32 candidate on every button, and
three experiments of instruments could not see why — 0076 cleared the corpus,
0077 killed the optimisation story, and the instruments now disagree among
themselves. What remains (conditioning×window, the units token) cannot be
separated by anything but ears, so the ranking becomes a pool: model-calltype
vs model-longctx-ct-b32, each serving exactly what chat serves (calltype
T 1.0 / 225 frames; b32 T 1.1 / 460 frames, both through the finetuned
decoder), conditioned across all four types, 10 compares per type plus 8
real-vs-generated catches — 48 trials, three doses of 16, cooldown 30.

The requested call type is deliberately not shown: the question is the voice,
and Ben's descriptions were type-independent ("human scream", "frog",
"metallic", "alien"). Types ride in each trial's facts for the analysis.

## Predictions

- Ben's informal verdict holds: P(calltype preferred) clearly above 0.5, and
  the graded margins say "noticeably" rather than "slightly".
- The defect families in his notes cluster on the b32 clips and echo the four
  descriptions already on the record.
- The null: the pool comes back nearer a coin flip than "noticeably" —
  informal chat listening and blinded anchored grading disagree, which has
  happened before in this project and would be worth exactly as much.

## Build

`sitting.py`, the 0069 shape: conditioned draws per type per arm (seeds
43000+ per-type blocks, clear of every recorded range), fresh test-split
anchors skipping the 168 consumed by earlier sittings, clips into
`crowgpt/results/listening-pools/voice-0078/`, registered with
`register_pool.py --dose-size 16 --cooldown 30`. No tail doses: 48 = 3×16.

## Result — pending

## What it changed — pending
