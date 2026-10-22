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
2. A **per-species call-type head** labels each detected region.
3. Regions are grouped into calls, with a confidence and a reliability tier.

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

- `calltype_clf.joblib` — the American Crow head
- `<species-slug>/calltype_clf.joblib` — one per additional species

Train another with `make train SLUG=<species-slug>`; this picks it up on the
next start, with no code change.

## History

This lived inside `demo/server.py`, behind a small Flask upload page that
predated the field server. The dashboard replaced the page. The engine inside it
was always the real thing, so it moved out on its own rather than being deleted
with its wrapper.
