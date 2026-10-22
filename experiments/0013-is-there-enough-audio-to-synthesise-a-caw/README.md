# 0013 — Is there enough audio to synthesise a caw?

## The question

"CrowGPT": calls in, a model that generates new ones out. The blocker looks
obvious — there are **35 human labels** on the field server, all American Crow,
across 7 captures — and on that basis the idea is dead on arrival.

That blocker is imaginary. A generative audio model does not need labels; it
needs audio. Labels only enter if you want to *ask* for a call type, and the
thing that would supply them is the per-species head that already ships. So the
question is not how many labels exist. It is:

**How many seconds of actual crow, cut into discrete call units, can be
recovered from the corpus without asking a human for anything?**

`data/species` is 11 GB, which sounds like plenty. But it is whole archive
recordings — wind, other species, recordists talking — and the fraction that is
a corvid vocalising has never been measured, only guessed at. Everything
downstream depends on that one number, and this is the measurement of it.

## Method

BirdNET runs about 40x realtime, so this reads **every** recording rather than a
sample: 2,675 files, 40.8 hours, none unreadable. Thresholds and the crow-name
list are imported from `analyzer/birdnet.py` rather than restated, so the crow
fraction is measured at the gate the pipeline actually uses (`CROW_MIN_CONF`
0.25, `CANDIDATE_MIN_CONF` 0.10, a 3-second grid).

Call units are energy bursts in the 800–4000 Hz band experiment 0004 used for
call SNR: contiguous runs more than *N* dB above the recording's own 20th
percentile, merged across gaps under 80 ms so one caw is not counted three times,
and dropped under 60 ms. Because that whole definition hangs on one arbitrary dB
number, every result is computed at 6, 8 and 12 dB.

Section E is the check that decides whether any of D is real, and it is the
reason to read this experiment sceptically before believing it.

## A. What the corpus actually is

| | files | hours |
|---|---|---|
| Archive corpus, 6 species | 2,675 | **40.8** |
| — of which lossless (PCM/FLAC) | | 14.3 |
| — of which mp3 | | 26.5 |
| Field captures, all | 101 | 0.49 |
| Field captures, **★ Keep** (real recordings) | 14 | **0.14** |

The field corpus is not a training set and this is the scale of why: 8.6 minutes
of genuine field audio against 40.8 hours of archive corpus. Everything below is the
corpus. `data/bebe_baglione_crows` is 1.4 GB and contributes **nothing** — it is
20 CSVs and some SVGs, the tabular half of a published dataset, with no audio in
it at all.

## B. How much of it is a corvid

| species | files | hours | corvid windows | corvid hours | files with none |
|---|---|---|---|---|---|
| Rook | 500 | 9.20 | 80% | **7.25** | 19 |
| Common Raven | 500 | 10.81 | 56% | 5.91 | 26 |
| Eurasian Jackdaw | 500 | 6.47 | 81% | 5.06 | 14 |
| Carrion Crow | 499 | 5.73 | 49% | 2.69 | 52 |
| Hooded Crow | 500 | 5.94 | 38% | 2.19 | 92 |
| American Crow | 176 | 2.65 | 54% | 1.39 | 12 |
| **total** | **2,675** | **40.8** | **61.6%** | **24.48** | 215 |

**61.6% of the grid is a corvid at the pipeline's own threshold — 24.5 hours.**
That is the finding that reframes the whole question, and it is far above the
10–20% a reasonable person would guess for field recordings. The reason is
sampling bias in the good direction: archive recordings are *deliberately* of
the target species, usually with the bird calling repeatedly, so the corpus is
much denser in crow than an equivalent number of hours from a fixed microphone
would be. A further 2,747 windows sit in the 0.10–0.25 candidate band.

215 files contain no corvid at all, Hooded Crow worst at 92 of 500.

## C. What else is in there

**1,381 distinct non-corvid species** were detected across the same recordings.

| | detections |
|---|---|
| Common Wood-Pigeon | 371 |
| Egyptian Goose | 236 |
| House Sparrow | 224 |
| Eurasian Blackbird | 163 |
| Great Spotted Woodpecker | 162 |
| Eurasian Jay | 159 |

The archive's own metadata agrees independently of BirdNET: 28% of the American
Crow recordings list another species in their `also` field. So a generator handed
whole corvid-positive windows would learn wood-pigeon as readily as crow. This is
the argument for training on *units* (D) rather than on windows, and it does not
go away entirely even then.

## D. Call units — the number that decides it

