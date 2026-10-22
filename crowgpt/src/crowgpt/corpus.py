"""Enumerating the collected corpus.

TWO STORES, because it grew in two stages and never got reconciled. A manifest
tree at data/species/<slug>/audio with a manifest.json beside it, written by the
corpus tooling and by pipelines/ingest/export_manifest.py; and
data/audio/<source>/ indexed by data/corvid.db, written by the corpus tooling
CLI. This module reads both and reconciles them, which is the only reason
anything downstream sees one corpus.

WHAT THIS DOCSTRING USED TO SAY, and what changed on 2026-08-06. It claimed
"data/species/american-crow/audio IS EMPTY" and that American Crow lived only in
corvid.db. Both were true when written and neither is now: that directory holds
13,422 files and 17 GB, almost all of it one big archive batch, and the manifest is
the ONLY index of those 13,311 records — corvid.db has no rows for them at all.
The description ran three weeks behind the disk, which is how a reader plans
from it and mis-scopes.

Measured on the day of the reconciliation, so the next reader can tell drift
from a real change:

    manifest tree   15,713 records over 6 slugs   28 GB
    corvid.db       11,689 rows                   44 GB
                    the other sources 11,689
    in both         2,383 shared ids, byte-identical, 9.87 GB duplicated

WHAT A RECORD KNOWS DECIDES HOW WELL IT CAN BE GROUPED, and grouping is what
stops one individual bird landing on both sides of a train/test split.
Recordists upload many recordings of one bird, one site, one day under separate
ids, so grouping per recording is not enough.

Manifests written since the reconciliation carry recordist/date/locality.
Four of the six carry only id/type/path/quality and fall back to per-recording,
which is weaker — but corvid.db holds recordist and date for nearly all of the
same recordings, so the fix is a join and not a re-fetch.
"""

import json
import os
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get("DATA_DIR") or REPO / "data")
SPECIES_DIR = DATA / "species"
CROW_DB = DATA / "corvid.db"

AMERICAN_CROW = "american-crow"

#: Where a recording whose species was never identified goes. "Corvus spec."
#: is the archive saying it does not know, and the corpus must not turn that
#: into a species — a slug that looks like a bird is one nobody questions.
UNIDENTIFIED = "unknown"


class Recording:
    """One source file, with everything the split and the index need."""

    def __init__(self, path, species, recording_id, group_key, quality=None):
        self.path = Path(path)
        self.species = species
        self.recording_id = recording_id
        self.group_key = group_key
        self.quality = quality

    def __repr__(self):
        return f"<Recording {self.species}/{self.recording_id} {self.path.name}>"


