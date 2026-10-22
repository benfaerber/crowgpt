# Can we tell the crows apart?

## Overview

This experiment asked whether individual crows in the Poe family — five named birds — could be told apart from audio alone, by clustering acoustic features of their calls. Since not one second of audio in the corpus is attributed to a named bird, the experiment could not test identity directly; instead it calibrated a fixed clustering method against recordings where the truth is known. The answer is no: a recording containing five crows produced exactly as much apparent cluster structure as a recording of one crow, and the structure that does exist tracks where the bird was standing (loudness and time), not who it was. The result closed the audio-only route to caller identity at this recording range and turned planned video-based attribution from a convenience into a requirement.

## In depth

### Method

Units came from `crowgpt.segment.Segmenter` at its packaged 12 dB threshold (validated in experiment 0013 §E; re-tuning is a documented trap). Features were duration, peak frequency, spectral centroid, flatness, fraction above 2 kHz, and MFCC 1–12 mean and standard deviation. K-means was run within a single recording, never across recordings.

Anything encoding loudness was deliberately excluded as a feature — no RMS term and no MFCC 0, since coefficient zero is log energy in cepstral form. Experiment 0016 showed range dominates this corpus, and birds in a flock stand at different distances, so log-energy is a position sensor. Loudness was kept only as a confound the clusters were scored against.

Four recordings were chosen for what they rule out:

| | | |
|---|---|---|
| **88** | one crow, 6 units | the floor — structure found here was produced with nothing to find |
| **87 vs 88** | the same crow, 44 s apart | success at telling them apart would be failure |
| **104** | fledglings + one adult | the ceiling — the only real labels, and the easiest question |
| **113** | five crows, 49 units, one call type | the main test |

### The floor: five birds look exactly like one

Capture 113 was subsampled to capture 88's 6 units before comparison, because silhouette climbs with sample size even on structureless data.

| k | capture 88 (**one** crow) | capture 113 (**five** crows), n=6 | |
|---|---|---|---|
| 2 | 0.196 | 0.195 [0.104, 0.469] | inside the floor |
| 3 | 0.100 | 0.131 [0.066, 0.223] | inside the floor |

This is the whole experiment: the five-bird recording sits at the median of what the one-bird recording produces. Whatever the clusters in capture 113 are — the bird turning its head, variation across a bout, the detector's edges — one crow makes just as many of them.

### What the clusters actually track

| cap | k | bout ARI | loudness η² | time η² | call-type ARI |
|---|---|---|---|---|---|
| 88 | 2 | 0.348 | 0.362 | 0.438 | — |
| 100 | 6 | 0.077 | **0.808** | 0.423 | 0.074 |
| 104 | 3 | 0.188 | 0.119 | 0.095 | — |
| 113 | 5 | 0.159 | 0.343 | **0.476** | — |

Capture 113's clusters are best explained by time (η² 0.476) and loudness (0.343). Capture 100's clusters are 81% loudness — very nearly a rangefinder. Both are position: loudness is how far away the bird was, time is where it had moved to by then. In a static flock position partly *is* identity — if one bird always sits in the tree, a position-based split can look like a bird-based split — but it is not voice: it stops working the moment the birds move and cannot generalise to the next recording. Notably, bout membership was *not* what the clusters found (ARI 0.159 on capture 113), which was the predicted false positive from experiment 0006; the confound here is geometry, not episode.

### Both controls gated, and both gatings are findings

The ceiling test never ran: capture 104's units by age class were 13 juvenile and 0 adult. The adult's only call sits in a single 42–51 s span in which the segmenter finds nothing at 12 dB — the adult is too far off to clear a threshold the begging fledglings clear easily. So the corpus cannot support even the easiest version of the question (fledgling vs. adult in one recording); individual identity is not merely unproven here, it is untestable.

The same-bird control gated too. Captures 87 and 88 were recorded 44 seconds apart on the same phone at the same distance band, both described as a single crow on top of a tall building — almost certainly one bird, twice. They differ by 9.3 dB of band SNR (12.4 vs 21.7), and the quieter recording yielded 3 units against 6 — too thin to run the classifier. The gating restates experiment 0016's result exactly: half the detected calls of one bird disappear across 9 dB, so any count, rate or duration compared between recordings at different ranges is measuring the range.

### What was not run, and why

No BirdNET or AST embedding space was tested. The floor result makes it moot: if one bird already produces the structure five birds produce, a richer feature space cannot fix the problem, because the problem is not resolution — it is that there is nothing to check an answer against. Those should be run when there is ground truth to score against, not before.

### Caveats

The recordings used here are real field captures of the Poe family, but the labels are thin: the only age-class ground truth (capture 104) yielded no adult units, and no recording has per-bird attribution. All silhouette and confound numbers are within-recording; nothing here generalises across recordings.

### What changed

The audio-only route to caller identity is closed at this range, and `phases/data-collection.md` was right to plan caller attribution from roof-station video instead — this null turns that from a convenience into a requirement. Three concrete outcomes:

1. **A `caller` field on labels.** The recordist cannot name a bird listening back, but can often name it live, when one visible bird is calling. An optional caller field, set only in that case, is the minimum change that makes this question answerable rather than boundable.
2. **Record solo birds, close and long.** The within-bird yardstick here is six units from one crow at 20–50 m; what is needed is one bird alone at 5–20 m for 60+ seconds, repeated across days. Edgar is identifiable in the field by his brood-guard role, so the same-bird-across-sessions control is collectable now.
3. **A second recorder, eventually.** Two synchronised devices give time-difference-of-arrival and therefore a position per call — position being the one confound a single microphone cannot break.

One standing rule was set: if a "which bird" feature is ever built, it ships with the 87/88 same-bird control beside it, or it does not ship. The run script asserts at startup that no per-bird table or caller column exists and raises if one appears, so the experiment cannot silently keep measuring the absence of ground truth after identity becomes recordable.
