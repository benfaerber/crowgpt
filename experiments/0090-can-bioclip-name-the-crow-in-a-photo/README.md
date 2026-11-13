# 0090 — Can BioCLIP name the crow in a photo?

**Question.** Could an in-house model name the corvid species in a photo, instead
of calling an outside API? Specifically: is BioCLIP 2 (an open CLIP model trained
on the Tree of Life), used zero-shot, good enough? If it isn't, does a small head
trained on its embeddings fix it? And would more training photos (iNaturalist)
be worth bringing in?

## Data

Macaulay Library photos, 480px, imported with `make photos` from the CSV exports
in `data/photos/macaulay-exports/`. The sample is a seeded random 400 photo rows
per export, so it can be reproduced.

| species | n | source |
|---|---|---|
| American Crow | 1649 | saved search page, not CSV (see caveats) |
| Common Raven, Fish Crow, Black-billed Magpie, Carrion Crow, Hooded Crow, Rook, Eurasian Jackdaw | 400 each | CSV |
| Chihuahuan Raven | 399 | CSV |

The labels are the uploader's identification on Macaulay, which is not
independently verified.

## Method

`run.py` embeds every photo once with `hf-hub:imageomics/bioclip-2` on CPU
(about 8 minutes per 1,600 photos on 32 cores), caching the embeddings in
`data/photos/embeddings/`. It scores against three candidate lists:

- **utah**: American Crow, Common Raven, Black-billed Magpie. The question a
  photo from home actually poses.
- **north-america**: the Utah list plus Fish Crow and Chihuahuan Raven. These
  are the two near-identical partners.
- **all**: 11 corvids. Two of them, Large-billed Crow and House Crow, are decoys
  with no photos.

Zero-shot averages three text prompts per species (scientific name, common
name, and both together). The trained head is a balanced logistic regression on
the frozen image embeddings, scored by 5-fold cross-validation. The learning
curve re-trains that head on 50 to 320 photos per species.

## Results

Top-1 accuracy per species:

| species | zero-shot utah | head utah | zero-shot N.Am. | head N.Am. | zero-shot all | head all |
|---|---|---|---|---|---|---|
| American Crow | 81.0% | **94.8%** | 43.5% | **79.9%** | 36.9% | **68.4%** |
| Common Raven | **95.0%** | 88.8% | **76.8%** | 71.2% | **72.2%** | 68.5% |
| Black-billed Magpie | 99.8% | 99.0% | 99.8% | 99.2% | 99.5% | 99.0% |
| Fish Crow | | | **85.0%** | 72.2% | **78.0%** | 70.0% |
| Chihuahuan Raven | | | **70.4%** | 66.4% | **68.4%** | 65.9% |
| Carrion Crow | | | | | 57.8% | **72.8%** |
| Hooded Crow | | | | | 93.2% | 92.5% |
| Rook | | | | | 81.5% | 82.5% |
| Eurasian Jackdaw | | | | | **95.0%** | 92.8% |

Learning curve for the head (balanced accuracy):

| photos per species | utah | north-america | all |
|---|---|---|---|
| 50 | 93.7% | 73.5% | 76.3% |
| 100 | 93.6% | 75.7% | 77.9% |
| 200 | 94.0% | 76.9% | 78.3% |
| 320 | 94.1% | 77.2% | 78.8% |

## What it says

- **Zero-shot is lopsided rather than blind.** In the Utah set it calls 18% of
  American Crows "Common Raven" while getting 95% of the ravens. With Fish Crow
  as a candidate, it sends 43% of American Crows there. Its text side has a
  prior toward some species names, and the head mostly removes that.
- **For the Utah question, the head reaches about 94% balanced accuracy.**
  Magpies are solved by either method. Crow vs. raven is where the remaining
  errors are.
- **The look-alike pairs stay at 66–80% either way.** American vs. Fish Crow and
  Common vs. Chihuahuan Raven are what field guides say: by eye, the two are
  told apart by voice and range, not plumage.
- **More photos won't move a frozen-embedding head.** The curve gains about one
  point from 50 to 320 photos per species. iNaturalist's extra volume would buy
  roughly nothing for this approach. What could help is a different approach:
  fine-tuning the backbone, cropping the bird out of a larger original so small
  birds keep their bill shape, or a range prior from where the photo was taken.

## Caveats

- **American Crow came from a saved search page, not a CSV.** It is whatever the
  default search order put first, likely the higher-rated photos, while every
  other species is a random sample. Its numbers may be flattering. Swap in a CSV
  export and rerun before quoting them.
- These are curated archive photos. A field photo of a distant bird on a wire is
  harder, and no number here measures that.
- The labels are the uploaders' calls, so some disagreements may be the label's
  fault, not the model's, especially in the look-alike pairs.

## What it changed

- **Decided not to add iNaturalist for now.** The learning curve is flat, so
  more photos of the same kind would not justify a third source.
- An in-house crow / raven / magpie classifier is viable at about 94% on
  archive photos: BioCLIP 2 embeddings plus a logistic head, CPU only, no
  outside API.
- Photo ID is not the answer to the look-alike pairs. That confirms audio, plus
  location, as the project's tool for them.
- Built `make photos` and `tools/import_ml_photos.py`, so the photo set can be
  rebuilt from the saved CSVs alone.
