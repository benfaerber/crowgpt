# 0027 — Does filtering for caws help?

## Overview

By the end of experiment 0026, the last untested cheap fix for the generator's "robotic" sound was Ben's own suggestion: filter the training corpus down to confidently caw-like audio, since the burst detector that cut it is "a bootstrap, not a call detector" and passes non-call audio. A model was trained on the filtered corpus and rated blind against the current model and real audio. The answer is no — and a same-size random control then showed the filter did precisely nothing: the filtered model and the control both rated 1/12 good, so the drop from the baseline's rating was the cost of halving the corpus, not of the filter. Validation loss also failed as a quality proxy for the second time, predicting a 0.15-nat difference between two models the ear rated identically.

## In depth

### The filter and the first sitting

Filter: BirdNET corvid confidence ≥ 0.8 everywhere, and for American Crow the experiment-0021 head must confidently say `alarm call` or `call`. This cut 81,389 bouts to 37,183 (American Crow 57,479 to 21,685). Same split seed and hyperparameters as the checkpoint experiment 0026 rated. 42 clips, three arms, criterion printed on the page before the first clip — the lesson from 0026.

| arm | good |
|---|---:|
| real held-out caws | 13/14 (93%) |
| current model | 6/14 (43%) |
| caw-filtered model | 3/14 (21%) |

Filtered against baseline: Fisher p = 0.42 — not significant, so this does not establish that filtering made things worse, only that it did not make them better, which is what it was run to find out. Real against baseline p = 0.013; real against filtered p = 0.0003.

### The confound, and the control that resolved it

The filtered model trained on 30,162 sequences against the baseline's 66,917 and early-stopped at 19,000 steps against 38,000 (final gap +0.353 against +0.202) — less data, stopped sooner. So "filtering did not help" was entangled with "removing 55% of the corpus costs something".

A same-size random control was trained — 30,049 sequences against the filtered model's 30,162, per-species counts pinned to match, so the only difference is *which* bouts. All four arms were then rated in one sitting.

| arm | good |
|---|---:|
| real held-out | 11/12 (92%) |
| full-corpus baseline | 3/12 (25%) |
| caw-filtered | 1/12 (8%) |
| same-size random control | 1/12 (8%) |

Filtered against control: 1/12 vs 1/12, Fisher p = 1.0. Not a small difference — no difference. Filtering neither helps nor hurts. What hurt was the volume: both half-corpus models land at 8% against the full corpus's 25%. That comparison is underpowered on its own (p = 0.59 each way), but it points the same direction twice and explains the first sitting's result without needing the filter to have done anything. The original headline was wrong in its reasoning even though its conclusion survives.

### Validation loss failed again, harder

The filtered model reached best val 4.6602 against the control's 4.8089 — a 0.15-nat gap, larger than the entire 0.164 nats the five-arm experiment-0023 sweep produced, on models of identical size trained identically. A listener rated them 1/12 and 1/12. That is the second clean case of validation loss predicting a difference the ear cannot find, and the cleaner one: 0023 compared a model against itself with knobs moved; this compares two models whose only difference is which half of the corpus they saw. Loss is measuring something real about how predictable a corpus is, and nothing about whether the output sounds like a crow.

### The most useful thing in the session is the note

> "i am able to hear distinctive crow like vocalizations but they sound robotic. Most were crow like and I was tempted to hit good just because it sounds like a robot crow, it almost matches the caw pattern."

Structure is learned; timbre is not. The model gets the caw pattern — timing, shape, repetition — close enough that a listener is tempted to pass it; what is wrong is the texture. That is a sharper description of the defect than anything measured so far, and it sits oddly beside experiment 0024, which found the fine codebooks inaudible: both the right structure and the wrong timbre must live in codebooks 0–4 together.

### Caveats

- All rating cells are small (12–14 clips per arm); the volume effect in particular is underpowered and rests on pointing the same direction twice.
- The corpus counts describe the training pipeline's archive-dominated corpus, not field recordings.

### What changed

- The last cheap lever is spent. Data filtering joins capacity, regularisation, bitrate, density, fine codebooks and pretrained bases on the list of things that do not fix "it sounds robotic". What remains is the objective, the tokenizer, or a different model class — none cheap.
- The defect has a better description: right structure, wrong texture. Any future attempt should be judged on timbre, since the pattern is already close.
- The same-size control that the first sitting owed was run, and it settled the question: the filter is exonerated of the harm and credited with nothing.
