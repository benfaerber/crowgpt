# analyzer

BirdNET inference. A path in, findings out.

```python
from analyzer import HEADS, analyze, to_wav, waveform_envelope

calls = analyze(to_wav(Path("clip.mp4")))
```

Deliberately knows nothing about the field server — no jobs, no captures, no
database. That separation is what lets the model be run over a loose directory
of files, or one clip, without standing up a server or a queue.
`fieldserver/worker/` is the part that owns jobs and storage, and it calls in
here.

## What it does

1. **BirdNET** locates corvids in the recording and names the species.
2. A **per-species call-type head** labels each detected region (`rattle`, `alarm call`, `begging`, `song`, `flight call` on American Crow via uniform 1024-d window-mean pooling; 3072-d `mean+std+max` on the five archive-only corvid heads).
3. Regions are grouped into calls, with a confidence and a reliability tier, while high-confidence true raptor detections (`>= 0.70`, experiment 0121) are kept alongside as honest co-detections (`"BirdNET also heard: Cooper's Hawk (0.74)"`, never as context or cause).

A detected corvid with no trained head is still reported, species-only. It is
never labelled with another species' model — a Rook's call type guessed by the
American Crow head would be a fabrication, and downstream nothing would show it
apart from a real one.

## Running it

Needs the BirdNET venv (`birdnetlib`, `sklearn`, `joblib`):

```bash
make analyzer     # from the repo root — loads it and lists the heads it found
```

Heads are read from `pipelines/training/models/` at import:

- `<species-slug>/calltype_clf.joblib` — one per species, American Crow included
  (`american-crow/calltype_clf.joblib`), each beside its `metrics.json`

Train another with `make train SLUG=<species-slug>`; this picks it up on the
next start, with no code change.

## Photos

`analyzer/photo/` names the corvid in a photo. Same contract as the audio
side: a path in, findings out, no server and no database.

```python
from analyzer.photo import PhotoIdentifier

identifier = PhotoIdentifier.load()
result = identifier.identify("crow.jpg", latitude=40.76, longitude=-111.89)
result.best.common_name, result.best.probability
```

```bash
make photo-id PHOTO=crow.jpg LAT=40.76 LON=-111.89
```

Three things go into an answer, each measured in `experiments/`:

1. **BioCLIP 2 embeddings with a logistic head** (0090). Zero-shot BioCLIP
   leans toward some species names; a head trained on a few hundred photos per
   species removes that.
2. **The whole frame and a crop of the bird** (0092). A detector finds the
   bird; the crop keeps bill and throat detail on small birds, the whole frame
   keeps the habitat.
3. **Where the photo was taken** (0091). An atlas of where each species is
   recorded, built from the same Macaulay CSV exports the photos come from.
   Coordinates are read from the photo's EXIF when not passed, and ignored
   where no candidate species has a record nearby.

It is a closed set: a photo of any other bird still comes back named as one of
the trained species. `bird_box` is `None` when no bird was found. American vs.
Fish Crow and Common vs. Chihuahuan Raven stay unreliable where their ranges
overlap; those are audio's job.

It runs in its own CPU venv, about two seconds a photo. The model is not in
git. It is built from the photos in `data/`:

```bash
make photos        # photos for every CSV in data/photos/macaulay-exports
make photo-train   # detect, embed, validate, fit; writes data/photos/models/photo-id
make photo-test    # logic tests, no model needed
```

`metrics.json` beside the model holds its cross-validated accuracy per species.
Nothing in the field server or the app calls this yet.

## History

This lived inside `demo/server.py`, behind a small Flask upload page that
predated the field server. The dashboard replaced the page. The engine inside it
was always the real thing, so it moved out on its own rather than being deleted
with its wrapper.