| dB threshold | units in corvid windows | total | median | per window |
|---|---|---|---|---|
| 6 | 66,907 | 13.68 h | | 2.28 |
| **8** | **68,245** | **11.77 h** | **0.376 s** | **2.32** |
| 12 | 64,932 | 8.83 h | | 2.21 |

**Roughly 65,000 discrete call units, 9–14 hours of them depending where the
threshold sits, at a median of 0.376 s each** (p10 0.104 s, p90 1.264 s). Duty
cycle inside corvid windows is 48%.

The stability is the point. A number that moved 10x across a plausible threshold
range would be an artefact of the threshold; this one moves by a third while the
threshold moves 2x, so ~65k units is a property of the corpus.

### Bandwidth, which settles the encoding worry

Rolloff (95% of unit energy) sits at a median of **2,688 Hz**, p99 11,500 Hz, and
**96.8% of units roll off below 8 kHz**. So a generative model at 16 kHz throws
away essentially nothing, and the 26.5 lossy hours are as usable as the 14.3
lossless ones — an mp3 lowpass at 15–16 kHz is far above anything a corvid puts
into the air. The corpus does not need re-collecting at higher fidelity.

## E. Is the burst detector finding calls, or room tone?

This is the section that could have killed the experiment, and nearly did. If
bursts appear as often in silence as in a corvid window, D counts noise.

One binary control cannot answer it, because BirdNET's own misses land in the
negative class — `birdnet.py` records a real alarm call at 0.183 and a begging
fledgling at 0.06, so "no detection" windows genuinely contain calls. So the
control is a gradient: density and duty cycle per confidence band.

| max crow conf | windows | 6 dB per win | 6 dB duty | 12 dB per win | 12 dB duty |
|---|---|---|---|---|---|
| 0.00–0.10 | 15,588 | 1.83 | 27% | **1.02** | **11%** |
| 0.10–0.25 | 2,747 | 2.31 | 42% | 1.84 | 24% |
| 0.25–0.50 | 4,051 | 2.25 | 47% | 1.98 | 28% |
| 0.50–0.75 | 5,600 | 2.21 | 51% | 2.08 | 33% |
| 0.75–1.00 | 19,727 | 2.30 | 59% | **2.29** | **39%** |

**At 12 dB both density and duty cycle rise monotonically with BirdNET's
confidence** — 1.02→2.29 units per window and 11%→39% duty, across five bands
that were never shown to each other. Two independent measures agreeing in the
same direction, against a detector that knows nothing about energy thresholds, is
what a passing control looks like.

At 6 dB the density signal washes out entirely (1.83 vs 2.30 — flat) while duty
cycle still separates. That is the sweep earning its place: **6 dB is too
permissive and would have produced a defensible-looking number that was mostly
background.** 12 dB is the threshold to use, and the conservative 64,932 / 8.83 h
is the honest figure to quote.

It is not clean. At 12 dB the lowest band still yields 1.02 units per window, so
a meaningful minority of bursts are not crow, and the strict "empty" control
(1.24 units/window against 2.32) is under 2x. **This detector is a usable
bootstrap, not a call detector**, and anything trained on its output inherits
that contamination.

## F. What the human labels are actually worth

All 35 labels sit on the 3-second grid — checked, not assumed; the run aborts if
one does not. They are BirdNET *windows*, not call boundaries, and the gap
between those two things is the whole problem for synthesis:

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

**The entire human ground truth of this project is 67.7 seconds of call audio**,
and only 5 of the 35 labels pin down a single call. A label reading `alarm call`
over 0–12 s of capture 100 covers 41 detected units. As a training target for a
classifier that is fine — it is what the head already learns from. As a target
for a synthesiser it is nearly useless, because "generate this" needs to point at
one call.

## The answer

**Yes for the audio, no for the meaning — and the reason is the opposite of what
it looks like.**

The corpus is not the constraint. 24.5 hours of corvid-positive audio and ~65,000
discrete call units at a median 0.376 s, obtained with **zero** human labelling,
is comfortably inside the regime where fine-tuning a pretrained audio generative
model works, and arguably enough to train a small unconditional model on 0.4 s
units from scratch. Encoding, sample rate and bandwidth are all non-issues.

So:

- **Unconditional or species-conditioned caw synthesis: possible now.** Species
  conditioning is free and trustworthy, because BirdNET's species ID is the thing
  that selected the windows in the first place.
