# 0046 — "Crow plus modem" is a stuck coarse codebook

**2026-08-04** · 60 real bouts against 60 generated · no listening, no labels

## The question

Ben, hearing a generated bout next to a real one and a codec round-trip of the
same recording:

> *"codec seems good, possibly minor quality degredation. ai gen it matches the
> shape of crow calls good. but it still does have some modem type sounds. so it
> is crow + modem"*

Two things in that, and the second is measurable. He **localises** the defect —
the codec is nearly fine, the modem arrives with the model. And **"modem" is a
sharper word than "robotic"**: a modem is *periodic*. Sustained, tonal,
repeating. That is a prediction about the token stream rather than a feeling
about the audio.

A codec frame is 13 ms. If the generator holds the same codebook entry across
neighbouring frames more often than real audio does, the waveform sustains one
spectral shape instead of moving — and a sustained repeating shape is what a
modem is.

## Result — fraction of adjacent frames whose code changes

| stage | real | top_k=200 | top_k=None |
|---|---|---|---|
| **0** | **0.868** | **0.801** | **0.837** |
| 1 | 0.936 | 0.924 | 0.934 |
| 2 | 0.956 | 0.946 | 0.957 |
| 3–7 | 0.974–0.988 | 0.976–0.993 | 0.981–0.995 |
| mean | 0.959 | 0.950 | 0.960 |

**The generator is too sticky, and only in the coarse codebook.** Stage 0 changes
on 80% of frame pairs where real audio changes on 87%. Stages 3–7 sit at or
slightly *above* real, so this is not general over-smoothing — it is specific to
the stage that carries structure and pitch.

**`stages.py` predicted this in a docstring, before anyone heard it:**

> *"Cooling a correctly-uncertain distribution does not clean it up; it makes the
> sampler re-pick the same arbitrary residual code over and over, which is
> periodic, and periodic is what 'robotic' sounds like."*

### top-k owns about half of it

Removing the truncation takes the stage-0 gap from −0.066 to −0.031, and brings
the **mean to 0.960 against real's 0.959** — indistinguishable. Mechanically that
follows: truncating to the 200 most likely ids removes exactly the tail that
would have broken a repeat. It agrees with 0043, which found top-k flattening
the output offline.

### What this cannot claim

**0044's sitting could not resolve top-k by ear** — P(no top-k) = 0.41 over 30
pairs, if anything favouring keeping it. An offline signal against a null by ear
is the exact shape of 0023 and 0027, and in this project **the ear wins**. So
this measures a mechanism and its size; it does not license changing the sampling
default.

Honest summary: *the stickiness is real, top-k causes about half of it, and
nobody has yet shown that fixing it is audible.*

**And half the gap is not top-k's.** Stage 0 sits 0.031 below real with no
truncation at all. That residual belongs to the model rather than the sampler —
it is intrinsically less willing to move the coarse code than the corpus is,
which is 0027's "right structure, wrong texture" with a number attached for the
first time.

## What this changed

- **The defect has a measurable signature at last.** Every previous attempt to
  characterise "robotic" reached for spectral distance or codec artefacts. This
  is a property of the token stream, costs two minutes, needs no listener, and
  can gate a model before a sitting is spent on it.
- **A concrete target rather than "be like real audio":** stage-0 churn 0.868.
  Any future generator can be checked against it immediately.
- **The residual is the model's, and it is the thing to attack.** No sampling
  change can reach the 0.031 that survives top-k removal.
- **It does not move the sampling default.** 0044 owns that decision and its
  answer was "unresolved"; this adds a mechanism, not a verdict.
- **Ben's ear localised it correctly before any of this ran** — codec nearly
  fine, modem from the model — and the measurement then found exactly that.

## Re-running

```bash
cd crowgpt
PYTHONPATH=src .venv/bin/python ../experiments/0046-crow-plus-modem-is-a-stuck-codebook/run.py
```

About two minutes. Writes `results.json` here.
