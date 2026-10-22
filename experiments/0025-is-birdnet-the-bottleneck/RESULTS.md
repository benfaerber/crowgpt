# Is BirdNET the bottleneck for call types, or is it the window?

## Overview

The call-type classifier is a linear probe on frozen BirdNET embeddings, and BirdNET is trained to tell species apart — so it may compress the within-species variation that call types live in. This experiment separated that hypothesis from a cheaper one, that the fixed 3-second analysis window is misaligned with the 1-second labels. The answer: the backbone is the bottleneck and Perch 2.0 is better at it — Perch given one second of audio beats BirdNET given three, on the same rows and folds, with the largest gain on exactly the mob-versus-alert distinction the question was about. The window hypothesis is a measured null (centring it actually costs a little). BirdNET stays for detection and species ID; only the embeddings feeding the call-type head were in question.

## In depth

### The candidates

Three things could be losing the call-type nuance: (a) the window — BirdNET scores on a fixed non-overlapping 3 s grid at `3*(second//3)`, so a 1 s label sits at an arbitrary offset inside it, and a caw is 200–500 ms; (b) the taxonomy — 4 CORE classes over what the 2026 León paper shows is a graded continuum; (c) the backbone. This experiment separates (a) from (c); (b) needs no experiment, since no backbone fixes it. The challenger is Perch 2.0 (arXiv 2508.04665), state of the art on BirdSet and BEANS linear probing and validated on a call-type dataset in its own paper — not the previously named candidate BirdAVES, which the 2026 comparative review (arXiv 2508.01277) puts near the bottom on linear probing (65.6 BEANS AUROC against 85.6 for Perch and BEATs).

### Three preflight findings that reframed the question

Measured on the committed caches before any comparison; `run.py --preflight` asserts all three.

1. On the crow-tools corpus the 3072-d feature is 1024 real dimensions: for all 2,494 cached rows the std block is exactly zero and the max block is bit-identical to the mean, because one 3 s window is pooled per label. So "pooling destroys sequence structure" is true of the deployed path and vacuous on the training corpus.
2. The shipped `flight call: 0.975` is measured on a feature that identifies the source of every positive: all 40 flight-call positives live in the archive cache, and 155/160 of its rows have non-zero std against 0/2,494 crow-tools rows — the std block is a near-perfect corpus indicator. So the incumbent to beat is experiment 0012, not `models/american-crow/metrics.json`.
3. Every crow-tools span is exactly 1 second (3,162 of 3,162), so the planned duration-quantile probe has no duration variable and was dropped rather than deferred.

### Method

