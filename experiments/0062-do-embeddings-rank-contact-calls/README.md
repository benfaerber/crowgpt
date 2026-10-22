# 0062 — do BirdNET's embeddings rank contact calls?

**2026-08-09** · the same 459 windows 0060 scored, probed with a logistic
over BirdNET's 1024-d embeddings · **answer: yes for crows — 0.97 AUC on
Hooded Crow, 0.983 with the recordist held constant; chance for ravens**

## The question

0061 measured Ben's lemon: real but weak — an envelope-shape combo reaches
0.637 grouped and leaves 60% of alarm in the funnel. Before building
anything, the feature space the project already ships deserved its turn:
BirdNET embeddings drove every Phase-4 head, and 0060's arms are a labeled
contact-vs-alarm set nobody had used.

## Method

The exact windows 0060 scored, re-sliced from the same capped decodes.
Logistic regression (C=0.1) over `BirdNet.embed_indexed` features,
recording-grouped 5-fold CV — identical grouping to 0061's combo, so the two
numbers are comparable and recording identity cannot leak into either.

Confound chased rather than hoped away: every Hooded Crow contact recording
is a single recordist's series, so the headline could have been his
microphone. Where a species' whole contact arm is one recordist who also has
alarm recordings in the sample, the AUC is recomputed over his recordings
alone — same gear, same habits, only the call type varying.

## Result

| slice | AUC | n (contact / alarm bouts) |
|---|---|---|
| all bouts, grouped CV | **0.815** | 78 / 381 |
| Hooded Crow only | **0.970** | 33 / 306 |
| Hooded Crow, single-recordist control | **0.983** | 33 / 179 |
| Northern Raven only | 0.488 | 45 / 75 |
| 0061's shape combo, same grouping | 0.637 | — |

At the operating point that keeps 80% of contact bouts, **36.5% of alarm
survives** overall (0061: 59.5%) — and the pooled number is dragged down
almost entirely by the ravens. For the crow, the separation is close to
clean, and it *rises* under the recordist control, so it is the call and not
the microphone.

**The raven result is inconclusive, not negative**: four contact recordings,
one of them a long family session whose "contact calls" span a whole
vocabulary of family noise. Nothing that thin can kill or confirm a probe.

Standing caveats: recordist-asserted at recording level, European corvids,
and alarm is the only confuser measured — begging, song and non-corvid noise
meet this probe unmeasured. Its output is a candidate *ranking* for a
trained ear, never a label.

## What it changed

- **The funnel now has a ranker, not just a finder.** 0060's detections
  find corvid bouts; this probe orders them so contact candidates surface
  first — for crow-like calls, nearly cleanly. The surfacing page can sort
  by `score` in `results.json`'s rows today.
- **The lemon retires as a ranker, stays as a description.** 0061's three
  real shape numbers were the ear's intuition validated, but the embedding
  space contains them and more; no shape-based prefilter should be built.
- **What would raise trust in the probe on American Crow**: a handful of
  window-session captures with calm-context chips, scored by this probe —
  the first field test the FUTURE entry's contact class was always waiting
  on.
