# 0074 — can the long window take orders?

**2026-08-15, predictions before results** · build: label 25 m (CPU) + tokenize 16 m +
train 58 m (GPU) · **answer: mostly — and the gate says HOLD, on begging alone**

## The question

model-longctx (the CrowGPT2 checkpoint) is the best generator this project has
and cannot be asked for anything: its manifest carries no call types. The one
model that answers Crow Chat's buttons is model-calltype — 31 Jul, 3 s window,
frozen-decoder era. This retrains the long-context recipe with the 0021
call-type prefix added: same corpus (bouts-6s), same architecture, same steps,
conditioning the only difference. If it conditions without losing what 0067
bought, chat gets its buttons on the good model and the checkpoint becomes
release crowgpt3.

## Predictions

Extrapolated from the record rather than freshly elicited; Ben may amend before
the night runs.

- **From 0021:** recall is monotonic in labelled bouts, and the label counts
  barely move between corpora (train-split human bouts: ~723 alarm on bouts-6s
  vs the v1-era set that produced 92.9% alarm recall). So alarm recall should
  land near 90% again; begging near 50%; call and song stay weak — data-bound,
  not window-bound (FUTURE.txt's ~2,000-per-class rule).
- **From 0067:** conditioning is one extra prefix token against a 3,600-token
  sequence; the structure metrics (units/bout, gaps) should be within noise of
  the incumbent. The window bought arrangement; a prefix token should not sell
  it back.
- **The null shape:** conditioning at 6 s costs structure (metrics regress
  toward the 3 s twin's), or the pseudo-label pass on the 6 s bouts is
  degenerate (longer bouts mix call types inside one bout, so single-class
  overlap gets rarer and the head abstains more) — the histogram gate below
  catches the second before the train spends its two hours.

## Build

Pieces committed this time (0021's labelling step never was):
`crowgpt label-calltypes` (the 0021 recipe as a CLI stage) and
`crowgpt tokenize --call-types` (positional file, size-checked). Chain in
`crowgpt/tools/night_0074.sh`:

1. `label-calltypes --bouts bouts-6s` → `bouts-6s/call_types.json` (CPU/TFLite)
2. `check_labels.py` — histogram gate
3. `tokenize --units --variants 2 --call-types … --out tokens-6s-ct` (~16 m)
4. `check_manifest.py` — prefix_len 4, sampled_slots 2, five call types
5. `train --steps 30000 --n-embd 384 --n-layer 8 --dropout 0 --batch-size 32
   --token-dir tokens-6s-ct --out results/model-longctx-ct` (~2 h GPU)
6. `smoke.py` — Sampler loads, one draw per type, no crash

Matched-recipe note, on the record: night_0067's `--batch-size 32` actually
trained at **micro-batch 8** (memory_budget 240e6 ÷ (block 3612 × vocab 8274)),
and this run keeps that clip on purpose — the same effective batch, so
conditioning stays the only difference. If the extra prefix token pushes the
clip to 4, the chain stops and the rerun uses `--accumulate 2`.

prefix_len 4 (species + call type + unit bucket + duration) has never existed
before; the manifest gate and the smoke draws are the cheap places it fails.

## Gate (decided before results)

Adopt for the chat worker and mint release crowgpt3 iff all of:

1. Forced-choice **alarm recall ≥ 80%** (0021's harness, repointed; T 1.1 /
   k 200 / 460 frames). **Begging > 25%** (above 4-way chance). Call and song
   are reported, not gated — the held-out anchor has n=3 / n=5 there and any
   verdict would be noise.
2. **Structure within ±15%** of incumbent model-longctx on units/bout (4.13),
   single_share (0.26), gaps/clip (3.32), median gap (0.299 s) — 100 draws per
   arm against the same 200 real 6 s test bouts, both arms through the
   finetuned decoder.
3. **Dust no worse** than the incumbent at the same cell (relative, same
   decoder state — lib/dustprobe's rules).
4. Manifest call types validate against the worker's list; a hand-listen to a
   few per-type draws contains no garbage.

Reject/hold: alarm < 60%, any structure metric > 25% away from the real
reference, or a degenerate label histogram. **Val loss is excluded** — a
different token stream is a different yardstick.

## Result — HOLD, and the reason is begging, not the window

The build itself was clean: labels in 25 minutes (16 ms/bout), all four classes
above their historical floors, prefix_len 4's first outing sampled without
complaint, the matched recipe held (batch 8×1, block 3613). The label pass was
the night's first real finding — **begging 5,707 and song 2,205 pseudo-labelled
bouts, both crossing the ~2,000 rule the old corpus never met** (v1: 2,764 and
1,306). One first-run stumble on the record: the label gate's original flat
500-per-class floor stopped the chain for `call` at 364 — its usual size (272
built model-calltype) — and was corrected to per-class historical floors.

Anchor: 83.3% vs 69.7% always-alarm on 132 held-out human bouts (0021's was
90.3% on 154 — weaker anchor, same shape). Forced-choice recall at the serving
cell (T 1.1 / k 200 / 460 frames):

| requested | 0021 (model-calltype) | 0074 (model-longctx-ct) |
|---|---|---|
| alarm call | 92.9% | **89.8%** |
| begging | 50.0% | **19.6%** |
| song | 16.4% | **38.2%** |
| call | 3.8% | **0%** |

Song more than doubled with its label pool, exactly the monotonic-in-data rule.
Begging went the other way despite tripled labels — and its draws are also the
dusty ones (below) — which reads as **pseudo-label noise, not data volume**:
6 s bouts mix call types more than 3 s ones, the head's begging calls got less
precise, and the generator learned a diluted token. A wrong pseudo-label is
worse than none, exactly as calltype.py warns.

Structure, all arms drawn fresh at the serving cell, real = 200 test bouts:

| arm | units | single | gaps | med gap | dust |
|---|---|---|---|---|---|
| real 6 s | 5.10 | 0.065 | 4.16 | 0.267 | — |
| model-longctx (no prefix) | 3.72 | 0.17 | 2.83 | 0.288 | 0.281 |
| ct, "unknown" prefix | 2.45 | 0.28 | 1.64 | 0.299 | 0.284 |
| ct, alarm requested † | 4.48 | 0.183 | 3.63 | 0.245 | 0.275 |
| ct, begging requested † | 4.08 | 0.183 | 3.22 | 0.288 | **0.538** |
| ct, call requested † | 4.22 | 0.15 | 3.35 | 0.299 | 0.346 |
| ct, song requested † | 3.98 | 0.2 | 3.12 | 0.267 | 0.346 |

† post-hoc supplement (serving_structure.py), labelled as such: the gate's
structure arm drew the ct model with its default prefix, which is the
"unknown" token — a condition chat never serves. Under every *requested* type
the conditioned model's structure **beats the incumbent** and moves toward
real; the regression the gate caught lives entirely in the unknown bucket.

**Gate verdict: HOLD.** Alarm passes (89.8% ≥ 80). Structure passes under the
serving condition (and the pre-registered wording did not fix the prefix, so
the generous reading is available) — but it does not matter, because
**begging fails cleanly on both instruments**: 19.6% against a >25% chance
bar, and dust at 0.538 against the incumbent's 0.281. No goalposts moved; the
model does not ship with a begging button that mostly produces dusty alarm.

## Addendum, same night — the begging post-mortem killed every cheap fix

0075 was booked as "fix the begging labels, retrain". Four hypotheses were
measured before spending the card, and all four died:

1. **Confidence floor — dead.** The head's confidence over its 5,618
   pseudo-begging calls is saturated: median 0.986, p75 0.999; a 0.95 floor
   still keeps 3,669. `class_weight="balanced"` on a 556-vs-76 train set makes
   rare-class probabilities incapable of ranking their own mistakes.
2. **Duration cap (mixed-content bouts) — dead.** Pseudo-begging bouts are not
   longer than human begging (median 4.09 s vs 5.13 s).
3. **The dust catastrophe — half-retracted.** Per-type references on real
   human-labelled bouts: begging 0.416, call 0.590, alarm 0.280, song 0.258.
   Real begging is dusty by the probe's one threshold — rasp reads as low
   pitch strength — so generated begging's 0.538 is +0.12 over its own
   reference, not +0.26 over an alarm-dominated one. Generated alarm matches
   real alarm to three decimals (0.275 vs 0.280); generated call at 0.346 is
   *less* dusty than real call, consistent with an ignored token producing
   generic caws. The gate's single dust reference was miscalibrated for
   per-type conditioning; a future gate should reference per type.
4. **Units × call-type scramble — no signature.** Begging's unit-bucket
   distribution in the token set is shaped like every other class's.

What remains true: begging recall 19.6% against the judge's own 59% ceiling on
real begging (13/22 held-out) — a real deficit of uncertain size, measured by
a weak instrument on exactly this class. The paths that remain are the ones no
retrain can shortcut: **human begging labels** (112 exist; the ~2,000 rule
says that is the wall) and **Ben's ear on the live begging button**, which is
in chat as of tonight. The 0075 GPU booking was struck without being used —
the retrain it was booked for had no evidence left to act on.

## What it changed

- `crowgpt label-calltypes` and `tokenize --call-types` now exist — the 0021
  step that was never committed cannot evaporate again, and any future corpus
  gets pseudo-labels for two commands and ~40 minutes.
- The follow-up has a shape (0075, if taken): **fix the begging labels, not
  the model** — raise the head's confidence floor for begging (or take begging
  from human labels only), re-tokenize (16 m), retrain (1 h), and re-gate with
  the structure arm pre-registered as per-requested-type. Everything else
  about this checkpoint already clears its bars.
- Until then the chat worker stays on model-calltype, and model-longctx-ct
  stays in results/ as the evidence — not a release, not promoted, not deleted.
