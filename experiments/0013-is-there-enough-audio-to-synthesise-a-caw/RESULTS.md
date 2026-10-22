# 0013 — Is there enough audio to synthesise a caw?

## Overview

Before attempting "CrowGPT" — a generative model that produces new crow calls — the project needed to know whether the corpus actually contains enough crow to train on. The corpus is 40.8 hours of whole archive recordings, and the fraction that is a corvid actually vocalising had only ever been guessed at. This experiment ran BirdNET over every file and then cut the corvid-positive audio into discrete call units with an energy-burst detector. The answer: yes for the audio, no for the meaning. 61.6% of the corpus is corvid — 24.5 hours, roughly 65,000 call units at a median 0.376 seconds — which is comfortably enough for unconditional or species-conditioned synthesis, with zero human labelling. But call-type-conditioned synthesis ("say an alarm call") is blocked: the entire human ground truth of the project amounts to 67.7 seconds of call audio, and the species with the most audio have the weakest or no call-type classifiers to pseudo-label with.

## In depth

### Method

BirdNET runs about 40x realtime, so every recording was read rather than a sample: 2,675 files, 40.8 hours, none unreadable. Thresholds and the crow-name list were imported from `analyzer/birdnet.py` rather than restated, so the crow fraction is measured at the gate the pipeline actually uses (`CROW_MIN_CONF` 0.25, `CANDIDATE_MIN_CONF` 0.10, a 3-second grid). Call units are energy bursts in the 800–4000 Hz band from experiment 0004: contiguous runs more than N dB above the recording's own 20th percentile, merged across gaps under 80 ms, dropped under 60 ms. Because that definition hangs on one arbitrary dB number, every result was computed at 6, 8 and 12 dB.

### What the corpus is

| | files | hours |
|---|---|---|
| Archive corpus, 6 species | 2,675 | **40.8** |
| — of which lossless (PCM/FLAC) | | 14.3 |
| — of which mp3 | | 26.5 |
| Field captures, all | 101 | 0.49 |
| Field captures, **★ Keep** (real recordings) | 14 | **0.14** |

The field corpus is not a training set: 8.6 minutes of genuine field audio against 40.8 hours of archive corpus. Everything below is about the archive corpus. `data/bebe_baglione_crows` (1.4 GB) contributes nothing — it is the tabular half of a published dataset with no audio in it.

### How much of it is a corvid

| species | files | hours | corvid windows | corvid hours | files with none |
|---|---|---|---|---|---|
| Rook | 500 | 9.20 | 80% | **7.25** | 19 |
| Common Raven | 500 | 10.81 | 56% | 5.91 | 26 |
| Eurasian Jackdaw | 500 | 6.47 | 81% | 5.06 | 14 |
| Carrion Crow | 499 | 5.73 | 49% | 2.69 | 52 |
| Hooded Crow | 500 | 5.94 | 38% | 2.19 | 92 |
| American Crow | 176 | 2.65 | 54% | 1.39 | 12 |
| **total** | **2,675** | **40.8** | **61.6%** | **24.48** | 215 |

**61.6% of the grid is a corvid at the pipeline's own threshold — 24.5 hours**, far above the 10–20% a reasonable person would guess for field recordings. The reason is sampling bias in the good direction: archive recordings are deliberately of the target species, usually with the bird calling repeatedly. A further 2,747 windows sit in the 0.10–0.25 candidate band. 215 files contain no corvid at all, Hooded Crow worst at 92 of 500.

The corpus is not clean, though: 1,381 distinct non-corvid species were detected in the same recordings (Common Wood-Pigeon 371 detections, Egyptian Goose 236, House Sparrow 224, and so on), and 28% of the American Crow recordings independently list another species in the archive's own `also` metadata. A generator handed whole windows would learn wood-pigeon as readily as crow — the argument for training on units rather than windows.

### Call units — the number that decides it

| dB threshold | units in corvid windows | total | median | per window |
|---|---|---|---|---|
| 6 | 66,907 | 13.68 h | | 2.28 |
| **8** | **68,245** | **11.77 h** | **0.376 s** | **2.32** |
| 12 | 64,932 | 8.83 h | | 2.21 |

Roughly 65,000 discrete call units, 9–14 hours depending on threshold, at a median 0.376 s each (p10 0.104 s, p90 1.264 s), with 48% duty cycle inside corvid windows. The stability is the point: the count moves by a third while the threshold moves 2x, so ~65k units is a property of the corpus, not the threshold.

Bandwidth settles the encoding worry: 95%-energy rolloff sits at a median of 2,688 Hz, p99 11,500 Hz, and 96.8% of units roll off below 8 kHz. A generative model at 16 kHz throws away essentially nothing, and the 26.5 lossy mp3 hours are as usable as the lossless ones. The corpus does not need re-collecting at higher fidelity.

### Is the burst detector finding calls, or room tone?

The control that could have killed the experiment. Because BirdNET's own misses land in the negative class (a real alarm call at 0.183 confidence, a begging fledgling at 0.06), a binary control cannot answer it; instead, burst density and duty cycle were checked per BirdNET-confidence band:

