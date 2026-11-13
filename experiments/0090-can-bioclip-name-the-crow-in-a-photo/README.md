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

| species | n |
|---|---|
| American Crow, Common Raven, Fish Crow, Black-billed Magpie, Carrion Crow, Hooded Crow, Rook, Eurasian Jackdaw | 400 each |
| Chihuahuan Raven | 399 |

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
| American Crow | 81.8% | **92.8%** | 46.8% | **78.2%** | 39.8% | **63.0%** |
| Common Raven | **95.0%** | 88.8% | **76.8%** | 70.8% | **72.2%** | 68.0% |
| Black-billed Magpie | 99.8% | 99.0% | 99.8% | 99.2% | 99.5% | 99.0% |
| Fish Crow | | | **85.0%** | 72.0% | **78.0%** | 67.8% |
| Chihuahuan Raven | | | **70.4%** | 65.4% | **68.4%** | 64.9% |
| Carrion Crow | | | | | 57.8% | **71.8%** |
| Hooded Crow | | | | | 93.2% | 92.2% |
| Rook | | | | | 81.5% | 82.2% |
| Eurasian Jackdaw | | | | | **95.0%** | 93.2% |

Learning curve for the head (balanced accuracy):

| photos per species | utah | north-america | all |
|---|---|---|---|
| 50 | 93.1% | 72.9% | 76.3% |
| 100 | 93.3% | 74.9% | 76.7% |
| 200 | 93.7% | 76.6% | 77.5% |
| 320 | 93.5% | 77.1% | 78.0% |

## What it says

- **Zero-shot is lopsided rather than blind.** In the Utah set it calls 18% of
  American Crows "Common Raven" while getting 95% of the ravens. With Fish Crow
  as a candidate, it sends 38% of American Crows there. Its text side has a
  prior toward some species names, and the head mostly removes that.
- **For the Utah question, the head reaches about 93.5% balanced accuracy.**
  Magpies are solved by either method. Crow vs. raven is where the remaining
  errors are.
- **The look-alike pairs stay at 65–85% either way.** American vs. Fish Crow and
  Common vs. Chihuahuan Raven are what field guides say: by eye, the two are
  told apart by voice and range, not plumage.
- **More photos won't move a frozen-embedding head.** The curve gains half a point to four
  points from 50 to 320 photos per species, and is flattening. iNaturalist's extra volume would buy
  roughly nothing for this approach. What could help is a different approach:
  fine-tuning the backbone, cropping the bird out of a larger original so small
  birds keep their bill shape, or a range prior from where the photo was taken.

## Caveats

- An earlier run used 1,649 American Crow photos from a saved search page
  (the search's first results, not a random sample). The head scored 94.8% on
  those against 92.8% on the random CSV sample here, so the saved-page set
  was slightly flattering, as suspected.
- These are curated archive photos. A field photo of a distant bird on a wire is
  harder, and no number here measures that.
- The labels are the uploaders' calls, so some disagreements may be the label's
  fault, not the model's, especially in the look-alike pairs.

## What it changed

- **Decided not to add iNaturalist for now.** The learning curve is flat, so
  more photos of the same kind would not justify a third source.
- An in-house crow / raven / magpie classifier is viable at about 93.5% on
  archive photos: BioCLIP 2 embeddings plus a logistic head, CPU only, no
  outside API.
- Photo ID is not the answer to the look-alike pairs. That confirms audio, plus
  location, as the project's tool for them.
- Built `make photos` and `tools/import_ml_photos.py`, so the photo set can be
  rebuilt from the saved CSVs alone.
