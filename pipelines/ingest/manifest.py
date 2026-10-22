"""The per-species manifest train_species.py reads, and who may overwrite what.

Two things write data/species/<slug>/manifest.json from opposite ends: the
corpus tooling (a private repo since 2026-08-05, carrying a vendored copy of
this module), which re-fetches a whole species query, and export_manifest.py,
which appends human-labelled field captures. The tooling used to write the file
whole, so a re-fetch silently discarded every field label that had been
exported into it — the training set got smaller and nothing said so. A head
then trained on less than you thought, which is not a failure you can see in
its metrics.

So a record says where it came from, and a re-fetch replaces only its own kind.
Records written before that stamp existed are classified by where their audio
sits: under the species' audio/ dir means the tooling put it there, and
anything else was exported from the field server's media.

Pure stdlib — the field server's tests import this, and they run without any
other venv.

The two writers sit either side of a repo boundary, so the JSON format is a
contract rather than an import. `merge_archive`'s source-stamping is the part
that must not drift: the whole reason it exists is that the two writers
disagree about who owns which record, and only one of them is here to be
changed by the same commit. The tooling's vendored copy keeps its own stamp
values; this side treats every non-field stamp as opaque.
"""

import json
import os
from pathlib import Path

FIELD = "field"

# What an unstamped record under the species' audio/ dir is classified as. The
# tooling's vendored copy resolves legacy records to its own stamp values; on
# this side the only distinction that matters is archive-vs-field, so one
# generic word covers every legacy row.
ARCHIVE = "archive"


def source_of(record, audio_dir):
    """Where a record came from, for manifests written before `source` existed."""
    stamped = record.get("source")
    if stamped:
        return stamped
    path = str(record.get("path", ""))
    return ARCHIVE if path.startswith(str(audio_dir)) else FIELD


def record(rid, path, source, call_type=None, quality=None,
           recordist=None, date=None, locality=None):
    """One manifest row.

    recordist/date/locality are what a grouped train-test split needs: the same
    bird gets uploaded under several ids on the same day by the same person, and
    without them the only available grouping is per-recording, which lets one
    individual sit on both sides of the split.
    """
    row = {"id": str(rid), "type": call_type or "", "path": str(path),
           "quality": quality, "source": source}
    for key, value in (("recordist", recordist), ("date", date), ("locality", locality)):
        if value:
            row[key] = value
    return row


def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def merge_archive(existing, fresh, audio_dir, stamp=ARCHIVE):
    """A fresh archive run replaces its OWN previous records, keeps everything else.

    Returns (records, kept) so the caller can say what it preserved. Silence is
    the thing being fixed here — a run that quietly drops field labels reads
    exactly like one that had none to drop.

    `stamp` is which source is re-fetching. It matters once a species is fed by
    more than one archive: a run from one must leave the other's records alone,
    and vice versa, or whichever ran last would be the only one left and the
    manifest would shrink without complaint.
    """
    kept = [r for r in existing if source_of(r, audio_dir) != stamp]
    kept_paths = {r.get("path") for r in kept}
    return [r for r in fresh if r.get("path") not in kept_paths] + kept, kept


def write(path: Path, records, **meta):
    """Write the manifest so a concurrent reader never sees half of it.

    The corpus tooling rewrites this every couple of hundred downloads, and a
    training run reads it to enumerate the corpus. Those overlap by design — the
    download is meant to keep going overnight — and a plain write_text leaves a window
    where the file on disk is truncated JSON. Rename is atomic on POSIX, so a
    reader gets either the old manifest or the new one and never a fragment.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".incoming")
    staging.write_text(json.dumps({**meta, "recordings": records}, indent=2))
    os.replace(staging, path)
    return path
