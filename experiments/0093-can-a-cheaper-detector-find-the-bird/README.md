# 0093 — Can a cheaper detector find the bird?

**Question.** 0092 showed that a crop of the bird, embedded beside the whole
frame, is worth two to three points. Its crop comes from Faster R-CNN
ResNet-50 FPN v2, and on the hosted box (two older cores) a photo took about
30 seconds, most of it that detector. Does a cheaper detector give a crop
that is just as useful?

## Method

`run.py` reuses 0092's photos (the four North American black corvids, 1,599
photos at 1200px), its folds, its BioCLIP 2 embedder and its whole-frame
embeddings. Only the detector that places the crop changes:

- **resnet50 800px**: 0092's detector, the reference.
- **resnet50 448px**: the same network with the short side resized to 448
  instead of 800.
- **mobilenet-v3**: torchvision's Faster R-CNN MobileNetV3-Large FPN, also
  COCO-trained.

Each variant's crops are embedded and the whole+crop logistic head is scored
by 5-fold cross-validation. Detector time is measured on two threads, 12
photos after a warm-up, on the development laptop.

## Results

| crop from | seconds a photo, 2 threads | no bird found | crow vs raven | four black corvids |
|---|---|---|---|---|
| (whole frame only) | | | 90.9% | 71.5% |
| resnet50 800px | 2.96 | 25 | 93.2% | 74.3% |
| resnet50 448px | 1.47 | 43 | **93.4%** | **74.7%** |
| mobilenet-v3 | **0.19** | 82 | 92.2% | 74.6% |

Against the reference's boxes:

- resnet50 448px puts its box on the same bird (IoU over 0.5) in 92.3% of the
  photos where both found one, median IoU 0.94. It misses 23 birds the
  reference found and finds 5 it missed.
- mobilenet-v3: 90.6%, median IoU 0.92. It misses 64 and finds 7.

## What it says

- **The crop does not need a good detector.** MobileNet finds no bird in 82
  photos against 25, and its head is within a point on crow vs. raven
  (92.2% against 93.2%, about eight photos of 800) and level on four species
  (74.6% against 74.3%). When no bird is found the crop falls back to the
  whole frame, which costs little.
- **MobileNet is fifteen times faster** on two threads, 0.19 s against 2.96 s.
  With it, the detector stops being the main cost of a photo; the two BioCLIP
  embeddings (about 1.4 s on the same two cores) are.
- **Halving the ResNet's input halves its time and costs nothing**, but it is
  still seven times slower than MobileNet for the same accuracy.

## Caveats

- One point on crow vs. raven is inside what a different fold split would
  move, so "no worse" is the honest reading, not "one point worse".
- Timings are from the laptop restricted to two threads. The hosted box's
  cores are slower, so absolute times there are larger; the ratio is what
  should carry over.
- Archive photos, as in 0090 and 0092. Field photos have smaller birds, which
  is where a weaker detector misses more. Untested.

## What it changed

- `analyzer/photo` now uses the MobileNetV3 detector, and the production
  model was retrained with its crops. On all nine species (3,599 photos,
  5-fold) the retrained model scores 82.0% by pixels and 91.7% with location,
  against 81.6% and 91.7% with the ResNet-50 crops; no species moves by more
  than two points either way. It finds no bird in 152 photos against 53.
- Decided not to keep the ResNet-50 detector, at either input size.
- The detector no longer explains the wait on the hosted box. What is left is
  the BioCLIP image tower twice a photo, and the cold start when the models
  have been released.
