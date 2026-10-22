# "Crow plus modem" is a stuck coarse codebook

## Overview

After listening to generated crow calls, Ben described them as "crow + modem": the shape of a crow call, with a periodic electronic sound on top. Because a modem is periodic, that impression makes a testable prediction about the model's token stream — that the generator repeats the same codec codebook entry across neighbouring 13 ms frames more often than real audio does. Measured over 60 real bouts against 60 generated ones, with no listening and no labels, the prediction held: the generator is too "sticky", and only in the coarse codebook (stage 0), which carries structure and pitch. About half of the gap is caused by top-k sampling truncation; the other half belongs to the model itself. This gives the "robotic" defect a cheap, measurable signature for the first time, though nobody has yet shown that fixing it is audible.

## In depth

**Question.** Ben, hearing a generated bout next to a real one and a codec round-trip of the same recording, said: *"codec seems good, possibly minor quality degredation. ai gen it matches the shape of crow calls good. but it still does have some modem type sounds. so it is crow + modem."* He localised the defect — the codec is nearly fine, the modem arrives with the model — and "modem" is sharper than "robotic" because a modem is periodic: sustained, tonal, repeating. A codec frame is 13 ms; if the generator holds the same codebook entry across neighbouring frames more often than real audio does, the waveform sustains one spectral shape instead of moving, and a sustained repeating shape is what a modem is.

**Measure.** The fraction of adjacent frames whose code changes ("churn"), per codebook stage, on 60 real bouts against 60 generated. About two minutes to run, no listener needed.

**Result.**

| stage | real | top_k=200 | top_k=None |
|---|---|---|---|
| **0** | **0.868** | **0.801** | **0.837** |
| 1 | 0.936 | 0.924 | 0.934 |
| 2 | 0.956 | 0.946 | 0.957 |
| 3–7 | 0.974–0.988 | 0.976–0.993 | 0.981–0.995 |
| mean | 0.959 | 0.950 | 0.960 |

The generator changes its stage-0 code on 80% of frame pairs where real audio changes on 87%. Stages 3–7 sit at or slightly above real, so this is not general over-smoothing — it is specific to the stage that carries structure and pitch. Notably, `stages.py` had predicted this in a docstring before anyone heard it: *"Cooling a correctly-uncertain distribution does not clean it up; it makes the sampler re-pick the same arbitrary residual code over and over, which is periodic, and periodic is what 'robotic' sounds like."*

**Top-k owns about half of the gap.** Removing the truncation takes the stage-0 gap from −0.066 to −0.031 and brings the mean to 0.960 against real's 0.959 — indistinguishable. Mechanically that follows: truncating to the 200 most likely ids removes exactly the tail that would have broken a repeat. It agrees with experiment 0043, which found top-k flattening the output offline. The other half — the 0.031 stage-0 gap that survives with no truncation at all — belongs to the model rather than the sampler: it is intrinsically less willing to move the coarse code than the corpus is. That is experiment 0027's "right structure, wrong texture" with a number attached for the first time.

**What this cannot claim.** Experiment 0044's listening sitting could not resolve top-k by ear — P(no top-k) = 0.41 over 30 pairs, if anything favouring keeping it. An offline signal against a null by ear is the exact shape of experiments 0023 and 0027, and in this project the ear wins. So this measures a mechanism and its size; it does not license changing the sampling default. The honest summary from the README: *the stickiness is real, top-k causes about half of it, and nobody has yet shown that fixing it is audible.*

**What this changed:**

- The defect has a measurable signature at last. It is a property of the token stream, costs two minutes, needs no listener, and can gate a model before a listening sitting is spent on it.
- A concrete target rather than "be like real audio": stage-0 churn 0.868. Any future generator can be checked against it immediately.
- The residual gap (0.031 with no truncation) is the model's own, and it is the thing to attack — no sampling change can reach it.
- It does not move the sampling default. Experiment 0044 owns that decision and its answer was "unresolved"; this adds a mechanism, not a verdict.
- Ben's ear localised the defect correctly before any of this ran — codec nearly fine, modem from the model — and the measurement then found exactly that.

Full per-stage numbers, including the per-stage gaps for both sampling settings, are in `results.json` in this folder.
