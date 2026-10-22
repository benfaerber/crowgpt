# Ingest — the American Crow label corpus

The human-reviewed American Crow labels originally came from the
[crow-tools](https://github.com/CrowCall/crow-tools) fork. **That fork is
abandonware and is no longer required.**

## The migration off it

What Cawtalker took from crow-tools splits in two, and the halves have opposite
properties:

- **The audio is replaceable.** Every labelled recording sits in a public
  catalogue, and the private corpus tooling fetches it by id against the
  committed labels.
- **The labels are not.** 3,162 hand-reviewed segments over 1,549 recordings —
  an order of magnitude more human ground truth than the field server holds, and
  the product of somebody sitting and listening. It cannot be re-derived, and it
  is the reason alarm call scores 0.97 here instead of 0.65.

  It is also **not our work**: MIT, © 2025 OpenShot Studios LLC, owlmaddie LLC.
  Their licence travels with the data in `crowtools/LICENSE.md`.

So the labels were lifted into `crowtools/labels.json`, which is **committed**;
a megabyte of JSON in git is a fair price for the one artifact here that cannot
be re-fetched. The audio is re-downloaded into `data/` with everything else.

```bash
python pipelines/ingest/import_crowtools.py --plan   # report, write nothing
python pipelines/ingest/import_crowtools.py          # write crowtools/labels.json
make corpus                                          # what is on disk
```

**Both steps are done, and the fork is deleted.** `corpus.py` reads the committed
labels and the audio in `data/species/american-crow/audio`, and knows nothing
about forks — 2,495 segments carry a CORE label, 2,339 of them have their audio
on disk. A checkout with the download not yet run reports that honestly rather
than failing.

## The one script that still knows about the fork

`import_crowtools.py`, and only for `gather()` — re-importing the labels if
upstream ever changes. Resolution order is
`--fork`, `$CROW_TOOLS_DIR`, the same key in `.env`, a sibling of this checkout,
then `~/Code/crow-tools`.

A path you name by hand is checked and **not** fallen back on. A typo'd
`CROW_TOOLS_DIR` stops the run rather than quietly finding some other fork under
`~/Code` and re-importing a corpus you did not choose. That is pinned by
`fieldserver/tests/test_import_crowtools_fork.py`.

## Why it is worth the megabyte

Commit `59f1ce1` showed that even with multi-label recovery, our weak archive data
leaves **alarm** stuck at the label ceiling. This curated set breaks that ceiling:

| CORE class | old single-label n | reviewed segments |
|------------|--------------------|---------------------|
| alarm call | 10 | **1,283** |
| song | 11 | **606** |
| call | 71 | 543 |
| begging | 4 | **307** |
| flight call | 25 | — (no flight flag upstream) |

Begging is the mirror image of flight call: it barely exists in the archive set (4
recordings) and lives almost entirely here. It used to be dropped on this side
and folded into `call` on the field-server side — it is now its own CORE class
on both.

## Get the audio

The private corpus tooling fetches exactly the 1,549 recordings the labels
name, into `data/species/american-crow/audio`. Labels present and audio absent
is a normal half-finished state, and it is what `make corpus` reports as
segments with no audio.

## Build Phase 4 features

`build_dataset.py` reads those labelled segments and emits the **same schema as
`training/recover_and_pool.py`** — `X` (3072-dim `pooling.pool`, mean+std+max)
and `Y` (object array of CORE label lists) — reusing the shared `pooling.py` so
the feature definition never drifts.

```bash
cd pipelines/ingest
../representation/.venv-birdnet/bin/python build_dataset.py --dataset all-public
# -> results/pooled_embeddings_crowtools_all-public.npz
```

Label mapping (aligned with `recover_and_pool.canon_token`): `mob`/`alert`/
`scold` → **alarm call**, `softSong` → **song**, `rattle` → **call**, `begging`
→ **begging**; `grief` (3 segments) falls outside CORE and is dropped.

**Localisation caveat:** these labels are per-second, so each feature pools the
single 3s BirdNET window covering the call (the std block ≈ 0). The archive
set pools whole clips, so its std/max blocks carry real spread. Train on this set
alone for the alarm/song lift, or account for that domain gap when concatenating
the two caches.

## Combine with the archive set (optional)

```python
import numpy as np
xc = np.load("../training/results/pooled_embeddings.npz", allow_pickle=True)
ct = np.load("results/pooled_embeddings_crowtools_all-public.npz", allow_pickle=True)
X = np.concatenate([xc["X"], ct["X"]])
Y = np.array([list(s) for s in list(xc["Y"]) + list(ct["Y"])], dtype=object)
np.savez("../training/results/pooled_combined.npz", X=X, Y=Y)
```

Then evaluate/train Phase 4 against the chosen cache.

## Files

- `corpus.py` — reads the committed labels + local audio, maps flags → CORE. Pure stdlib.
- `import_crowtools.py` — re-imports the labels from a fork.
- `build_dataset.py` — pools BirdNET windows into Phase-4 features (BirdNET venv).
