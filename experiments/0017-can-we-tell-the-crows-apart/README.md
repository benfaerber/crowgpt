# Can we tell the crows apart?

**Answer: no, and not for want of a better algorithm.** Five crows in one
recording produce exactly as much apparent cluster structure as one crow does.
What structure exists tracks where the bird was standing, not who it was.

## Why

The goal is a caption: "Crow A cawed at 3 s, Crow B at 8 s." The Poe family has
five names — Thrasher and Ripjaw the parents, Killer and Shredder the fledglings,
Edgar the yearling helper — and **not one of them is attached to a single second
of audio.** There is no crows table, no caller column on `labels`, and the
recordist confirmed he cannot attribute a call to a bird even listening back.

That makes clustering unfalsifiable in the way experiment 0016 was: with no
labels, any method returns five clusters if you ask for five, and nothing says
whether they are birds. So this experiment does not try to find individuals. It
tries to **bound** the answer, by calibrating a fixed method against recordings
where the truth is known.

## Method

Units from `crowgpt.segment.Segmenter` at its packaged 12 dB (0013 §E validated
it; re-tuning is the documented trap). Features are duration, peak frequency,
spectral centroid, flatness, fraction above 2 kHz, and **MFCC 1–12** mean and
standard deviation. K-means within a single recording, never across.

**What is deliberately not a feature: anything encoding loudness.** 0016 showed
range dominates this corpus, and birds in a flock stand at different distances,
so log-energy is a position sensor. That means no RMS term and **no MFCC 0** —
coefficient zero is log energy wearing a cepstral hat, and including it is the
quiet way this experiment would have fooled itself. Loudness is kept only on the
other side of the ledger, as a confound the clusters are scored against.

Four recordings, chosen for what they rule out:

| | | |
|---|---|---|
| **88** | one crow, 6 units | the floor — structure found here was produced with nothing to find |
| **87 vs 88** | the same crow, 44 s apart | success at telling them apart would be failure |
| **104** | fledglings + one adult | the ceiling — the only real labels, and the easiest question |
| **113** | five crows, 49 units, one call type | the main test |

## Results

### The floor: five birds look exactly like one

Capture 113 is subsampled to capture 88's 6 units before comparison, because
silhouette climbs with sample size even on structureless data.

| k | capture 88 (**one** crow) | capture 113 (**five** crows), n=6 | |
|---|---|---|---|
| 2 | 0.196 | 0.195 [0.104, 0.469] | inside the floor |
| 3 | 0.100 | 0.131 [0.066, 0.223] | inside the floor |

**This is the whole experiment.** The five-bird recording sits at the median of
what the one-bird recording produces. Whatever the clusters in 113 are — the bird
turning its head, variation across a bout, the detector's edges — one crow makes
just as many of them.

### What the clusters actually track

| cap | k | bout ARI | loudness η² | time η² | call-type ARI |
|---|---|---|---|---|---|
| 88 | 2 | 0.348 | 0.362 | 0.438 | — |
| 100 | 6 | 0.077 | **0.808** | 0.423 | 0.074 |
| 104 | 3 | 0.188 | 0.119 | 0.095 | — |
| 113 | 5 | 0.159 | 0.343 | **0.476** | — |

Capture 113's clusters are best explained by **time** (η² 0.476) and loudness
(0.343). Capture 100's are 81% loudness — the clustering is very nearly a
rangefinder.

Both are position: loudness is how far away the bird was, time is where it had
moved to by then. Worth stating the subtlety, because it is the strongest version
of the opposing case — **in a static flock, position partly *is* identity.** If
Edgar always sits in the tree and the fledglings are always on the ground, then a
position-based split will look like a bird-based split. But it is not voice: it
stops working the moment they move, and it cannot generalise to the next
recording, where the same bird stands somewhere else.

Notably bout membership is *not* what was found (ARI 0.159), which was the
predicted false positive from 0006. The confound here is geometry, not episode.

### The ceiling gated, and the gating is a finding

Capture 104's units by age class: **13 juvenile, 0 adult.**

The adult's only call sits in a single 42–51 s span, and the segmenter finds
nothing in it at 12 dB — the adult is too far off to clear a threshold the
begging fledglings clear easily.

So the corpus cannot support the *easiest* version of this question: telling a
begging fledgling from an adult caw, in one recording, with time-in-recording
confounded helpfully in its favour. Individual identity is not merely unproven
here. It is untestable.

### The same-bird control gated too, and that is also a finding

Captures 87 and 88 were recorded 44 seconds apart on the same phone at the same
distance band, both described as "a single crow on top of a tall building", 87
named for Edgar. Almost certainly one bird, twice.

They differ by **9.3 dB** of band SNR (12.4 vs 21.7) — and the quieter recording
yielded **3 units against 6**. Too thin to run the classifier, but the gating
restates 0016's result exactly: half the detected calls of one bird disappear
across 9 dB, so any count, rate or duration compared between recordings at
different ranges is measuring the range.

### What was not run, and why

No BirdNET or AST embedding space was tested. The floor result makes it moot: if
one bird already produces the structure five birds produce, a richer feature space
cannot fix the problem, because the problem is not resolution. It is that there is
nothing to check an answer against. Run them when there is ground truth to score
against — not before.

## What changed

**The audio-only route is closed at this range, and `phases/data-collection.md`
was right to plan caller attribution from roof-station video instead.** This
turns that from a convenience into a requirement.

Three concrete things:

1. **A `caller` field on labels — the change this null buys.** `FUTURE.txt` says
   which bird called is "unrecordable". That is wrong in the one case that
   matters: the recordist cannot name a bird *listening back*, but he can often
   name it **live**, when one visible bird is calling. Capture 103's observation
   already does exactly this in prose — "Edgar watches from the top of the apt".
   `FamilyStore`'s docstring has even chosen the shape: `crows(name, role,
   family_id)`. An optional caller, set only when one bird is visibly calling, is
   the minimum change that makes this question answerable rather than boundable.
   It is the same lesson as the stranger tags earlier the same day: the corpus
   answers the questions its metadata can express, and no others.

2. **Record solo birds, close and long.** The within-bird yardstick here is six
   units from one crow at 20–50 m. What it needs is one bird alone at 5–20 m for
   60+ seconds, repeated across days — and Edgar is identifiable in the field by
   his brood-guard role, so the same-bird-across-sessions control is collectable
   now, for free, with the phone that already exists.

3. **A second recorder, eventually.** Two synchronised devices give
   time-difference-of-arrival, and therefore a position per call. Position is the
   one confound a single microphone cannot break, and separating position from
   voice is precisely what this experiment could not do.

And one standing rule: if a "which bird" feature is ever built, it ships with the
87/88 same-bird control beside it, or it does not ship.

## Re-running

```
pipelines/representation/.venv-birdnet/bin/python \
    experiments/0017-can-we-tell-the-crows-apart/run.py
```

The script asserts at startup that no per-bird table or caller column exists, and
**raises if one appears** — this experiment measures the absence of ground truth,
so the day identity becomes recordable it must be rewritten rather than quietly
continuing to measure the wrong thing.
