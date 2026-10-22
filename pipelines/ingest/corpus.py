"""The American Crow label corpus: 3,162 hand-reviewed segments, vendored here.

The labels are committed at `crowtools/labels.json` and the audio they name
arrives in `data/species/american-crow/audio` with the rest of the corpus — the
private corpus tooling re-fetches it by id, so a fresh checkout needs the
corpus on disk after all. Nothing in *this* module fetches anything: reading
the corpus that is already there is pure stdlib, which is why the field
server's tests can import it.

`import_crowtools.py` is the only script in this project that knows what the
upstream fork is, and it is needed only to re-import the labels if upstream ever
changes.

The labels are not our work — MIT, © 2025 OpenShot Studios LLC, owlmaddie LLC.
`crowtools/README.md` says where they came from and what they cost; their licence
sits beside them in `crowtools/LICENSE.md`.

This module maps their multi-label flags onto CrowGPT's CORE call types;
build_dataset.py turns them into pooled BirdNET features for Phase 4. Pure
stdlib, so it runs in any interpreter — the fieldserver tests import it to check
the two label spaces still agree.

Run it directly to see what is on disk:

    python pipelines/ingest/corpus.py
"""

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR") or REPO / "data")

# The vendored labels, and where the corpus supplies the recordings they name.
IMPORTED_LABELS = Path(__file__).resolve().parent / "crowtools" / "labels.json"
LOCAL_AUDIO = DATA / "species" / "american-crow" / "audio"


def env_file_value(key, env_file=None):
    """Read one key out of the repo-root .env. Hand-parsed to stay stdlib-only.

    Not corpus-specific — tools/backup.py reads BACKUP_DIR through it, and
    import_crowtools.py reads its own key. python-dotenv is not a dependency
    here on purpose: the fieldserver tests import this module to check the two
    label spaces agree, and they run without the BirdNET venv. Handles
    `KEY=value`, `export KEY=value`, comments and quotes — enough for paths,
    which is all this file holds.
    """
    path = Path(env_file or REPO / ".env")
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.removeprefix("export ").partition("=")
        if name.strip() == key:
            return value.strip().strip("'\"") or None
    return None


# The CORE call types, written down once for everything that has to agree about
# them. This module is pure stdlib and importable by path from any interpreter,
# which is what lets the field server (its own venv), the training pipelines
# (BirdNET's) and crowgpt (torch's) check themselves against one list instead of
# each keeping a copy. Three copies is what there used to be, and they had
# already drifted: crowgpt's is four classes because the flags below cannot
# produce a flight call, and nothing said so.
#
# Adding one here is a fleet-wide vocabulary change — the served config, the
# shipped classifier's classes and the generator's prefix tokens all move — so
# it belongs with a WIRE_VERSION bump and a look at every consumer, not on its
# own.
CORE_CLASSES = ("alarm call", "begging", "call", "flight call", "song")

# The segments carry several boolean call-type flags. Map them onto the same CORE
# classes recover_and_pool.py uses, so the two corpora share a label space.
#
# NOT EVERY CORE CLASS IS REACHABLE FROM HERE, and that is the fork this comment
# exists to stop being silent: there is no flight-call flag in the upstream
# labels, so no segment of this corpus can carry the class with the best AUC in
# the project (0.91). Anything trained only on these flags has a four-class
# vocabulary, and anything joining it to the fleet's five has to say what it
# does with the fifth rather than discover the gap at runtime.
# mob/alert/scold are alarm; softSong is song; rattle is a generic call; begging
# is its own class (this corpus is where nearly all of it lives — 307 reviewed
# segments against 4 in the archive set). grief, at 3 segments, stays out.
#
# Why the finer flags are not classes of their own — measured in
# experiments/0012, not assumed. scold looks temptingly large at 106 positives
# and fails three ways: 0.581 grouped AUC against a 0.947 control, 76% of it is
# also mob, and it is only *asked* on 1,089 of 2,494 segments. That last one is
# the trap — the upstream project grew scold and grief mid-labelling, so on the
# rest the key is absent rather than False, and reading it with .get() turns
# 1,405 unexamined segments into confident negatives. mob vs alert is the one
# split the corpus does support (0.726 with the recording held constant), and it
# waits on field labels to score it against rather than on evidence.
FLAG_TO_CORE = {
    "mob": "alarm call",
    "alert": "alarm call",
    "scold": "alarm call",
    "softSong": "song",
    "rattle": "call",
    "begging": "begging",
}