- **Call-type-conditioned synthesis — "say an alarm call" — is not.** Not from
  human labels: 67.7 seconds, 5 isolated calls. It would have to come from
  pseudo-labels, and there the corpus has a structural problem that no amount of
  new audio fixes.

**The audio and the ability to label it are anti-correlated across species.**

| species | units available | call-type head |
|---|---|---|
| Rook | 19,493 | AUC 0.478–0.757 (weak) |
| Eurasian Jackdaw | 17,461 | **no head at all** |
| Common Raven | 15,271 | AUC 0.579–0.809 (weak) |
| Carrion Crow | 6,243 | AUC 0.626–0.765 (weak) |
| Hooded Crow | 5,453 | AUC 0.836–0.948 |
| **American Crow** | **4,324** | **AUC 0.904–0.975 (strong)** |

The one head good enough to pseudo-label with sits on 4,324 units — 6% of the
pool. The three deepest pools have heads that are weak or, for Jackdaw's 17,461
units, entirely absent. Conditioning on call type would mean either training on
6% of the data or accepting labels from a 0.48-AUC head, which is a coin flip
wearing a class name.

What this would take is therefore **not collection**. It is two labelling jobs:
tight call boundaries (or an accepted convention that the 12 dB burst detector
supplies them), and call-type ground truth for species other than American Crow.

## What changed

No code. This is a feasibility measurement, and its output is four numbers that
were previously guesses:

- **61.6% of the corpus is corvid — 24.5 hours.** The working assumption in
  conversation had been 10–20%, i.e. 4–8 hours, which is the difference between
  "too thin to try" and "enough". Nothing had measured it.
- **~65,000 call units at a median 0.376 s**, stable across a 2x threshold sweep.
  This is the quantity a generative model consumes and it now has a value.
- **16 kHz is enough and the lossy corpus is fine** (96.8% of units under 8 kHz).
  Kills any argument for re-fetching at higher fidelity for this purpose.
- **67.7 seconds.** The total human ground truth in the project, stated as call
  audio rather than as "35 labels", which flatters it.

And one decision recorded: **CrowGPT goes in `FUTURE.txt`, not `TODO.txt`** — it
has a shape and a data budget now, but it is gated on call-type labels for the
deep-pool species rather than on anything buildable this week.

The 12 dB threshold is also worth keeping. A burst detector at 6 dB looks fine in
isolation and is mostly background; anything reusing this segmentation should
start from 12.

## Re-running

```bash
../../pipelines/representation/.venv-birdnet/bin/python run.py
```

Reads all 2,675 files with 12 workers in about 7 minutes; progress is
printed as it goes and results land in `results.json`. Set
`SAMPLE_PER_SPECIES=6` for a fast check — note the crow fraction runs high on a
small sample, because the first files per species are the well-rated ones.

Needs `ffprobe`, and `DATA_DIR` if the corpus is not at `data/`.

---

## Amendment, 2026-08-06 — the file counts were inflated; the answer is not

Found while reconciling the two corpus stores, not by re-running this.

`corpus_files()` read the manifest tree per species and then appended **every**
downloaded row in `corvid.db` to `american-crow`, whatever bird it was. That was
correct while the corpus held only American Crow. It stopped being correct on
2026-08-05, when a sweep put 48 species in that database, and it got worse the
next day when 13,311 recovered archive rows joined them. It also counted the
2,382 recordings held in **both** stores twice.

With the corpus as it stands today, the old code reports:

| | old | corrected |
|---|---|---|
| slugs | 6 | 61 |
| files under `american-crow` | **38,282** | **13,785** |
| total files | 40,681 | 27,370 |

So the American Crow figure was overstated **2.78x**, by other species wearing
its name and by duplicates counted twice.

**What this does not change: the conclusion.** The headline of this experiment
is a *rate* — the fraction of a recording that is a corvid vocalising, and the
seconds of call unit that survive the gate — measured per file and then summed.
Mislabelling which species a file belongs to does not alter the rate, and the
duplicates are byte-identical, so they contributed the same measurement twice
rather than a wrong one. The 12.75 hours of bouts that 0013 reported was
extracted by `crowgpt/extract`, which reads `crowgpt.corpus` and not this
function, so the corpus that trained the model was never the inflated one.

What it does mean is that any *per-species* number read off this run is wrong,
and the `american-crow` row is the one to distrust.

`corpus_files()` now files each row under its own `slug` — the column the
reconciliation added, resolved once by the corpus tooling's taxonomy — and skips a
path already counted from the manifest.