| max crow conf | windows | 6 dB per win | 6 dB duty | 12 dB per win | 12 dB duty |
|---|---|---|---|---|---|
| 0.00–0.10 | 15,588 | 1.83 | 27% | **1.02** | **11%** |
| 0.10–0.25 | 2,747 | 2.31 | 42% | 1.84 | 24% |
| 0.25–0.50 | 4,051 | 2.25 | 47% | 1.98 | 28% |
| 0.50–0.75 | 5,600 | 2.21 | 51% | 2.08 | 33% |
| 0.75–1.00 | 19,727 | 2.30 | 59% | **2.29** | **39%** |

At 12 dB both density and duty cycle rise monotonically with BirdNET's confidence — 1.02→2.29 units per window and 11%→39% duty — two independent measures agreeing against a detector that knows nothing about energy thresholds. At 6 dB the density signal washes out entirely (1.83 vs 2.30): 6 dB is too permissive and would have produced a defensible-looking number that was mostly background. **12 dB is the threshold to use**, and the conservative 64,932 units / 8.83 h is the honest figure.

It is not clean: at 12 dB the lowest band still yields 1.02 units per window, so a meaningful minority of bursts are not crow. This detector is a usable bootstrap, not a call detector, and anything trained on its output inherits that contamination.

### What the human labels are worth

All 35 labels sit on the 3-second grid (checked; the run aborts if one does not). They are BirdNET windows, not call boundaries:

| | |
|---|---|
| labels | 35 |
| total label span | 216.0 s |
| call units inside them | 220 |
| median units per label | **3.0** (max 41) |
| labels isolating exactly one call | **5** |
| labels containing several | 25 |
| labels containing none detected | 5 |
| **actual call audio inside every human label** | **67.7 s** |

The entire human ground truth of this project is 67.7 seconds of call audio, and only 5 of the 35 labels pin down a single call. As a training target for a classifier that is fine; as a target for a synthesiser it is nearly useless, because "generate this" needs to point at one call.

### The answer

- **Unconditional or species-conditioned caw synthesis: possible now.** 24.5 hours and ~65,000 units, with zero human labelling, is inside the regime where fine-tuning a pretrained audio generative model works. Species conditioning is free and trustworthy, because BirdNET's species ID selected the windows in the first place.
- **Call-type-conditioned synthesis is not**, and the reason is structural: the audio and the ability to label it are anti-correlated across species.

| species | units available | call-type head |
|---|---|---|
| Rook | 19,493 | AUC 0.478–0.757 (weak) |
| Eurasian Jackdaw | 17,461 | **no head at all** |
| Common Raven | 15,271 | AUC 0.579–0.809 (weak) |
| Carrion Crow | 6,243 | AUC 0.626–0.765 (weak) |
| Hooded Crow | 5,453 | AUC 0.836–0.948 |
| **American Crow** | **4,324** | **AUC 0.904–0.975 (strong)** |

The one head good enough to pseudo-label with sits on 4,324 units — 6% of the pool. Conditioning on call type would mean either training on 6% of the data or accepting labels from a 0.48-AUC head, which is a coin flip wearing a class name. What this takes is not collection but two labelling jobs: tight call boundaries (or an accepted convention that the 12 dB detector supplies them), and call-type ground truth for species other than American Crow.

### What changed

No code — a feasibility measurement whose output is four numbers that were previously guesses: 61.6% corvid (24.5 hours, against a working assumption of 10–20%); ~65,000 call units at a median 0.376 s; 16 kHz is enough and the lossy corpus is fine; and 67.7 seconds of total human ground truth. One decision recorded: **CrowGPT goes in `FUTURE.txt`, not `TODO.txt`** — it has a shape and a data budget, but is gated on call-type labels for the deep-pool species. The 12 dB threshold is worth keeping; anything reusing this segmentation should start from 12.

### Amendment, 2026-08-06 — the file counts were inflated; the answer is not

Found while reconciling the two corpus stores. `corpus_files()` appended every downloaded row in `corvid.db` to `american-crow` whatever bird it was — correct while the corpus held only American Crow, wrong after a 2026-08-05 sweep put 48 species in that database and 13,311 recovered archive rows joined them the next day. It also counted the 2,382 recordings held in both stores twice.

| | old | corrected |
|---|---|---|
| slugs | 6 | 61 |
| files under `american-crow` | **38,282** | **13,785** |
| total files | 40,681 | 27,370 |

The American Crow figure was overstated 2.78x. **The conclusion does not change**: the headline is a rate — the fraction of a recording that is a corvid, and the seconds of call unit surviving the gate — measured per file and summed. Mislabelling a file's species does not alter the rate, and the duplicates are byte-identical, so they contributed the same measurement twice rather than a wrong one. The 12.75 hours of bouts that trained the model was extracted by `crowgpt/extract`, which reads `crowgpt.corpus` and never the inflated function. What it does mean: any per-species number read off this run is wrong, and the `american-crow` row is the one to distrust. `corpus_files()` now files each row under its own `slug` and skips paths already counted from the manifest.

### Re-running

`../../pipelines/representation/.venv-birdnet/bin/python run.py` — reads all 2,675 files with 12 workers in about 7 minutes; progress printed as it goes, results to `results.json`. Needs `ffprobe`, and `DATA_DIR` if the corpus is not at `data/`. `SAMPLE_PER_SPECIES=6` gives a fast check, but the crow fraction runs high on a small sample because the first files per species are the well-rated ones.