2,339 labelled segments over 1,098 recordings (down from the cache's 2,494/1,195 — 97 recordings have lost their audio), every arm joined by segment key. The probe in `experiments/lib/probe.py` is logic-identical to the pipeline's, and the run aborts unless it reproduces experiment 0012's numbers (alarm 0.942 / begging 0.916 / call 0.961 / song 0.913) on the committed cache — it does, to the decimal. Audio is decoded once into a 48 kHz, 9 s excerpt centred on each labelled second, and every arm windows the same samples, so "Perch got more context" can only ever be a claim about one argument.

Arms: **A** birdnet-grid (the incumbent anchor), **B** birdnet-centred (A vs B isolates grid jitter), **C** perch-3s (the backbone at matched context), **D** perch-1s and perch-5s (the context ladder), **G** birdnet+perch concatenated (replace, or add?).

### Results

Recording-grouped 5-fold. Macro-F1 over the four CORE classes; mob vs alert is restricted to the 26 recordings carrying both, where recording identity provably cannot be the answer, with 5-seed spreads.

| arm | macro-F1 | mob vs alert | spread | rattle vs softSong |
|---|---|---|---|---|
| A birdnet-grid | 0.849 | 0.637 | [0.612, 0.637] | 0.901 |
| B birdnet-centred | 0.855 | 0.540 | [0.524, 0.540] | 0.858 |
| D perch-1s | 0.856 | 0.759 | [0.709, 0.759] | 0.866 |
| C perch-3s | 0.871 | 0.741 | [0.700, 0.741] | 0.900 |
| C perch-3s, noise pad | 0.878 | 0.760 | [0.703, 0.760] | 0.893 |
| D perch-5s | 0.831 | 0.725 | [0.685, 0.725] | 0.780 |
| G birdnet+perch | 0.858 | 0.736 | [0.711, 0.736] | 0.850 |

Per-class AUC moves little, as pre-registered — the CORE classes sit at 0.90–0.97 with about 0.04 of headroom. Best arm against the incumbent: alarm 0.953→0.957, begging 0.914→0.940, call 0.970→0.980, song 0.904→0.923.

**The context ladder settles it.** Perch at 1 s beats BirdNET at 3 s — 0.856 vs 0.849 macro-F1, and 0.759 vs 0.637 on mob vs alert with non-overlapping spreads — on a third of the audio. And more context hurts: perch-5s (0.831) is the worst arm in the table, because a 5 s window centred on a 1 s label reaches into neighbouring calls. 3 s is close to right, and right for both models.

**The window is a null, and slightly worse than null.** Centring BirdNET's window buys +0.006 macro-F1 and costs 0.10 on mob vs alert (0.637 → 0.540, spreads separate). The cheap fix did not work, which is worth as much as the one that did: `build_dataset.window_for` should be left alone.

**Error accounting:** perch-3s fixes 127 of BirdNET's CORE errors and breaks 84 — a net gain, not a reshuffle. Centring is a reshuffle (82 fixed, 69 broken).

**Replace, do not add.** The pre-registered concatenation arm scores 0.858, below perch-3s alone at 0.871; the BirdNET dimensions dilute rather than add.

**Fine repertoire recovery: nobody wins.** Predicting the 41 upstream-derived cluster ids with ≥20 segments across ≥5 recordings: birdnet-grid 0.205, birdnet-centred 0.221, perch-1s 0.243, perch-3s 0.209, perch-5s 0.188. Pre-registered one-sided (the cluster ids may themselves derive from BirdNET embeddings), and it stays uninformative: 41-way fine repertoire is not recoverable from any of these frozen embeddings with a linear probe.

**The real ceiling is overlapping callers.** Split by how many crows the reviewer heard: on single-crow segments (n=1794) perch-3s noise pad reaches 0.875 against BirdNET's 0.848; on segments with two or more birds (n=536) nothing helps and Perch is slightly worse (0.747–0.750 vs 0.775). The entire Perch gain is on single-crow segments — the segmentation ceiling experiment 0016 measured from the other side, and the strongest argument here for a per-event detector (Voxaboxen) rather than a better backbone.

### Against the pre-registered verdict

The MIGRATE bar was ≥0.03 macro-F1 *and* non-overlapping mob-vs-alert spreads, sustained at perch-3s. perch-3s clears the spread condition decisively and lands at +0.022 macro-F1; the noise-pad variant reaches +0.029. The 0.03 bar was not cleared and has not been moved. What makes it a migrate case anyway is what the thresholds could not anticipate: perch-1s beats birdnet-3s on both metrics with a third of the audio, and a rival that wins while starved is stronger evidence than one that wins by 0.03.

**Caveat, stated rather than buried:** mob vs alert is n=91 over 26 recordings — the metric with headroom and the metric with the least data. The spreads separate across five seeds, but this deserves re-running when the field corpus can contribute labels of its own. (The labelled corpus here is archive material; the field corpus held too few labels to participate — 0006's re-run per backbone was skipped because it would produce only refusals.)

### Methods notes worth keeping

- An mp3 seeking bug nearly produced a confident wrong answer: the first excerpt cache used `ffmpeg -ss` before `-i`, which fast-seeks to a frame boundary — a random few-tens-of-milliseconds jitter over half the corpus, in an experiment about temporal alignment. Caught by validating arm A against the committed cache (1,028 of 2,035 rows exact, the rest at cosine 0.98 with no pattern). Fixed by decoding each recording once and slicing sample-exactly; any future arm must go through `experiments/lib/excerpts.py`.
- Perch pads and peak-normalises internally, and neither could be controlled away: its API returns one pooled 1536-d vector per 5 s window, so every short arm is part audio and part padding (perch-1s is 20% real). Noise padding *helps* (+0.007 over zero padding), so the short arms are lower bounds on Perch and the ladder conclusion is conservative.

### What this changed

- The backbone question is answered and the previously named candidate was wrong: Perch 2.0, not BirdAVES. The other half of that entry — Voxaboxen for overlapping callers — is now the better-supported half.
- The window hypothesis is retired; `build_dataset.window_for` stays as it is.
- Pooling is not the problem it was assumed to be on the training corpus, where two thirds of the shipped feature is constant.
- `models/american-crow/metrics.json` may no longer claim 0.975 for flight call without saying it is measured across a corpus boundary that predicts the label.
- A migration is justified but not started. It is a real cost — five shipped heads retrained, a second venv and a subprocess in the inference path (BirdNET disables CUDA at import, so the two can never share a process), and `analyzer/birdnet.py` restructured to embed regions after grouping. That file now refuses to load a head whose feature width or backbone does not match, so the migration will fail loudly rather than at the 400th capture.

`results.json` and `probes.json` in this folder hold the numbers; the 4 GB excerpt cache lives under `data/` and is gitignored, so the numbers are the durable part.
