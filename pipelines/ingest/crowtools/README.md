# crowtools/labels.json

3,162 hand-reviewed call-type segments over 1,549 American Crow recordings,
lifted out of the [crow-tools](https://github.com/CrowCall/crow-tools) fork by
`../import_crowtools.py` on 2026-07-30.

**This is somebody else's work.** MIT, © 2025 OpenShot Studios LLC, owlmaddie
LLC — `LICENSE.md` here is their copy, kept with the data as the licence
requires. Trained on the archives' weak tags alarm call sits at ~0.65 AUC; on
these labels it reaches 0.97. That result is theirs, not ours.

**This file is committed on purpose, and it is the one thing in this project
that cannot be re-fetched.** The audio it points at can be re-downloaded from
its catalogues by id at any time (that fetching lives with the private corpus
tooling). These labels exist because a person
sat and listened to several thousand seconds of crow, and they survived only
inside an unmaintained fork's gitignored cache until they were moved here.

| | |
|---|---|
| segments | 3,162 reviewed |
| with a CORE label | 2,495 |
| recordings | 1,549 — across two public catalogues (1,440 + 109) |
| alarm call / song / call / begging | 1,283 / 606 / 543 / 307 |

`libraries` maps each recording id to an opaque token for the catalogue it came
from. That is not recoverable from the filename — both use bare numeric ids —
and without it a re-download cannot tell which one to ask. What each token
resolves to is recorded with the corpus tooling, not here.

Not imported, deliberately: `auto.json` (31 MB of the detector's own guesses,
regenerable and not human), the 3-D embeddings (derived), and the audio.

Regenerating it needs the fork: `python ../import_crowtools.py --fork <path>`.
Fetching the audio it names is the corpus tooling's job.
