# Is BirdNET the bottleneck for call types, or is it the window?

**Answer: it is the backbone, and Perch 2.0 is better at it. The window is a
measured null.** Perch given **one second** of audio beats BirdNET given three,
on the same rows and the same folds. The gain is largest on exactly the
distinction our taxonomy collapses — `mob` vs `alert` inside "alarm call" —
which is the nuance the question was about.

BirdNET stays for detection and species ID. Only the embeddings feeding the
call-type head are in question here.

## Why ask

BirdNET is trained to tell species apart, so it may compress the within-species
variation call types live in. Reasonable, but not the only candidate. Three
things could be losing the nuance:

- **(a) the window** — BirdNET scores on a fixed non-overlapping 3 s grid at
  `3*(second//3)`, so a 1 s label sits at an arbitrary offset inside it, and a
  caw is 200–500 ms
- **(b) the taxonomy** — 4 CORE classes over what the 2026 León paper shows is a
  graded continuum (`FUTURE.txt`)
- **(c) the backbone**

This separates (a) from (c). (b) needs no experiment — no backbone fixes it.

`FUTURE.txt` already asked for this ("evaluate before the next head is trained,
not after") and named **BirdAVES**. That is the wrong candidate: the 2026
comparative review (arXiv 2508.01277) puts AVES at 63.8 and BirdAVES at 65.6
BEANS linear-probe AUROC against Perch and BEATs at 85.6. Perch 2.0 (arXiv
2508.04665) is state of the art on BirdSet and BEANS linear probing, and — the
reason it is here — its own paper validates on the Weldy **call-type** dataset.
Call-type recognition is something it was selected for.

## Three preflight findings that reframed the question

Measured on the committed caches before any comparison. `run.py --preflight`
asserts all three and aborts if a future rebuild changes them.

1. **On the crow-tools corpus the 3072-d feature is 1024 real dimensions.** For
   all 2,494 cached rows the std block is exactly zero and the max block is
   bit-identical to the mean. `build_dataset.py` pools one 3 s window per label,
   and `pooling.pool` on a single vector returns `[mean, 0, mean]`. So "mean+std+max
   pooling destroys sequence structure" is true of the *deployed* path — where
   `group_regions` fuses several windows — and **vacuous on the training corpus**.
   That splits the pooling worry in two rather than answering it.

2. **The shipped `flight call: 0.975` is measured on a feature that identifies
   the source of every positive.** crow-tools has no flight-call flag at all, so
   all 40 flight-call positives live in the archive cache — and 155/160 of its rows
   have non-zero std against 0/2494 crow-tools rows. In the combined set the std
   block is a near-perfect corpus indicator with every flight-call positive on
   one side of it. `train_american_crow.py` says the feature "partly encodes
   source". It entirely does. **So the incumbent to beat is experiment 0012, not
   `models/american-crow/metrics.json`.**

3. **Every crow-tools span is exactly 1 second** (3,162 of 3,162). `FUTURE.txt`'s
   duration-quantile probe has no duration variable, so it is dropped rather
   than deferred — see *What was not run*.

## Method

2,339 labelled segments over 1,098 recordings (down from the cache's 2,494/1,195
— 97 recordings have lost their audio). Every arm joined **by segment key**, not
by reconstructed corpus order.

`experiments/lib/probe.py` is logic-identical to
`pipelines/ingest/evaluate.one_vs_rest_auc`, and `reproduces()` proves it: the
run aborts unless it lands on 0012's `alarm 0.942 / begging 0.916 / call 0.961 /
song 0.913` on the committed cache. It does, to the decimal. Nothing downstream
is comparable until that passes.

Audio is decoded once into a 48 kHz, 9 s excerpt centred on each labelled
second, and every arm windows the same samples — so "Perch got more context" is
a claim about one argument and nothing else.

### The arms

| arm | input | isolates |
|---|---|---|
| **A** `birdnet-grid` | BirdNET 3 s at `3*(t//3)` | the incumbent. The anchor. |
| **B** `birdnet-centred` | BirdNET 3 s on the label | A vs B = grid jitter alone |
| **C** `perch-3s` | Perch 2.0, 3 s | the backbone at matched context |
| **D** `perch-1s`, `perch-5s` | the context ladder | what makes C mean anything |
| **G** `birdnet+perch` | concatenated 2560-d | replace, or add? |

## Results

Recording-grouped 5-fold. Macro-F1 over the four CORE classes; `mob vs alert` is
restricted to the 26 recordings carrying both, where recording identity provably
cannot be the answer, with the 5-seed spread beside it.

| arm | macro-F1 | mob vs alert | spread | rattle vs softSong |
|---|---|---|---|---|
| **A** birdnet-grid | 0.849 | 0.637 | [0.612, 0.637] | 0.901 |
| **B** birdnet-centred | 0.855 | **0.540** | [0.524, 0.540] | 0.858 |
| **D** perch-1s | 0.856 | **0.759** | [0.709, 0.759] | 0.866 |
| **C** perch-3s | 0.871 | 0.741 | [0.700, 0.741] | 0.900 |
| **C** perch-3s, noise pad | **0.878** | **0.760** | [0.703, 0.760] | 0.893 |
| **D** perch-5s | 0.831 | 0.725 | [0.685, 0.725] | 0.780 |
| **G** birdnet+perch | 0.858 | 0.736 | [0.711, 0.736] | 0.850 |

Per-class AUC moves little, as pre-registered — the CORE classes sit at 0.90–0.97
with about 0.04 of headroom, which is why they are not the primary metric. Best
arm (perch-3s noise pad) against the incumbent: alarm 0.953→0.957, begging
0.914→0.940, call 0.970→0.980, song 0.904→0.923.

### The context ladder settles it

**Perch at 1 s beats BirdNET at 3 s** — 0.856 against 0.849 on macro-F1, and
0.759 against 0.637 on `mob vs alert` with non-overlapping spreads. Perch had a
third of the audio. Whatever it is doing better, it is not "having more context".

And more context *hurts*: perch-5s (0.831) is the worst arm in the table,
below the incumbent. A 5 s window centred on a 1 s label reaches into
neighbouring calls, which is the same failure `REGION_GAP` was tuned against in
`analyzer/birdnet.py`. **3 s is close to right, and it is right for both models.**

### The window is a null, and slightly worse than null

Centring BirdNET's window on the label buys +0.006 macro-F1 and **costs 0.10 on
`mob vs alert`** (0.637 → 0.540, spreads separate) and 0.043 on the control.
Hypothesis (a) is dead. Two reasons it was bounded before it ran: `start%3==1`
already centres the label, so 795 of 2,339 segments are byte-identical between
the arms; and BirdNET's grid window keeps the *preceding* audio, which for a
call type defined partly by what came before it is not obviously worse.

This is the cheap fix that did not work, and it is worth as much as the one that
did — it means `build_dataset.window_for` should be left alone.

### Where the errors go (N3)

CORE multiclass, same rows and folds, against arm A:

| arm | both right | both wrong | fixes | breaks |
|---|---|---|---|---|
| birdnet-centred | 1790 | 169 | 82 | 69 |
| perch-3s | 1775 | 124 | **127** | 84 |
| perch-3s noise pad | 1775 | 116 | **135** | 84 |
| perch-1s | 1733 | 108 | 143 | 126 |
| birdnet+perch | 1798 | 164 | 87 | 61 |

perch-3s fixes 127 of BirdNET's errors and breaks 84 — a net gain, not a
reshuffle. Centring is a reshuffle (82 for 69), which is the same null the
headline table shows, seen per-row.

### Replace, do not add (G)

Concatenation was pre-registered so it could not be a post-hoc rescue. It scores
0.858, **below perch-3s alone at 0.871**. The 1024 BirdNET dimensions do not
carry anything the 1536 Perch ones lack; they dilute. The answer is replace.

### Fine repertoire recovery (N1) — nobody wins

Every crow-tools span carries an unused `cluster` id — 86 of them, finer than
CORE. Predicting cluster over the 41 with ≥20 segments across ≥5 recordings:

| arm | macro-F1 |
|---|---|
| birdnet-grid | 0.205 |
| birdnet-centred | 0.221 |
| **perch-1s** | **0.243** |
| perch-3s | 0.209 |
| perch-5s | 0.188 |

All bad. Pre-registered as a **one-sided** test — the ids are upstream-derived
with unrecorded provenance and may themselves have come from BirdNET embeddings,
so BirdNET losing here would be uninformative. Nobody wins, so it stays
uninformative. The honest reading: 41-way fine repertoire is not recoverable
from any of these frozen embeddings with a linear probe, and that is a fact
about the probe and the labels as much as about the backbones.

### The real ceiling is overlapping callers (N4)

Macro-F1 split by how many crows the reviewer heard:

| split | n | birdnet-grid | perch-3s | perch-3s noise pad |
|---|---|---|---|---|
| crowCount==1 | 1794 | 0.848 | 0.869 | **0.875** |
| crowCount>=2 | 536 | 0.775 | 0.747 | 0.750 |

**The entire Perch gain is on single-crow segments.** On segments with two or
more birds nothing helps and Perch is slightly worse. That is the segmentation
ceiling experiment 0016 measured from the other side, and it is the strongest
argument in this experiment for the *other* half of the `FUTURE.txt` entry —
Voxaboxen, which does per-event onset/duration for overlapping vocalizations.
A better backbone does not separate two crows calling over each other; a better
detector might.

## Against the pre-registered verdict

Thresholds fixed before the arms ran:

- **MIGRATE** — ≥0.03 macro-F1 **and** non-overlapping `mob vs alert` spreads,
  **sustained at perch-3s, not only at perch-5s**
- **NULL** — within ±0.02 macro-F1 and overlapping spreads
- **ADD** — G beats both parents

perch-3s clears the spread condition decisively (0.741 vs 0.637, no overlap) and
lands at **+0.022** macro-F1 — **short of the 0.03 bar**. The noise-pad variant
reaches +0.029, still short. **The bar was not cleared and has not been moved.**

What makes this a migrate case anyway is the thing the thresholds could not
anticipate: perch-1s beats birdnet-3s on both metrics with a third of the audio.
A rival that wins while starved is stronger evidence than a rival that wins by
0.03, and the ladder was built precisely to catch it.

**Caveat, stated rather than buried:** `mob vs alert` is n=91 over 26 recordings.
It is the metric with headroom and the metric with the least data. The spreads
separate across five seeds, but this deserves re-running when the field corpus
can contribute labels of its own.

## What was not run, and why

- **The duration-quantile probe** from `FUTURE.txt`. Every span is 1 s, so there
  is no duration variable. Deriving one means running the 12 dB segmenter inside
  each span, which imports 0016's finding that 49% of detected units vanish under
  9 dB of added noise — measured duration would substantially be a function of
  recording SNR. Dropped, not deferred.
- **Rerunning 0006's "does context separate"** per backbone. 0006 refuses below
  10 calls across 4 recordings per class; the field corpus holds 3 labelled calls
  with context. Four backbones would produce four refusals. `excerpts.py` and
  `probe.py` make it a small change when the corpus clears that bar.
- **BirdAVES.** See above — near the bottom on linear probing, and its 50 ms
  frames only pay off under a temporal head, which is a different experiment.
- **BEATs with attentive probing.** The review's largest effect was a *probing*
  change, not a model change. Worth its own experiment; it would have muddied
  this one.

## Two methods notes worth keeping

**An mp3 seeking bug nearly produced a confident wrong answer.** The first
excerpt cache used `ffmpeg -ss` *before* `-i`, which on mp3 fast-seeks to a frame
boundary. Validating arm A against the committed BirdNET cache caught it: 1,028
of 2,035 rows matched to 1e-4 and the rest sat at cosine 0.98, with **no pattern
in the labels or in `start%3`** — a random few-tens-of-milliseconds jitter over
half the corpus, in an experiment about temporal alignment. Fixed by decoding
each recording once from the start and slicing every segment out of it, which is
sample-exact and, at ~2.1 segments per recording, also faster. Any future arm
must go through `experiments/lib/excerpts.py` for this reason.

**Perch pads and peak-normalises, and neither could be controlled away.**
`perch-hoplite`'s `embed()` returns one 1536-d vector per 5 s window, already
pooled — the 5×3×1536 spatial grid the paper describes is not exposed, so the
planned time-masked pooling was impossible. Every short arm is therefore part
audio and part padding (perch-1s is 20% real). The noise-pad variant measures
what that costs: it *helps*, +0.007 macro-F1 over zero padding, so the short arms
are lower bounds on Perch and the ladder conclusion is conservative. Perch also
peak-normalises internally while every other arm is fed unnormalised audio,
because the deployed path does none and 0022 showed level moves BirdNET's
numbers. That is a difference between arms rather than a choice.

## What this changed

- **`FUTURE.txt`'s backbone entry is answered, and its candidate was wrong.**
  Perch 2.0, not BirdAVES. The entry's other half — Voxaboxen for overlapping
  callers — is now the *better*-supported half, because N4 shows every gain
  vanishing at crowCount≥2.
- **The window hypothesis is retired.** `build_dataset.window_for` stays as it
  is; centring the window is a small loss, not a free win. That is a change to
  what gets built next, by subtraction.
- **Pooling is not the problem it was assumed to be** — on the training corpus
  two thirds of the shipped feature is constant, so region pooling can only be
  investigated on the deployed path, which this experiment does not touch.
- **`models/american-crow/metrics.json` may no longer claim 0.975 for flight
  call** without saying it is measured across a corpus boundary that predicts the
  label.
- **A migration is justified but not started.** It is a real cost — five shipped
  heads retrained, a second venv and a subprocess in the inference path (BirdNET
  sets `CUDA_VISIBLE_DEVICES=""` at import, so the two can never share a
  process), and `analyzer/birdnet.py` restructured to embed regions after
  grouping instead of before. `analyzer/birdnet.py` now refuses to load a head
  whose feature width or backbone does not match, so that migration will fail
  loudly rather than at the 400th capture.

## Running it

```bash
cd experiments/0025-is-birdnet-the-bottleneck
../../pipelines/representation/.venv-birdnet/bin/python run.py --preflight --selfcheck
../../pipelines/representation/.venv-birdnet/bin/python run.py --build-cache   # ~4 GB, 8 min

cd ../../pipelines/representation
.venv-birdnet/bin/python embed_birdnet_window.py --align grid
.venv-birdnet/bin/python embed_birdnet_window.py --align centred
(cd perch && uv sync)                                             # its own venv, once
perch/.venv/bin/python embed_perch.py --seconds 3 --pad zero

cd ../../experiments/0025-is-birdnet-the-bottleneck
../../pipelines/representation/.venv-birdnet/bin/python run.py --score --probes
```

Follow a long stage from a second terminal:

```bash
make watch experiments/0025-is-birdnet-the-bottleneck
```

`results.json` and `probes.json` hold the numbers; the 4 GB excerpt cache lives
under `data/` and is gitignored, so the numbers are the durable part.
