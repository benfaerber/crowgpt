# Cawtalker: an AI to talk to crows.
The idea for caw talker started when I began feeding a murder of local crows. I was impressed by their intelligence and wondered if they had a language of their own.

Cawtalker is a set of tools and applications made to analyze and potentially translate crow vocalizations into english. The current version is able to classifier call types and every day I gather more semantics data. The hope is if I pair my call analyzer with the context of what was happening during recordings of crows I will be able to create a “Crow Translate”. I am going for simple calls first, such as “dog spotted”, “human spotted”, “food”, etc.

Crowgpt allows me to generate crow vocalizations synthetically. Currently crowGPT generates an alarm call reliably and begging about half the time; song and generic calls need more training data before they arrive on request. As Crow Translate improves I can make this more granular.

The goal of the project is to combine Crow Translate and CrowGPT into an end-to-end crow-human-crow translator allowing for cross species interactions and friendships with the help of AI!


## What works today

- **Detection + species ID** for corvids in any audio or video file (via
  [BirdNET](https://birdnet.cornell.edu/)), with a waveform timeline of where the
  calls are.
- **Per-species call-type classification** — five corvid species: American Crow,
  Carrion Crow, Common Raven, Rook, Hooded Crow. Each detection is routed to its
  own species' model; a corvid we can detect but haven't trained is shown
  species-only, never mislabeled with another species' model.
- **A reproducible pipeline** to add a species in one command once its corpus
  manifest exists.
- **Honest evaluation** with recording-grouped cross-validation and per-class
  AUC, so nothing is graded on data it trained on.
- **A field capture system** — an Android app that records unprocessed 48 kHz
  audio, a server that ingests it, and a dashboard to work through it. Calls can
  be confirmed, corrected, or marked by ear, and each one tagged with what was
  happening at the time.
- **Generating crow calls** ([`crowgpt/`](crowgpt/)) — a small transformer
  trained from scratch on call bouts cut out of the corpus with no human
  labelling in the extraction loop; call-type conditioning was added later
  through a head trained on the human labels. The long-standing ceiling —
  BirdNET calling 39% of its output a corvid against 81% for real audio
  through the same codec — was measured through a decoder now retired: an
  adversarial decoder finetune closed most of that quality gap
  ([`experiments/0063`](experiments/0063-did-the-decoder-finetune-clear-its-gate/))
  and both numbers await re-measurement through it. It does *not* copy its
  training set: overlap that looked like memorisation turned out to be a
  sampling artifact
  ([`experiments/0015`](experiments/0015-is-it-copying-or-playing-it-safe/)).

## The idea

Two distinct problems hide in "what is the crow saying," and they need different
machinery. Keeping them separate is the main design decision.

1. **What are the call types?** (acoustics) — Are the categories acoustically
   separable at all? A classification problem on audio. **This is what works.**
2. **What does each type mean?** (semantics) — Mapping a call to "I see a dog" or
   "threat human." That needs the call paired with observed *context*, and is the
   open frontier (see [the gold set](#the-gold-set-and-the-semantics-frontier)).

Call types are the four BirdNET-era classes plus **begging**, promoted to its own
core class because juvenile calls were otherwise hidden inside the largest and
vaguest one — and because the detector is worst at exactly them.

**Scope: loud / public calls only.** Crows also make quiet "soft song" (subsong)
that likely carries more information, but it needs a close mic and drowns in
noise. Loud broadcast calls have high SNR and are stereotyped and repeated —
which is what weak supervision needs. Soft song is deferred to a possible v2.

## How it works

Raw audio is too high-dimensional to classify directly, so every clip is turned
into a fixed-length **embedding** — a "fingerprint" where acoustically similar
calls land near each other. We use **BirdNET** (Cornell's bird-specific model) as
the embedder: it was trained on millions of bird recordings, so its internal
representation already separates bird sounds. On top of that, a small
**logistic-regression head per species** maps the fingerprint to a call type. At
a few hundred examples per species, a regularized linear model beats a deep net.

Clips are pooled with **mean + std + max** over their 3-second BirdNET segments
(`pipelines/training/pooling.py`) so the feature captures temporal spread — the
signature of a repeated, insistent alarm vs. a single call.

## Results (measured, not assumed)

**BirdNET was the unlock for representation.** Classical MFCC features and a
general audio transformer (AST) sat near chance; a bird-specific model made the
distinct classes separable — flight call reaches **0.91** one-vs-rest AUC.
(Full write-up: [`pipelines/representation/results/report.md`](pipelines/representation/results/report.md).)

**The remaining limit is labels, not the model.** Trained on the archives' coarse
free-text `type` tags, alarm and song stay weak. But evaluated on a
human-reviewed corpus (from the MIT-licensed
[crow-tools](https://github.com/CrowCall/crow-tools) project) with recording-grouped
CV, the same pipeline lifts them decisively:

| Class | Archive weak labels | Clean labels (crow-tools) |
|-------|:---------------------:|:-------------------------:|
| alarm call | ~0.65 | **0.97** |
| song | ~0.56 | **0.91** |

So alarm and song were **label-limited, not unlearnable** — the path to strong
heads is clean, contextual labels, not a fancier algorithm. (Evaluation:
[`pipelines/ingest/`](pipelines/ingest/).)

## Try it

```bash
make field
```
Open http://127.0.0.1:5100, sign in with the operator token it prints, and drag an
audio or video file onto the dashboard. It uploads through the same endpoints the
phone uses, the worker analyzes it, and the calls come back on a waveform.

Needs the BirdNET venv under `pipelines/representation/.venv-birdnet` and the
trained heads in `pipelines/training/models/` (both included). `make analyzer`
lists the heads without starting anything.

### Add a species

[`corvidcrawler/`](corvidcrawler/) fetches a species from Xeno-canto or the
Macaulay Library into `data/species/<slug>/` with the manifest `make train`
reads:

```bash
make -C corvidcrawler crawl SP=monedula GEN=Coloeus SLUG=eurasian-jackdaw
make train SLUG=eurasian-jackdaw          # train the head; the analyzer picks it up
```

The manifest format is a contract in `pipelines/ingest/manifest.py`: each
writer replaces only its own records, so a re-crawl never discards field
labels exported into the same file.

## Repository layout

| Path | What it is |
|------|------------|
| [`analyzer/`](analyzer/) | BirdNET inference — species + call types from a recording, no server needed |
| [`pipelines/representation/`](pipelines/representation/) | Phase 3 — which embedder separates call types (classical vs AST vs BirdNET) |
| [`pipelines/training/`](pipelines/training/) | Phase 4 — pooling + the call-type heads |
| [`pipelines/ingest/`](pipelines/ingest/) | The American Crow label corpus (vendored, no fork needed) + the per-species training pipeline |
| [`crowgpt/`](crowgpt/) | Generating crow calls — a small transformer over codec tokens, no labels used |
| [`corvidcrawler/`](corvidcrawler/) | The corpus crawler — Xeno-canto and the Macaulay Library into `data/` |
| [`fieldserver/`](fieldserver/) | Fleet ingest + command-and-control API |
| [`fieldserver/worker/`](fieldserver/worker/) | Inference worker — coupled to the server only by the shared DB |
| [`dashboard/`](dashboard/) | Operator dashboard (Vite + React), built into the field server's static/ |
| [`promo/`](promo/) | The promo page — a compiled static bundle the field server serves at `/promo` |
| [`mobile/`](mobile/) | The field capture app (React Native + Expo, Android first) |
| [`experiments/`](experiments/) | 69 numbered measurements, each with what the answer changed |
| [`phases/`](phases/) | The phased plan and dated results |
| `data/` | The corpus (provided externally) — **gitignored**, never committed |

## Data & attribution

### crow-tools, which is why the classifier works at all

**[crow-tools](https://github.com/CrowCall/crow-tools)** — MIT, © OpenShot
Studios / owlmaddie — deserves more than a line in a list, because the single
biggest result in this project is not ours.

Trained on the archives' weak `type` tags, alarm call sat at ~0.65 AUC and song at
~0.56. Trained on crow-tools' labels, they reach **0.97** and **0.91**. That is
the difference between a classifier that does not work and one that does, and it
came entirely from **3,162 hand-reviewed segments across 1,549 recordings** —
somebody sitting and listening to several thousand seconds of crow, one second at
a time, and writing down what each one was. No amount of engineering on this side
substitutes for that, and none of it was our labour.

Its label vocabulary shaped ours, too. The CORE classes here are a deliberate
mapping of crow-tools' flags (`mob`, `alert`, `scold`, `softSong`, `rattle`,
`begging`), and where we departed from it — folding `scold` into alarm, dropping
`grief` — we measured first and wrote down why (`experiments/0012`).

The upstream project is no longer maintained, so as of July 2026 those labels are
vendored into this repo at
[`pipelines/ingest/crowtools/labels.json`](pipelines/ingest/crowtools/) rather
than read from a clone, and the audio is re-fetched from the archives it came
from. **They remain crow-tools' work under its MIT licence** — the copy exists so
the labels outlive an unmaintained fork's gitignored cache directory, not to
claim them.

### The corpus

The recordings are provided externally and held locally for research. Every
recording keeps its recordist so attribution is possible.

The audio corpus, its database, and any recordings live under `data/` and are
gitignored — they are **not** part of this repo. The one exception is
crow-tools' labels above, which are committed precisely because they cannot be
re-downloaded.

## The gold set and the semantics frontier

Problem 2 — *meaning* — needs calls paired with witnessed context. The seed of
that is the **Poe Family**, a local crow family (Thrasher & Ripjaw the parents,
Killer & Shredder the fledglings, Edgar the helper) whose sighting notes are, by
accident, proto-labels of these exact call types. Paired with audio, that becomes
the labeled gold set that maps a call to "I see a dog" — the piece acoustics
alone can't provide.

Sightings were originally logged in a separate map app (`crowtracker/`, since
retired). [`mobile/`](mobile/) replaces it: a capture *is* a sighting with audio
attached, so the note and the recording arrive together instead of being
reconciled afterwards.

## The field capture system

Building the gold set by hand doesn't scale, so this is the fleet that collects
it: record corvid audio in the field with GPS, get it analyzed, and say what was
heard *and what was happening*. The pieces are deliberately separated so the
heavy ML never sits in the request path.

```bash
make field        # field server + inference worker -> http://127.0.0.1:5100
make install-app  # standalone app onto an attached phone (keeps its captures)
make test         # every suite, no device needed
```

| Piece | Job | State |
|-------|-----|-------|
| [`analyzer/`](analyzer/) | BirdNET inference. A path in, findings out — no server, no database. | 5 species heads. Runs standalone (`make analyzer`). |
| [`fieldserver/`](fieldserver/) | CRUD + command-and-control. No model code. | 80 endpoints, resumable uploads, idempotent create, contributor accounts. |
| [`fieldserver/worker/`](fieldserver/worker/) | Polls for jobs, calls the analyzer, writes results back. | Working; shares only a SQLite file with the server. |
| [`dashboard/`](dashboard/) | Operator view — captures, contributors, families, calls × context. | React + TanStack, served by the field server at `/`. |
| [`mobile/`](mobile/) | Field app. Records, labels, syncs only when asked. | In field use: raw 48 kHz capture, video, waveform, trim, families, labelling. |

**Honest status of the corpus.** It is mostly seeded archive clips and test
uploads: 152 captures, of which **24** are genuine field recordings, marked with
a ★ Keep flag. Any count that does not filter on that describes the pipeline, not
crows — the dashboard says which it is showing.

Human labelling has started and is still tiny: **66 labels across 16 captures**,
plus 158 context events. Label count flatters it — measured as *call audio*, the
first 35 of those came to **67.7 seconds**, with only 5 isolating a single call
([`experiments/0013`](experiments/0013-is-there-enough-audio-to-synthesise-a-caw/)).
That is the number that matters.

The server and the worker share one SQLite file and nothing else — no HTTP
between them, no re-upload. That keeps the API responsive while model inference
takes as long as it takes, and means the worker can run on a different machine
(or not at all) without the fleet noticing.

The app is **local-first**: a capture is complete on the phone the moment
recording stops, and syncing is a projection of that record onto the API rather
than the other way round. Because a sync happens only when the user asks for
one, interruption is the normal case rather than the exceptional one, so every
step is resumable and safe to repeat — captures and media are keyed on
device-generated uuids that make create idempotent, and the server's byte count
is authoritative for where an interrupted upload resumes.

Three kinds of ground truth come back, deliberately kept apart:

- **Labels** — what the bird said. A span plus a call type from a closed,
  server-driven vocabulary. The only thing that feeds training.
- **Context** — what a human saw *while that call was made*: a dog walked
  through, someone put food down. Attached to the call, not the recording:
  tagging the whole capture would credit every situation to every call in it, so
  a clip where a dog appears and the crow later sings would report that crows
  sing at dogs.
- **Observations** — free text written afterwards, to explain a confusing
  prediction and to discover which situations recur often enough to earn a tag.

The vocabularies are pushed from the server, so promoting a recurring phrase to
a tag is a config change rather than an app release. See
[`fieldserver/README.md`](fieldserver/README.md).

A call can also be marked **by ear**, with no detection behind it. That matters
more than it sounds: BirdNET scores a begging fledgling at 0.06, so confirming
detections alone can only ever collect what the model already finds — and the
classes it is worst at could never gain training data.

## Setup notes

- Python pipelines run in per-component venvs (BirdNET needs numpy<2 + tflite;
  see each component's README). Apps use `uv`. `crowgpt/` carries torch *and*
  birdnetlib in one venv (`make -C crowgpt venv`) so its stages never hand off
  through a second interpreter.
- **Keys/config are env-only** — nothing location- or account-specific is baked
  into the source. Set the map view via `MAP_CENTER_LAT/LNG/ZOOM` (backend) /
  `EXPO_PUBLIC_MAP_*` (the field app); all default to neutral values.
- **Set `FIELD_LAT` / `FIELD_LON` in `fieldserver/.env`.** They turn on BirdNET's
  species-occurrence filter for captures with no GPS of their own. Without it the
  global model will name a Rook or a Torresian Crow in Utah — and since those
  species have trained heads, the wrong species gets a confident call type hung
  off it. Phone captures carry their own coordinates and ignore this.

## Roadmap

The [`phases/`](phases/) directory has the plan and dated results. Representation
(3), training (4) and assembly (5) are done. The
[field capture system](#the-field-capture-system) is built and in use: the app
records, labels and syncs; the server, worker, analyzer and dashboard all work.

What is left is **not more machinery — it is data**. The corpus now holds 24 real
field recordings and 66 human labels, which is a start rather than a training
set:

1. **Keep labelling real captures.** Confirm what the analyzer heard, correct it,
   and mark the calls it missed. The first 35 labels amounted to 67.7 seconds of
   call audio, only 5 of them isolating a single call — enough to check the
   pipeline end to end, nowhere near enough to train on.
2. **Tag context per call**, which is the only thing that can answer what a call
   is *about*. 158 events so far against a 23-tag vocabulary.
3. **Retrain** the American Crow head on the clean crow-tools labels (now
   vendored, see [attribution](#data--attribution)), then on field labels once
   there are enough.

Known gaps, in rough order of how much they would hurt:

- **No TLS, one shared enrollment secret.** Fine on a home network, blocking for
  anything public.
- **Full-precision GPS on every capture.** A public dataset would export
  contributors' home addresses at seven decimal places; coordinates need
  coarsening before any of this is shared.
- Retracting a synced label or context tag while offline drops it locally but
  leaves it on the server — reconciling that needs tombstones.
- Re-cropping a capture after upload does not re-send the audio.