class Corpus:
    """Every downloaded recording, from both sources."""

    def __init__(self, species_dir=SPECIES_DIR, crow_db=CROW_DB, limit_per_species=None):
        self.species_dir = Path(species_dir)
        self.crow_db = Path(crow_db)
        self.limit = limit_per_species or int(os.environ.get("SAMPLE_PER_SPECIES", "0")) or None

    def recordings(self):
        # THE DATABASE ROW WINS. This ran manifests first and kept first-seen,
        # so for every recording held in both stores the poorer record won:
        # 1,982 of them have a recordist and a date in the database and neither
        # in the manifest, and the dedup was throwing the richer copy away and
        # then grouping them per-recording for want of the metadata it had just
        # discarded.
        found = {}
        for slug, items in self._from_crow_db().items():
            found.setdefault(slug, []).extend(items)
        for slug, items in self._from_manifests().items():
            found.setdefault(slug, []).extend(items)

        for slug, items in found.items():
            seen = set()
            unique = []
            for rec in items:
                if rec.recording_id in seen:
                    continue
                seen.add(rec.recording_id)
                unique.append(rec)
            found[slug] = unique[: self.limit]
        return found

    def _from_manifests(self):
        out = {}
        for manifest_path in sorted(self.species_dir.glob("*/manifest.json")):
            slug = manifest_path.parent.name
            manifest = json.loads(manifest_path.read_text())
            items = []
            for entry in manifest.get("recordings", []):
                if entry.get("source") == "field" or not entry.get("path"):
                    continue
                path = Path(entry["path"])
                if not path.exists():
                    path = manifest_path.parent / "audio" / path.name
                if not path.exists():
                    continue
                rec_id = str(entry.get("id") or path.stem)
                items.append(
                    Recording(path, slug, rec_id, self._manifest_group(slug, rec_id, entry),
                              entry.get("quality"))
                )
            if items:
                out[slug] = items
        return out

    @staticmethod
    def _manifest_group(slug, rec_id, entry):
        """Recordist and day if the manifest records them, else the recording.

        SAME SHAPE AS THE DATABASE KEY, deliberately. These two branches used
        different formats — `slug:who|when|where` here against a different one
        there — so two recordings of the same session grouped apart whenever
        one came from each store, which is a leak rather than a cosmetic
        difference. Locality is out for the same reason it is out of the store's
        rule: it splits a session whenever the place string varies, and finer
        groups are the unsafe direction.
        """
        who, when = entry.get("recordist"), entry.get("date")
        if who and when:
            return f"{slug}|rec-day|{who}|{str(when)[:10]}"
        if who:
            return f"{slug}|rec|{who}"
        return f"{slug}|file|{rec_id}"

    #: the archives' common name against the slug the corpus already uses. Both
    #: are the same bird under a name that changed: Corvus corax is filed as
    #: "Northern Raven" by XC and as common-raven here, and Coloeus monedula as
    #: "Western Jackdaw" against eurasian-jackdaw. Slugifying naively would
    #: split each species into two, and the model conditions on the species
    #: token — so half of every raven would train under a label the other half
    #: never sees.
    SPECIES_ALIASES = {
        "northern-raven": "common-raven",
        "western-jackdaw": "eurasian-jackdaw",
    }

    @classmethod
    def _slug(cls, common_name):
        slug = "-".join((common_name or "").lower().split())
        return cls.SPECIES_ALIASES.get(slug, slug)

    def _from_crow_db(self):
        """Every downloaded corpus row, under its OWN species.

        THIS USED TO LABEL EVERYTHING american-crow, and that was correct
        exactly as long as the corpus only held American Crow. The 2026-08-05
        sweep brought back 10,637 recordings across 48 species — hooded crows,
        ravens, jackdaws, rooks and forty-four others — of which 446 are
        American Crow. Extracting under the old code would have filed all of
        them as american-crow, silently: nothing raises, the bouts extract, the
        species token becomes noise, and the one species this project is about
        gets its training signal diluted twenty-fold by other birds wearing its
        name.
        """
        if not self.crow_db.exists():
            return {}
        with sqlite3.connect(str(self.crow_db)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT source, source_ref, file_path, quality, recordist, raw, "
                "       species, slug, group_key, date, location "
                "FROM recordings WHERE downloaded = 1 AND file_path IS NOT NULL"
            ).fetchall()

        out = {}
        for row in rows:
            path = Path(row["file_path"])
            if not path.exists():
                # A stale absolute file_path (the corpus moved) rejoins under
                # the layout the tooling writes: audio/<source>/<name>.
                path = DATA / "audio" / row["source"] / path.name
            if not path.exists():
                continue
            # THE STORE ANSWERS BOTH OF THESE NOW. `slug` and `group_key` are
            # resolved once, by one rule, at write time — three definitions of
            # the grouping used to live in the readers and they disagreed,
            # which they will keep doing because a reader that opens this
            # database with bare sqlite3 shares no code with the others.
            # SLUG AND KEY COME FROM THE SAME PLACE OR NOT AT ALL. A row the
            # store has grouped has already had its species adjudicated, and a
            # NULL slug there is a decision — "Corvus spec." names no bird, and
            # slugifying it anyway invents a species called corvus-spec. that
            # the group key (correctly) refuses to use. Only a row the store
            # has never seen falls back to deriving both here.
            if row["group_key"]:
                slug = row["slug"] or UNIDENTIFIED
                group = row["group_key"]
            else:
                slug = self._slug(row["species"]) or AMERICAN_CROW
                group = self._group_key(slug, str(row["source_ref"] or path.stem), row)
            rec_id = str(row["source_ref"] or path.stem)
            out.setdefault(slug, []).append(
                Recording(path, slug, rec_id, group, row["quality"])
            )
        return out

    def _group_key(self, slug, rec_id, row):
        """Recordist plus day, for a row the store has not grouped yet.

        THIS USED TO NAMESPACE EVERY KEY american-crow, whatever the bird was,
        even though the slug was already in hand a few lines above. After the
        2026-08-05 sweep put 48 species in the database that put 8,809
        recordings into a group named after a species they do not belong to —
        hooded crows, ravens and jackdaws merged under the American Crow label.
        The damage was over-merging rather than leakage, but it was 35% of the
        corpus and it was silent.

        Date comes off the COLUMN first and the raw blob second. The column is
        populated for most rows of the two biggest sources, and for 817 more that
        have no `raw.date` at all, so reading the blob alone dropped recordings
        to per-recording grouping for no reason.
        """
        meta = {}
        if row["raw"]:
            try:
                meta = json.loads(row["raw"])
            except (ValueError, TypeError):
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        who = row["recordist"] or meta.get("rec")
        when = row["date"] or meta.get("date")
        if who and when:
            return f"{slug}|rec-day|{who}|{str(when)[:10]}"
        if who:
            return f"{slug}|rec|{who}"
        return f"{slug}|file|{rec_id}"
