# 0041 — A forced-choice instrument, validated on a question already answered

**2026-08-03** · 65 pairs · **the instrument works, and it found a 65% left bias**

## Why

0038 caught the rating page grading against company: `model-fair-k8` — identical
weights — scored 0.21 in one sitting and 0.54 in the next while the real anchor
held at 0.92 in both, and every repeated arm's score tracked its *rank* inside
its sitting. A forced choice has no company. It also estimates one quantity,
P(A preferred), against a null of exactly 0.5, rather than differencing two noisy
rates.

A new instrument that only produces new answers cannot be trusted, so the sitting
was built to check itself: 40 pairs of the open question, 15 of a comparison
already settled, and 10 catch trials.

## Results

### Catch — real vs fairk8, 10 pairs

**real 9, fairk8 1.** P(fairk8) = 0.10, interval excludes 0.5. The listener was
engaged and real beats generated, as it must. These are excluded from every model
comparison — pairing generated against real has a known answer and measures
nothing about models, which was Ben's objection to the original design and the
reason they are catch trials rather than an arm.

### Known — fairk8 vs k5-matched, 15 pairs

**fairk8 11, k5-matched 4.** P(fairk8) = 0.73, interval [0.53, 0.93], excludes
0.5. Absolute rating settled this the night before at 0.54 against 0.17.

**The instrument reproduces a known answer.** That is what licenses reading the
open one.

### Open — fairk8 vs dac44, 40 pairs

**fairk8 20, dac44 12, and 8 too close to call.** Raw P(fairk8) = 0.62;
side-balanced, 0.65. The interval marginally includes 0.5, so this is **still not
resolved** — but it is tighter than 0037's attempt and it points the other way.

| | 0037 (absolute rating) | 0041 (forced choice) |
|---|---|---|
| favours | dac44, barely | **fairk8** |
| interval width | 0.50 | 0.31 |

Combined with 0037's null the fair summary is: **DAC-44 did not beat EnCodec-8 at
the generator, and may be worse.** The 20% too-close rate on this pairing against
0% on the other two is the same finding from the inside — these two are genuinely
hard to separate, where the others were not.

## The instrument found a bias in the listener

**Left was chosen on 37 of 57 decided trials — 0.65, interval [0.53, 0.75],
excludes 0.5.** A real side preference, and *as large as the model effect under
test*.

It shows up inside the open pairing too:

| fairk8 placed | wins | rate |
|---|---|---|
| on the left (14×) | 12 | 0.86 |
| on the right (18×) | 8 | 0.44 |

A 42-point swing on the same model, from which button it sat above. Randomising
sides only cancels that *in expectation*: over 32 trials it put fairk8 left 14
times and right 18, so the bias leaked into the raw number and had to be
corrected afterwards.

**Fixed by construction rather than by correction.** `PairPage` now balances each
arm-pairing exactly — half flipped, half not, per pairing rather than in
aggregate, since balancing only the total lets one comparison sit left-heavy
while another compensates and cancels nothing for either. Two tests hold it.

This is the second time recording a nuisance variable paid for itself: 0040
needed recording ids that Phase 3 never stored, and this needed the side, which
existed only because the page was written to record it.

## What this changed

- **The forced choice is the instrument for model-vs-model from now on.** It
  reproduced a known answer, resolved the catch set, and gave a tighter interval
  than absolute rating on the same question.
- **Absolute rating keeps one job**: how far from real. Forced choice cannot say
  that, and it is the number that says whether the project is going anywhere.
- **Never randomise a nuisance variable you can balance.** Random assignment is
  what let a 65% side bias reach the estimate.
- **Ben's report on it: "much easier and less stressful".** Worth recording — the
  pace was 4.4 s a trial against ~1.4 s for a single clip, so it is slower per
  trial and covers two clips, and it removed the part he found effortful, which
  was holding a scale in his head.
- **DAC-44 is unlikely to be the answer.** Two instruments, neither resolving it,
  both now pointing at EnCodec-8 or a tie. The tokenizer route stays closed.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0041-a-forced-choice-instrument/run.py
```

About four minutes. Session in `crowgpt/results/listening/pairwise-0041/`.
