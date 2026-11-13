# 0091 — Does location settle the look-alike corvids?

**Question.** 0090 left the look-alike species near 70% from pixels alone and
found that more photos would not help. Does knowing where the photo was taken
close the gap, using only data already in `data/photos`?

## Method

All nine species in `data/photos`, 400 photos each (399 for Chihuahuan Raven),
every one from a Macaulay CSV export and so carrying coordinates.

- **Image term.** 0090's logistic head on cached BioCLIP 2 embeddings, 5-fold
  cross-validated probabilities.
- **Location term.** Every located row in an export (photo, audio or video,
  about 10,000 per species, 6,589 for Chihuahuan Raven) is a point where that
  species was documented. A photo's likelihood for a species is the smoothed
  share of that species' records within a radius of the photo. Records by the
  photo's own recordist are excluded, so their other uploads from the same
  outing cannot vouch for it.
- **Record rate (one variant).** The exports are capped at 10,000 rows, so the
  location term alone treats all species as equally common. The variant
  multiplies in how fast each species is documented, measured from the newer
  half of its export: American Crow 98 records a day, Common Raven 89,
  Chihuahuan Raven 2, the rest 14 to 26.

## Results

Top-1 per species, nine candidates, 150 km radius:

| species | image alone | location alone | image x location | x record rate |
|---|---|---|---|---|
| American Crow | 63.0% | 38.0% | 71.8% | **88.5%** |
| Black-billed Magpie | 99.0% | 97.0% | 100.0% | 99.5% |
| Carrion Crow | 71.8% | 73.0% | 94.0% | 92.8% |
| Chihuahuan Raven | 64.9% | 97.0% | **99.2%** | 45.4% |
| Common Raven | 68.0% | 21.8% | 74.5% | **85.8%** |
| Eurasian Jackdaw | 93.2% | 31.0% | 96.0% | 95.5% |
| Fish Crow | 68.0% | 88.8% | **89.2%** | 59.8% |
| Hooded Crow | 92.2% | 75.2% | 97.5% | 97.0% |
| Rook | 82.2% | 36.2% | 89.0% | 83.5% |
| **balanced accuracy** | 78.0% | 62.0% | **90.1%** | 83.1% |

Image x location by radius: 89.5% at 50 km, 90.1% at 150 km, 89.8% at 500 km.
The radius barely matters.

## What it says

- **Location and pixels fail on different photos.** Neither is good alone
  (78% and 62%); together they reach 90%. Location removes the
  cross-continent confusions (American Crow called Carrion Crow) that pixels
  cannot.
- **The species with a small range are settled.** Chihuahuan Raven goes from
  65% to 99% and Fish Crow from 68% to 89%.
- **The two widespread species are left behind**: American Crow at 72% and
  Common Raven at 75%. Their records are spread across a continent or more, so
  the location term underrates them wherever a local species is also present.
  79 American Crows are still called Fish Crow, because the Fish Crow's range
  lies inside the American Crow's and location cannot rule either out there.
- **The record-rate correction is a trade, not a fix.** It lifts American Crow
  to 89% and Common Raven to 86%, and drops Fish Crow to 60% and Chihuahuan
  Raven to 45%. Where a look-alike pair overlaps, neither pixels nor location
  decide, and a prior only picks which one to get wrong. Those zones are a job
  for audio.

## Caveats

- The test set is balanced at 400 per species. Real photos are not: in most of
  North America an unknown black crow is far more often American than Fish.
  That is why the record-rate variant looks worse here than it would in use,
  and a deployed model would need that choice made deliberately.
- Reference records and test photos come from the same exports, which lean
  recent. Same-recordist records are excluded; other people's records from the
  same hotspot are not, which is how the prior would work in practice.
- It does nothing for the Utah question. Crow, raven and magpie all occur
  there, so 0090's 93.5% stands for photos taken at home.
- A first run, before American Crow had a CSV export, scored the other eight
  species at 94.2%. Adding the ninth, a widespread look-alike, is what brought
  the figure to 90.1%.

## What it changed

- A photo classifier for this project should take coordinates as an input, not
  just pixels: image x location at 150 km. Whether to add the record-rate term
  is undecided; it depends on whether missing a rare species or mislabelling a
  common one costs more.
- No new data source was needed. The prior comes from the CSV exports already
  saved, which is a second reason to keep exporting CSVs over saving pages.
- Confirms the division of labour: pixels plus place handle most species;
  American vs. Fish Crow and the raven overlap zone stay with audio.
