# 0015 — Is CrowGPT copying, or just playing it safe?

**2026-07-30** · 240 generated bouts across 10 sampling settings

## The question

`crowgpt`'s judge reported that generated bouts share an exact token n-gram with
the training set **37.5%** of the time over ~213 ms, against **4.3%** for
held-out real audio scored identically. That was written up as memorisation, and
it was the most damning number in the module.

There is a confound, and it is not a small one. Sampling at temperature 0.95 with
top-k 200 draws from the model's high-probability region, and **the most probable
patterns are the most common training patterns**. A model that had memorised
nothing whatsoever would still overlap more than natural audio does, simply by
playing it safe.

The two come apart under temperature. Mode-seeking is a property of *sampling*
and should melt as temperature rises; memorisation is a property of the
*weights* and should not.

## Method

The shipped 7.3M-parameter model, unchanged. Five temperatures × top-k 200 or
off, 24 bouts each (4 per species). For every setting: exact n-gram overlap at 16
frames (~213 ms) against the canonical training set, and BirdNET's verdict on the
same bouts placed in real ambience. Overlap is measured at the coarse codebook,
because matching all eight is 64 identical tokens in a row and returns zero for
generated *and* real audio alike.

Held-out real base rate: **0.043**.

## Result

| temperature | top-k | overlap | × base rate | BirdNET detects | mean duration |
|---|---|---|---|---|---|
| 0.70 | 200 | 0.958 | 22.1× | 0.25 | 3.00 s |
| 0.70 | off | 0.917 | 21.2× | 0.21 | 2.94 s |
| 0.85 | 200 | 0.667 | 15.4× | **0.42** | 2.83 s |
| 0.85 | off | 0.542 | 12.5× | 0.29 | 2.75 s |
| 1.00 | 200 | 0.250 | 5.8× | 0.29 | 2.26 s |
| 1.00 | off | 0.167 | 3.8× | 0.38 | 2.18 s |
| **1.15** | **200** | **0.043** | **1.0×** | **0.38** | 1.73 s |
| 1.15 | off | 0.000 | 0.0× | 0.25 | 1.71 s |
| 1.30 | 200 | 0.000 | 0.0× | 0.25 | 1.46 s |
| 1.30 | off | 0.000 | 0.0× | 0.04 | 1.62 s |

**It is mode-seeking, and the earlier claim was wrong.**

At T=1.15 with top-k 200 the overlap is **0.043 — exactly the held-out real base
rate**, to three decimal places. Generated audio matches the training set no more
often than recordings the model has never heard. A model carrying memorised spans
could not do that: memorised content does not evaporate when you raise the
sampling temperature. Whatever the weights hold, it is not stored copies.

The 37.5% was real, but it was a property of *how the shipped model was being
sampled*, not of what it learned.

## The setting was never chosen

Temperature 0.95 and top-k 200 were defaults typed while writing `sample.py`,
and nothing had measured them. They turn out to be close to the worst available
combination of the two things anyone cares about.

**T=1.15 / top-k 200 is free.** Detection 0.38 against the shipped 0.39 — inside
noise at n=24 — while overlap drops from 8.7× the base rate to 1.0×. There is no
trade being made here; the shipped default was simply worse on one axis and the
same on the other.

Two things the table shows that are worth keeping:

- **Top-k matters more than it looks, and not monotonically.** At every
  temperature except 1.00, turning it off makes detection worse. Unbounded
  sampling from a 1,024-way codebook admits tokens the model barely believes in,
  and one bad fine-codebook token is audible.
- **Hotter bouts are shorter** — 3.00 s at T=0.70 down to 1.46 s at T=1.30. The
  model ends bouts sooner when sampling is less conservative, so temperature is
  quietly also a duration knob. Whether shorter is better by ear is not something
  these numbers answer.

T=1.30 is where it falls apart: with top-k off, detection collapses to 0.04,
which is the sound of a model with no constraints left.

## What changed

- **The memorisation claim is retracted.** `crowgpt/README.md`, the root
  `README.md` and the `TODO.txt` entry all said the model recalls training spans
  far more often than novel audio does. True at the shipped setting, false as a
  statement about the model, and all three are corrected.
- **The sampling default moves to T=1.15 / top-k 200**, which costs nothing
  measurable and removes the overlap entirely.
- **"Sample colder" is deleted from the TODO as a lever.** It was the first of
  three suggested fixes and it is precisely backwards: T=0.70 is the worst
  setting in the table on both axes at once, 22× the base rate *and* the second
  worst detection rate.
- **A methodological note worth reusing:** an overlap statistic measured at one
  sampling setting says nothing about a model on its own. The held-out base rate
  made the number interpretable; the temperature sweep made it attributable. The
  first without the second was enough to reach a confident wrong conclusion.

Nothing here says the model is good — detection sits at 0.38 against a codec
ceiling of 0.81, and it still sounds rough. It says the roughness and the
overlap are not evidence of copying.

## Re-running

```bash
cd crowgpt && PYTHONPATH=src .venv/bin/python \
  ../experiments/0015-is-it-copying-or-playing-it-safe/run.py
```

About 50 minutes, dominated by autoregressive generation (1,800 tokens per bout,
one forward pass each) rather than by BirdNET. Needs `crowgpt/results/model/` and
the token memmaps under `data/crowgpt/tokens/`.