class LabeledSegment:
    def __init__(self, file_id, library, audio_path, start, end, labels, flags):
        self.file_id = file_id
        self.library = library
        self.audio_path = audio_path
        self.start = start
        self.end = end
        self.labels = labels  # set of CORE classes (multi-label)
        self.flags = flags

    @property
    def key(self):
        return f"{self.file_id}-{self.start}-{self.end}"


class LabelCorpus:
    def __init__(self, dataset="all-public", imported=IMPORTED_LABELS):
        self.dataset = dataset
        self.imported_path = Path(imported)
        self._audio_index = None
        self._imported = None

    @property
    def imported(self):
        """The committed labels. Absent means the import was never run."""
        if self._imported is None:
            if not self.imported_path.exists():
                raise FileNotFoundError(
                    f"No labels at {self.imported_path}. They are committed, so this "
                    f"is a broken checkout rather than a missing download — restore "
                    f"the file, or regenerate it with "
                    f"`python pipelines/ingest/import_crowtools.py --fork <path>`."
                )
            self._imported = json.loads(self.imported_path.read_text())
        return self._imported

    @property
    def source(self):
        """Where the labels came from, as stamped by the import."""
        return self.imported.get("source") or self.dataset

    def audio_index(self):
        """Map file_id -> (library, path) for every recording on disk.

        The library is carried by the labels rather than read off the filename:
        both archives use bare numeric ids, so it is not recoverable from disk.
        """
        if self._audio_index is None:
            attribution = self.imported.get("libraries", {})
            self._audio_index = {
                mp3.stem: (attribution.get(mp3.stem), mp3)
                for mp3 in sorted(LOCAL_AUDIO.glob("*.mp3"))
            } if LOCAL_AUDIO.is_dir() else {}
        return self._audio_index

    def labels(self):
        return self.imported["labels"]

    @staticmethod
    def core_labels(flags):
        return {core for flag, core in FLAG_TO_CORE.items() if flags.get(flag)}

    def labeled_segments(self, require_audio=True):
        """Yield reviewed segments that carry at least one CORE label."""
        index = self.audio_index()
        for key, flags in self.labels().items():
            if not flags.get("reviewed"):
                continue
            labels = self.core_labels(flags)
            if not labels:
                continue
            file_id, start, end = key.rsplit("-", 2)
            found = index.get(file_id)
            if found is None:
                if require_audio:
                    continue
                library, audio_path = None, None
            else:
                library, audio_path = found
            yield LabeledSegment(
                file_id, library, audio_path, int(start), int(end), labels, flags,
            )


def _describe():
    """What the labels hold and how much of their audio has been fetched.

    Segment counts come with and without audio on purpose: the labels are
    committed but the recordings are not, so "have the labels, downloaded
    nothing" is the normal half-finished state and the one worth seeing at a
    glance.
    """
    corpus = LabelCorpus()
    print(f"labels:   {corpus.imported_path}")
    print(f"source:   {corpus.source}, imported {corpus.imported.get('imported', '?')}")
    print(f"audio:    {LOCAL_AUDIO}")

    labeled = list(corpus.labeled_segments(require_audio=False))
    with_audio = [s for s in labeled if s.audio_path]
    print(f"segments: {len(labeled)} with a CORE label, {len(with_audio)} with audio")
    for core in sorted(set(FLAG_TO_CORE.values())):
        n = sum(1 for s in with_audio if core in s.labels)
        print(f"  {core:<12} {n}")
    if not with_audio:
        print("\nNo audio yet — fetch exactly the recordings the labels name with"
              "\n  python pipelines/ingest/import_crowtools.py --download")


if __name__ == "__main__":
    import sys

    try:
        _describe()
    except FileNotFoundError as e:
        sys.exit(str(e))
