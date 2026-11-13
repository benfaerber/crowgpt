# 0091 — Does location settle the look-alike corvids?

**Question.** 0090 left the look-alike species near 70% from pixels alone and
found that more photos would not help. Does knowing where the photo was taken
close the gap, using only data already in `data/photos`?

## Method

The eight species whose photos came from Macaulay CSV exports (so each photo
has coordinates): 400 photos each, 399 for Chihuahuan Raven. American Crow is
absent, because its photos came from a saved page and carry no location.

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
  half of its export: Common Raven 89 records a day, Chihuahuan Raven 2, the
  rest 14 to 26.

## Results

Top-1 per species, eight candidates, 150 km radius:

| species | image alone | location alone | image x location | x record rate |
|---|---|---|---|---|
| Black-billed Magpie | 99.0% | 98.0% | 100.0% | 99.8% |
| Carrion Crow | 81.0% | 73.0% | 93.8% | 93.2% |
| Chihuahuan Raven | 64.9% | 97.0% | **99.2%** | 44.9% |
| Common Raven | 69.0% | 31.5% | 79.8% | **93.5%** |
| Eurasian Jackdaw | 93.5% | 31.0% | 95.5% | 95.2% |
| Fish Crow | 81.5% | 98.0% | 98.5% | 93.2% |
| Hooded Crow | 92.2% | 75.2% | 97.8% | 96.8% |
| Rook | 83.5% | 36.2% | 89.0% | 83.5% |
| **balanced accuracy** | 83.1% | 67.5% | **94.2%** | 87.5% |

Image x location by radius: 93.2% at 50 km, 94.2% at 150 km, 93.5% at 500 km.
The radius barely matters.

## What it says

- **Location and pixels fail on different photos.** Neither is good alone
  (83% and 68%); together they reach 94%. Location removes the cross-continent
  confusions (Carrion Crow called Fish Crow) that pixels cannot.
- **Chihuahuan Raven goes from 65% to 99%**, because most of its photos come
  from places Common Ravens are seldom recorded.
- **Common Raven is the species left behind, at 80%.** It occurs across the
  whole northern hemisphere, so its records are spread thin everywhere and the
  location term underrates it wherever a local species is also present.
- **The record-rate correction is a trade, not a fix.** It lifts Common Raven
  to 94% and drops Chihuahuan Raven to 45%. Where the two ravens overlap,
  neither pixels nor location decide, and a prior only picks which one to get
  wrong. That overlap zone is a job for audio.

## Caveats

- **American Crow is missing**, so the pair that matters most in North America,
  American vs. Fish Crow, is untested. Fish Crow's 98.5% is flattered by its
  look-alike not being a candidate. Rerun once an American Crow CSV is in.
- The test set is balanced at 400 per species. Real photos are not, which is
  why the record-rate variant looks worse here than it would in use.
- Reference records and test photos come from the same exports, which lean
  recent. Same-recordist records are excluded; other people's records from the
  same hotspot are not, which is how the prior would work in practice.
- It does nothing for the Utah question. Crow, raven and magpie all occur
  there, so 0090's 94% stands for photos taken at home.

## What it changed

- A photo classifier for this project should take coordinates as an input, not
  just pixels: image x location at 150 km, no record-rate term. The phone
  already records where a capture was made.
- No new data source was needed. The prior comes from the CSV exports already
  saved, which is a second reason to keep exporting CSVs over saving pages.
- Confirms the division of labour: pixels plus place handle most species; the
  raven overlap zone, and probably American vs. Fish Crow, stay with audio.
