# 0094 — Can the photo model say "not a corvid"?

**Question.** A visitor uploaded a black cat. The local Scan page called it a
Fish Crow and the hosted one a Black-billed Magpie. The head knows nine
corvids and always names one. Ben's suggestion: below some percent, say "I
don't think this is a crow". Does a threshold work, and if not, what does?

## The cat

The local scan of the cat: no bird found, and a nearly flat ranking (Fish
Crow 20%, American Crow 17%, Carrion Crow 14%, Eurasian Jackdaw 12%). The
hosted scan had the visitor's location, and the location term turned that
flat guess into a confident magpie, the species with the largest share of
its records near Salt Lake City.

## Method

`run.py` scores six signals, each read as "higher is more corvid-like":

- the head's top probability from pixels alone (the threshold idea);
- whether the detector found a bird;
- how close the BioCLIP embedding is to the training corvids: the nearest
  species centroid, and the mean of the five nearest photos, each for the
  whole frame and for the bird crop.

Corvids: the 3,599 training photos, scored out of fold, and 319 corvids
from the scout layer's archived sighting photos (Utah, small thumbnails, a
different source the model has never seen). Non-corvids: that archive's 464
hawks, owls and falcons. They are birds, so the detector passes them; that
makes them the hard case. For each signal the table gives the share of
non-corvids caught at a threshold that loses 1%, 2%, 5% or 10% of real
corvids.

## Results

Training corvids against the archive's raptors and owls:

| signal | AUC | lose 1% | lose 2% | lose 5% | lose 10% |
|---|---|---|---|---|---|
| top probability | 0.911 | 8.2% | 15.5% | 34.9% | 62.7% |
| whole frame, nearest centroid | 0.953 | 17.0% | 31.5% | 51.3% | 96.8% |
| whole frame, neighbours | 0.952 | 36.4% | 46.1% | 70.7% | 84.5% |
| crop, nearest centroid | 0.964 | 7.8% | 37.9% | 66.2% | 100.0% |
| crop, neighbours | 0.952 | 39.2% | 49.6% | 74.1% | 84.3% |

The archive's own corvids against its raptors and owls (same source and
size on both sides, so the fairer test):

| signal | AUC | lose 1% | lose 2% | lose 5% | lose 10% |
|---|---|---|---|---|---|
| top probability | 0.836 | 7.1% | 11.9% | 22.4% | 41.8% |
| whole frame, nearest centroid | 0.913 | 8.0% | 20.7% | 35.1% | 53.0% |
| whole frame, neighbours | 0.895 | 11.2% | 27.8% | 42.2% | 59.7% |
| crop, nearest centroid | 0.823 | 0.2% | 0.6% | 12.1% | 32.5% |
| crop, neighbours | 0.815 | 18.3% | 28.2% | 41.2% | 55.2% |

"Bird found" alone: the detector finds no bird in 4.2% of training corvids
and 16.3% of the archive's thumbnails, and in 34.5% of the raptors and owls.

The production model on the archive's 319 corvids, its first test outside
the training source:

| | American Crow (130) | Common Raven (105) | Black-billed Magpie (84) |
|---|---|---|---|
| pixels | 66.2% | 47.6% | 95.2% |
| pixels + location | 75.4% | 62.9% | 100.0% |

With location, 22 of the crows and 20 of the ravens are called magpies.

## What it says

- **A percent threshold does not work.** A real crow often scores low
  because the head splits its vote among look-alikes (American Crow 37%,
  Carrion Crow 24%, Fish Crow 24% is a normal answer for a crow). A
  threshold that loses 5% of real corvids catches a fifth to a third of the
  hawks and owls.
- **Distance from the training photos is better and still not enough.** On
  the fair test, losing 5% of corvids catches 35 to 42% of the raptors.
  Nothing unsupervised separates "another bird" from "a corvid" here.
- **The cat is a different and easier case: it is not a bird.** The
  detector already runs on every photo and knows cats, dogs and people.
  When it finds no bird, the page should not headline a species.
- **Telling a hawk from a crow needs examples of hawks.** An "other bird"
  class trained on non-corvid photos is the fix for that, and it needs
  photos the project does not have yet.
- **The location term overrules clear pixels.** A magpie is the one species
  pixels get right 95% of the time, yet with location a sixth of Utah's
  crows and ravens become magpies. The term rewards a species for having a
  small range, which is not evidence about the photo.
- **Accuracy outside the training source is lower than cross-validation
  said**: 75% and 63% for crow and raven against 76% and 81%. The archive's
  photos are small thumbnails, so part of that is resolution, but it is the
  first sign of how field photos will go.

## Caveats

- No cats in the test. The one cat is the visitor's, read from its stored
  result; the file was deleted as designed. The detector's "cat" answer was
  checked on the repo's own non-bird photos (a person, a city skyline), not
  on a cat.
- The non-corvids are five raptor and owl species from one valley. Grackles,
  starlings and blackbirds, the birds people actually mistake for crows, are
  not in it.
- The archive's photos are thumbnails; the Scan page gets full-size uploads.

## What it changed

- **Decided not to use a probability threshold.** Measured, it rejects real
  crows before it rejects hawks.
- The photo model now reports a verdict. When no bird is found and the
  detector confidently sees a cat, dog, person or other animal, the answer
  is "Not a corvid: this looks like a photo of a cat". When no bird is found
  and nothing else is either, the answer is "No bird found", with the
  ranking kept as a stated guess. A species is the headline only when a bird
  was found.
- Opened two follow-ups: an "other bird" class once there are non-corvid
  photos to train it on, and capping the location term so it can rule a
  species out but not vote one in (a first look: capping it moves the
  archive's crows from 75% to 87% for about half a point of cross-validated
  accuracy).
