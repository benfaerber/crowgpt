# 0018 — Which species is the model actually failing?

## Overview

After listening to the generator's demo output, Ben reported that American Crow and Common Raven sounded good, that roughly half of everything sounded like garbage, and that there was nothing in between. This experiment checked all three impressions against 72 paired evaluation trials that had just run — and found the raw per-species scores said the opposite of the ear. The distribution of quality really is two-ended with little middle, and once each species' score is normalised by the best its audio codec can carry, the ear was right: American Crow sits at 99% of its achievable ceiling and Raven third, not last. The practical upshot was an inversion of priorities — for American Crow the model is no longer the constraint, the tokenizer is — and a standing rule that per-species scores are always reported as a share of their own codec ceiling.

## In depth

Run on 2026-07-31 over 72 paired trials, on the model at `crowgpt/results/model-long`.

*(This experiment was numbered 0016 when written, colliding with `0016-did-the-stranger-get-a-different-call` — two agents picked the next free number twenty minutes apart. It was renumbered to 0018; the stranger experiment keeps 0016 because it was written first and 0017 already cites it under that name.)*

### A. The bimodality is real

BirdNET confidence over 72 generated bouts:

| confidence | count |
|---|---|
| 0.00 – 0.05 | **20** |
| 0.05 – 0.25 | 14 |
| 0.25 – 0.50 | 12 |
| 0.50 – 0.75 | 8 |
| 0.75 – 1.00 | **18** |

28% score essentially zero and 25% score above 0.75, with the two ends the largest bins. The distribution is U-shaped, not centred: "either pretty good or pretty bad, no in between" is a correct description of the model's output, not an impression. That shape is the signature of *derailment*, the characteristic failure of autoregressive generation: one implausible token puts the context off the training distribution and nothing afterwards recovers, which predicts failures should be near-total rather than graceful — exactly what the histogram shows.

### B. The raw per-species scores are misleading

| species | generated |
|---|---|
| american-crow | 0.686 |
| rook | 0.427 |
| eurasian-jackdaw | 0.425 |
| carrion-crow | 0.296 |
| hooded-crow | 0.263 |
| **common-raven** | **0.258** |

Read alone, this says Common Raven is the worst species — flatly against the listening report. Believing it would have sent the next round of work at exactly the wrong target.

### C. Normalised by what is achievable, the ear was right

The codec puts a hard ceiling under every species, and it is not the same for each. BirdNET scores real raven at 0.591, but real raven put through the codec at only 0.347 — half what American Crow gets — and the model cannot exceed that however good it becomes.

| species | real | codec ceiling | generated | **share of ceiling** |
|---|---|---|---|---|
| american-crow | 0.805 | 0.693 | 0.686 | **99%** |
| rook | 0.730 | 0.527 | 0.427 | 81% |
| common-raven | 0.591 | 0.347 | 0.258 | **74%** |
| carrion-crow | 0.603 | 0.443 | 0.296 | 67% |
| eurasian-jackdaw | 0.749 | 0.722 | 0.425 | 59% |
| hooded-crow | 0.665 | 0.550 | 0.263 | 48% |

Raven moves from last to third. American Crow and Raven are the two the listener picked out, and against the achievable target they are first and third. The ear was right and the raw number was wrong, because the raw number silently compares species whose ceilings differ by a factor of two. An absolute confidence is only comparable within one species.

### D. The finding that changes what to do next

American Crow is at 99% of its codec ceiling. For the species the project is actually about — the Poe family's species, the one with a strong call-type head, and by then 84% of the corpus — the model is no longer the constraint; the tokenizer is. More training, more data and more capacity cannot move American Crow by more than a point, because only a point remains between the model and the best its codec can carry. That inverted the standing plan, which had the 12 kbps codec rung last in the ladder as the speculative one to drop if a night ran short; for American Crow it became the only rung that can help.

### Caveats

These numbers score generated audio against a bird detector; they are pipeline measurements over the training corpus, which is dominated by archive audio, and say nothing about the field recordings or the Poe family birds themselves. The derailment reading of the U-shape is a named hypothesis, not a demonstrated mechanism.

### What changed

- **12 kbps was promoted from last to first** for American Crow work. Experiment 0014 measured the ceiling rising from 0.810 to 0.877 retention there, and section A shows the model has already taken everything the 6 kbps ceiling offers.
- **Per-species scores are normalised by the codec arm from now on.** The raw ranking put Raven last where it is third, and would have aimed the next experiment at the wrong species.
- **Hooded Crow is the worst at 48% of ceiling**, and is the species to examine if the question is where the model itself is weakest — not Raven.
- **Derailment became the named, testable hypothesis** for the U-shaped distribution: if failures are derailment, a bout's confidence should be predictable from how far in the first improbable token appears. Nothing had measured that yet.

The listening report is the reason any of this was found: the numbers were already on disk and were being read the wrong way round.
