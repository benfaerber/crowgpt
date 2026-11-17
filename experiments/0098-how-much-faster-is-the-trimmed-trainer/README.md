# 0098 — How much faster is the trimmed trainer?

**2026-11-16** · GPU about 1 h 50 min · **answer: 2.7 times faster for
0.016 of validation loss, but only when batches are cut by tokens. Cut by
count, bucketing costs 0.09 and is not worth using.**

## The question

Reading the trainer for the generator study turned up two costs that have
nothing to do with the model. Batches are eight random sequences padded to
the longest, and lengths run from about 150 tokens to 3,600, so half of
every step is padding. And logits are computed over all 8,274 ids when
only about 1,024 are legal at any position. Two changes address them, both
opt-in on `Trainer`:

- `sliced_loss`: the loss over the legal ids only (`crowgpt/sliced.py`). A
  masked id contributes nothing to the softmax, so this is the same loss;
  `test_sliced_loss.py` checks the value and the gradients.
- `bucketed`: draw 64 batches' worth with the usual weights, sort by
  length, deal into batches (`BucketedBatcher`). Each sequence is drawn as
  often as before.

How much do they buy, and does the model still train as well?

## Method

- **`run.py`, speed.** The larger model (d512/L12/H4) for 200 optimiser
  steps per configuration after 20 of warm-up, counting non-padding target
  tokens per second.
- **`train.py`, quality.** 0097's best arm again (CrowGPT2's size, 60,000
  steps, peak rate 0.0006, same seed and panels) with both changes on, in
  two forms: eight sequences per batch, and batches cut to a token budget
  of 12,300 padded positions, which is what a plain batch of eight holds
  in real tokens on average. Scored on all 5,033 canonical American Crow
  validation bouts beside 0097's snapshot.

## Results

Speed, larger model:

| configuration | real tokens / s | real share of batch | peak memory |
|---|---:|---:|---:|
| as trained in 0096 | 58,900 | 47% | 9.3 GiB |
| sliced loss | 63,200 | 47% | 6.9 GiB |
| bucketed | 122,600 | 98% | 9.3 GiB |
| sliced + bucketed | 126,300 | 98% | 6.9 GiB |
| sliced + bucketed, batch 16 | 133,000 | 98% | 13.1 GiB |
| sliced + bucketed, batch 32 | out of memory | | |

Quality, CrowGPT2's size, 60,000 steps at 0.0006:

| trainer | full validation | training time |
|---|---:|---:|
| plain (0097) | 4.690 | 2 h 00 min |
| sliced + bucketed, eight per batch | 4.781 | 52 min |
| sliced + bucketed, token budget | 4.706 | 44 min |

## What it says

- **Bucketing is nearly all of the speed.** The sliced loss adds 7% and
  frees 2.5 GiB; it does not by itself make batch 32 fit.
- **Bucketing by count trains worse, by 0.09.** That gives back most of
  what 60,000 steps gained over CrowGPT2 (4.793). The loss is a mean over
  a batch's tokens, so eight short sequences get a full optimiser step for
  a tenth of the tokens eight long ones bring: short clips are overweighted
  and their steps are noisy.
- **A token budget recovers it to within 0.016.** The remaining gap is
  one seed against one seed, smaller than the 0.04 between the two learning
  rates in 0097, and may be nothing; batches of one length are also a
  plausible small cost.

## Caveats

- One seed per arm, so 0.016 is not distinguishable from zero here.
- The sliced loss and the token budget were tested together, not apart, on
  the full schedule. The sliced loss is exact by construction.
- Speed was timed on the larger model and quality on the smaller.
- The token-budget run sees the same number of real tokens per step as a
  plain run, in about a third of the time. A larger budget (more tokens
  per step at the old step cost) is untested and is a different question,
  since batch 32 hurt in 0080.

## What it changed

- **`Trainer` gained `sliced_loss`, `bucketed` and `token_budget`, all off
  by default.** No existing run or recipe changes.
- **Use all three together or not at all.** `bucketed` without
  `token_budget` is the losing arm and should not be used for a real run;
  the batcher's docstring says so.
- **A 60,000-step run of CrowGPT2's size now costs 44 minutes**, and
  120,000 steps about an hour and a half. For a run whose result will be
  compared at the 0.02 level (0097's size difference), the plain trainer
  is still the reference until a second seed says the 0.016 is noise.
