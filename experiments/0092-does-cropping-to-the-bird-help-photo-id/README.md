# 0092 — Does cropping to the bird help photo ID?

**Question.** 0090 shrinks the whole photo to 224px, so a small bird keeps a
bill a few pixels long. Does finding the bird and cropping to it first help
tell crows from ravens?

## Method

The four North American black corvids from `data/photos`: American Crow,
Common Raven, Fish Crow (400 each) and Chihuahuan Raven (399).

- Fetch each photo's 1200px version by catalog number.
- Find birds with torchvision's COCO Faster R-CNN (ResNet-50 FPN v2). Take the
  largest bird detected at 0.5 confidence or more, else the best one above
  0.3, else keep the whole frame.
- Crop a square 1.2 times the bird's longer side and embed it with BioCLIP 2.
- Score the 0090 logistic head, 5-fold cross-validated on identical folds, on
  three inputs: the whole-frame embedding, the crop embedding, and the two
  concatenated.

The detector found no bird in 25 of 1,599 photos (1.6%).

## Results

Top-1 accuracy:

| | whole frame | crop only | whole + crop |
|---|---|---|---|
| **Crow vs. raven** (balanced) | 90.9% | 91.4% | **93.2%** |
| American Crow | 93.2% | 94.8% | 95.5% |
| Common Raven | 88.5% | 88.0% | 91.0% |
| **Four black corvids** (balanced) | 71.5% | 69.5% | **74.3%** |
| American Crow | 75.8% | 77.8% | 80.2% |
| Common Raven | 72.5% | 68.2% | 72.2% |
| Fish Crow | 72.2% | 70.0% | 76.5% |
| Chihuahuan Raven | 65.7% | 61.9% | 68.2% |

Photo by photo against the whole frame: for crow vs. raven, whole + crop fixes
24 photos and breaks 5; for four species it fixes 97 and breaks 53. Crop only
fixes 29 and breaks 25 (crow vs. raven), and fixes 144 and breaks 177 (four
species).

Crow vs. raven by how much of the frame the bird fills:

| bird fills | n | whole frame | crop only | whole + crop |
|---|---|---|---|---|
| under 5% | 263 | 86.7% | 88.2% | **92.0%** |
| 5% to 20% | 263 | 92.0% | 92.8% | 93.9% |
| over 20% | 263 | 93.9% | 93.5% | 93.9% |

## What it says

- **Cropping alone does not help.** It trades one set of errors for another
  and is slightly worse on four species. The crop gains bill and throat
  detail but loses the surroundings, and the surroundings carry information:
  habitat separates a Chihuahuan Raven in desert scrub or a Fish Crow on a
  beach from its look-alike.
- **Whole frame plus crop is a real but modest gain**: 2.3 points for crow
  vs. raven and 2.8 points for the four species. The fix-to-break counts
  (24 to 5, 97 to 53) put it well outside chance.
- **The gain is where the lost-detail explanation predicts.** For small birds
  (under 5% of the frame) crow vs. raven goes from 86.7% to 92.0%. For birds
  filling over 20% there is no change.
- **The look-alike pairs are still not solved.** Four-species accuracy stays
  near 74%, so better pixels are not what separates American from Fish Crow
  or the two ravens.

## Caveats

- The concatenated input has twice the features of either alone, so a little
  of its gain could come from capacity; the by-size pattern argues most of it
  is the crop's detail.
- When a photo holds several birds, the largest is cropped. In mixed flocks
  that could be the wrong species.
- Archive photos, as in 0090. Field photos have smaller birds on average,
  which is where this helped most, so the gain there may be larger. Untested.

## What it changed

- A photo classifier for this project should embed both the whole frame and a
  crop of the bird. It costs one detector pass (about 1.3 s on CPU; 0093 later
  swapped in a detector fifteen times cheaper) and one
  extra embedding per photo.
- Decided not to pursue crop-only, or higher-resolution inputs by themselves,
  as a fix for the look-alike pairs.
- Combined with 0091, the recipe so far is whole frame + crop + location. The
  remaining errors need a different signal (audio) or a fine-tuned backbone.
