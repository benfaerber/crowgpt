# 0027 — Does filtering for caws help?

Ben's suggestion from the 0026 sitting: "I think filtering for caw like sounds
might work." By then it was the most promising untested lever — "it sounds
robotic" had already survived the fine codebooks (0024), density and recording
quality (0026), capacity and regularisation (0023), the codec bitrate, and both
a 433M and a 1.4B pretrained base (0022).

The case was in the project's own notes: `segment.py`'s burst detector is "a
bootstrap, not a call detector", and 0013 measured it passing 1.02 units per
window even in its emptiest confidence band. So some fraction of every training
run so far has been audio that is not a crow call.

**Filter:** BirdNET corvid confidence ≥ 0.8 everywhere, and for American Crow the
0021 head must confidently say `alarm call` or `call`. 81,389 bouts → 37,183;
American Crow 57,479 → 21,685. Same split seed, same hyperparameters as the
checkpoint 0026 rated.

## The answer: no

42 clips, three arms, criterion printed on the page before the first clip.

| arm | good |
|---|---:|
| real held-out caws | 13/14 (93%) |
| current model | 6/14 (43%) |
| caw-filtered model | **3/14 (21%)** |

Filtered against baseline: 3/14 vs 6/14, **Fisher p = 0.42**. Not significant, so
this does not establish that filtering made things worse. It establishes that it
did not make them better, which is what it was run to find out.

Real against baseline p = 0.013, real against filtered p = 0.0003.

## Settled by the control: filtering is neutral, the data loss was the cost

A same-size random control was trained — 30,049 sequences against the filtered
model's 30,162, per-species counts pinned to match, so the only difference is
*which* bouts. All four arms were then rated in one sitting.

| arm | good |
|---|---:|
| real held-out | 11/12 (92%) |
| full-corpus baseline | 3/12 (25%) |
| caw-filtered | 1/12 (8%) |
| same-size random control | 1/12 (8%) |

**Filtered against control: 1/12 vs 1/12, Fisher p = 1.0.** Not a small
difference — no difference. Filtering neither helps nor hurts.

**What hurt was the volume.** Both half-corpus models land at 8% against the full
corpus's 25%. That comparison is underpowered on its own (p = 0.59 each way), but
it points the same direction twice and it explains 0027's first result without
needing the filter to have done anything.

So the original headline was wrong in its reasoning even though its conclusion
survives: filtering for caw-like audio does not help. It also does not hurt. It
does nothing, and the 3/14 it scored was the corpus being halved.

### And validation loss failed again, harder

The filtered model reached best val **4.6602** against the control's **4.8089** —
a 0.15 nat gap, larger than the entire 0.164 the five-arm 0023 sweep produced,
and on models of identical size trained identically. A listener rated them
**1/12 and 1/12**.

That is the second clean case in this project of validation loss predicting a
difference the ear cannot find, and the cleaner of the two: 0023 compared a model
against itself with knobs moved, this compares two models whose only difference
is which half of the corpus they saw. Loss is now measuring something real about
how predictable a corpus is, and nothing about whether the output sounds like a
crow.

## The confound, which was real and is now resolved

The filtered model trained on 30,162 sequences against the baseline's 66,917,
and early-stopped at 19,000 steps against 38,000 — final gap +0.353 against
+0.202. **Less data, stopped sooner.** So "filtering did not help" is entangled
with "removing 55% of the corpus costs something", and this cannot separate them.

That control was run, and it is the section above. The filter is exonerated of
the harm and credited with nothing.

## The most useful thing in the session is the note

> "i am able to hear distinctive crow like vocalizations but they sound robotic.
> Most were crow like and I was tempted to hit good just because it sounds like a
> robot crow, it almost matches the caw pattern."

**Structure is learned; timbre is not.** The model gets the caw pattern — the
timing, the shape, the repetition — close enough that a listener is tempted to
pass it. What is wrong is the texture.

That is a sharper description of the defect than anything measured so far, and it
sits oddly beside 0024, which found the fine codebooks inaudible. If stages 5–7
carry nothing a listener can hear, then both the right structure and the wrong
timbre live in codebooks 0–4 together. The model is predicting those well enough
to reproduce a caw pattern and badly enough to sound synthetic doing it.

## What changed

- **The last cheap lever is spent.** Data filtering joins capacity,
  regularisation, bitrate, density, fine codebooks and pretrained bases on the
  list of things that do not fix it. What remains is the objective, the
  tokenizer, or a different model class — none cheap.
- **The defect has a better description**: right structure, wrong texture. Any
  future attempt should be judged on timbre, since the pattern is already close.
- **A same-size control is owed** before this result is quoted as "filtering does
  not work" rather than "filtering at 45% of the data does not work".

## Re-running

```bash
cd crowgpt
.venv/bin/python ../experiments/0027-does-filtering-for-caws-help/run.py   # ~2.5 GPU-hours
.venv/bin/python ../experiments/0027-does-filtering-for-caws-help/rate.py  # builds the page
```
