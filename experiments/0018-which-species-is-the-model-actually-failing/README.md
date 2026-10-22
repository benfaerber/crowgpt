# 0018 — Which species is the model actually failing?

*(Numbered 0016 when written on 2026-07-31, colliding with
`0016-did-the-stranger-get-a-different-call` — two agents picked the next free
number twenty minutes apart. Renumbered to 0018; the stranger experiment keeps
0016 because it was written first and `0017` already cites it under that name.)*

**2026-07-31** · 72 paired trials, the model at `crowgpt/results/model-long`

## The question

Listening to the demo, Ben reported three things: American Crow and Common Raven
sound good, roughly half of everything sounds like garbage, and there is nothing
in between — it is either convincing or it is noise.

All three are checkable against the paired evaluation that had just run, and one
of them contradicted what the numbers said on their face.

## A. The bimodality is real

BirdNET confidence over 72 generated bouts:

| confidence | count |
|---|---|
| 0.00 – 0.05 | **20** |
| 0.05 – 0.25 | 14 |
| 0.25 – 0.50 | 12 |
| 0.50 – 0.75 | 8 |
| 0.75 – 1.00 | **18** |

**28% score essentially zero and 25% score above 0.75**, with the two ends the
largest bins. The distribution is U-shaped, not centred. "Either pretty good or
pretty bad, no in between" is a correct description of the model's output and not
an impression.

That shape is the signature of *derailment*, which is the characteristic failure
of autoregressive generation: one implausible token puts the context off the
training distribution, and nothing afterwards recovers. It predicts that failures
should be near-total rather than graceful, which is what the histogram shows.

## B. The raw per-species scores are misleading, and say the opposite of the ear

| species | generated |
|---|---|
| american-crow | 0.686 |
| rook | 0.427 |
| eurasian-jackdaw | 0.425 |
| carrion-crow | 0.296 |
| hooded-crow | 0.263 |
| **common-raven** | **0.258** |

Read alone, this says Common Raven is the **worst** species — flatly against the
listening report. Believing it would have sent the next round of work at exactly
the wrong target.

## C. Normalised by what is achievable, the ear was right

The codec puts a hard ceiling under every species, and that ceiling is not the
same for each. BirdNET scores *real* raven at 0.591, and real raven through the
codec at only **0.347** — half what American Crow gets. The model cannot exceed
that however good it becomes.

| species | real | codec ceiling | generated | **share of ceiling** |
|---|---|---|---|---|
| american-crow | 0.805 | 0.693 | 0.686 | **99%** |
| rook | 0.730 | 0.527 | 0.427 | 81% |
| common-raven | 0.591 | 0.347 | 0.258 | **74%** |
| carrion-crow | 0.603 | 0.443 | 0.296 | 67% |
| eurasian-jackdaw | 0.749 | 0.722 | 0.425 | 59% |
| hooded-crow | 0.665 | 0.550 | 0.263 | 48% |

Raven moves from last to third. American Crow and Raven are the two the listener
picked out, and against the achievable target they are first and third. **The ear
was right and the raw number was wrong**, because the raw number silently
compares species with ceilings that differ by a factor of two.

Every per-species figure this project quotes from here should be a share of its
own ceiling. An absolute confidence is only comparable within one species.

## D. The finding that changes what to do next

**American Crow is at 99% of its codec ceiling.**

For the species this project is actually about — the Poe Family's species, the
one with a strong call-type head, and now 84% of the corpus — the model is no
longer the constraint. The tokenizer is. More training, more data and more
capacity cannot move American Crow by more than a point, because there is only a
point left between the model and the best its codec can carry.

That inverts the standing recommendation. The plan had 12 kbps last in the
ladder, as the speculative rung to drop if a night ran short. For American Crow
it is now the *only* rung that can help.

## What changed

- **12 kbps is promoted from last to first** for American Crow work. 0014
  measured the ceiling rising from 0.810 to 0.877 retention there, and A shows
  the model has already taken everything the 6 kbps ceiling offers.
- **Per-species scores are normalised by the codec arm** from now on. The raw
  ranking put Raven last where it is third, and would have aimed the next
  experiment at the wrong species.
- **Hooded Crow is the worst at 48%**, and is the species to look at if the
  question is "where is the model itself weakest" — not Raven, and not on the
  strength of the raw score.
- **Derailment is the named hypothesis** for the U-shaped distribution, and it
  is now testable: if failures are derailment, the confidence of a bout should be
  predictable from how far in the first improbable token appears. Nothing has
  measured that yet.

The listening report is the reason any of this was found. The numbers were
already on disk and were being read the wrong way round.

## Re-running

```bash
cd crowgpt && make evaluate          # writes results/evaluation.json
```
Then the analysis here is a few lines over `mean_conf_values`, twelve per species
in the order the manifest lists them.
