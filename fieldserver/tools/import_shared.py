#!/usr/bin/env python3
"""Import recordings a recordist shared outside the app, with their notes.

The app is the only door audio normally comes through. This is the other one,
for clips sent by hand (a shared folder of phone videos and a spreadsheet of
what was happening), run on the box over the stores directly, like admin.py.

A manifest describes one batch. It lives beside the files, in `data/`, never in
the tree: it carries the recordist's own notes about named birds and places.

    {
      "batch": "instagram-2026-11",
      "contributor": {"display_name": "...", "region": "UK"},
      "species": "Carrion Crow",
      "generator_excluded": true,
      "families": [{"key": "f1", "name": "...", "notes": "...",
                    "crows": ["Reginald"]}],
      "clips": [{"file": "1.mov", "title": "...", "notes": "...",
                 "observer_role": "feeder", "call_type": "contact call",
                 "label_notes": "recordist: Territorial/contact call",
                 "family": "f1", "caller": "Reginald",
                 "caller_role": null, "contexts": ["human_gives_food"]}]
    }

What each clip becomes: a capture (provenance 'shared', never published,
optionally excluded from the generator), the extracted audio as 48 kHz mono
WAV (re-stored as FLAC like any upload) queued for analysis, the original video
byte-for-byte, one whole-clip human label in the recordist's call type, and the
context events they described, attached to that label.

    uv run python tools/import_shared.py ../data/instagram/batch/import.json
    uv run python tools/import_shared.py ../data/instagram/batch/import.json --apply

Without --apply it validates and prints the plan. Re-running is safe: every
row is keyed on the batch and file name, so a second run finds the first.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fieldserver.app import DEFAULT_DB  # noqa: E402
from fieldserver.core.schema import upgrade  # noqa: E402
from fieldserver.stores.analysis import AnalysisStore  # noqa: E402
from fieldserver.stores.captures import CaptureStore  # noqa: E402
from fieldserver.stores.config_store import ConfigStore  # noqa: E402
from fieldserver.stores.context_events import ContextStore  # noqa: E402
from fieldserver.stores.contributors import ContributorStore  # noqa: E402
from fieldserver.stores.db_base import utc_now  # noqa: E402
from fieldserver.stores.devices import DeviceStore  # noqa: E402
from fieldserver.stores.families import FamilyStore  # noqa: E402
from fieldserver.stores.labels import LabelStore  # noqa: E402
from fieldserver.stores.media import MediaStore  # noqa: E402

CHUNK = 8 * 1024 * 1024
PLATFORM = "shared"


class ManifestError(ValueError):
    pass


@dataclass
class Clip:
    file: str
    call_type: str
    title: str | None = None
    notes: str | None = None
    label_notes: str | None = None
    observer_role: str | None = None
    family: str | None = None
    caller: str | None = None
    caller_role: str | None = None
    contexts: list[str] = field(default_factory=list)

    def uuid(self, batch, suffix):
        return f"{batch}:{self.file}:{suffix}"


@dataclass
class Manifest:
    path: Path
    batch: str
    contributor: dict
    species: str
    generator_excluded: bool
    families: list[dict]
    clips: list[Clip]

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        raw = json.loads(path.read_text())
        return cls(
            path=path,
            batch=raw["batch"],
            contributor=raw["contributor"],
            species=raw["species"],
            generator_excluded=bool(raw.get("generator_excluded", False)),
            families=raw.get("families", []),
            clips=[Clip(**clip) for clip in raw["clips"]],
        )

    @property
    def folder(self) -> Path:
        return self.path.parent

    def validate(self, config: ConfigStore) -> None:
        problems = []
        family_keys = {f["key"] for f in self.families}
        crows = {name for f in self.families for name in f.get("crows", [])}
        for clip in self.clips:
            where = clip.file
            if not (self.folder / clip.file).exists():
                problems.append(f"{where}: file not found")
            if not config.label_exists(clip.call_type):
                problems.append(f"{where}: unknown call_type {clip.call_type!r}")
            if clip.observer_role and not config.observer_role_exists(clip.observer_role):
                problems.append(f"{where}: unknown observer_role {clip.observer_role!r}")
            if clip.caller_role and not config.caller_role_exists(clip.caller_role):
                problems.append(f"{where}: unknown caller_role {clip.caller_role!r}")
            if clip.family and clip.family not in family_keys:
                problems.append(f"{where}: unknown family {clip.family!r}")
            if clip.caller and clip.caller not in crows:
                problems.append(f"{where}: caller {clip.caller!r} is in no family")
            for key in clip.contexts:
                if not config.context_exists(key):
                    problems.append(f"{where}: unknown context {key!r}")
        if problems:
            raise ManifestError("\n".join(problems))


class Media:
    """ffprobe/ffmpeg over one shared file."""

    def __init__(self, path: Path):
        self.path = path

    def duration(self) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(self.path)],
            check=True, capture_output=True, text=True).stdout
        return float(out.strip())

    def extract_wav(self, dest: Path) -> None:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(self.path), "-map", "0:a:0",
             "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(dest)],
            check=True)


class SharedImporter:
    def __init__(self, db_path: Path):
        upgrade(db_path)
        media_dir = db_path.parent / "media"
        self.db_path = db_path
        self.config = ConfigStore(db_path)
        self.contributors = ContributorStore(db_path)
        self.devices = DeviceStore(db_path)
        self.families = FamilyStore(db_path)
        self.captures = CaptureStore(db_path)
        self.media = MediaStore(db_path, media_dir)
        self.labels = LabelStore(db_path)
        self.contexts = ContextStore(db_path)
        self.analysis = AnalysisStore(db_path)

    def plan(self, manifest: Manifest) -> None:
        manifest.validate(self.config)
        print(f"batch {manifest.batch}: {len(manifest.clips)} clips, "
              f"species {manifest.species}, generator_excluded="
              f"{manifest.generator_excluded}")
        for clip in manifest.clips:
            print(f"  {clip.file:10} {clip.call_type:14} caller={clip.caller or '-':14} "
                  f"contexts={','.join(clip.contexts) or '-'}")

    def apply(self, manifest: Manifest) -> None:
        manifest.validate(self.config)
        contributor_id, device_id = self._actor(manifest)
        families, crows = self._families(manifest, contributor_id, device_id)
        version = self.config.current_version()
        for clip in manifest.clips:
            capture_id = self._clip(manifest, clip, contributor_id, device_id,
                                    families, crows, version)
            print(f"  {clip.file} -> capture {capture_id}")
        print(f"contributor {contributor_id}, device {device_id}")

    def _actor(self, manifest):
        """The batch's contributor and its device, found again on a re-run.

        The device exists because a capture must name one; its token is revoked
        at once, since nobody will ever sync through it.
        """
        with self.devices._connect() as conn:
            row = conn.execute(
                "SELECT id, contributor_id FROM devices WHERE platform = ? AND label = ?",
                (PLATFORM, manifest.batch)).fetchone()
        if row:
            return row["contributor_id"], row["id"]
        person = manifest.contributor
        contributor, _ = self.contributors.create(person["display_name"])
        self.contributors.set_location_precision(
            contributor["id"], "region", region=person.get("region"))
        device, _ = self.devices.register(contributor["id"], label=manifest.batch,
                                          platform=PLATFORM)
        self.devices.revoke(device["id"])
        return contributor["id"], device["id"]

    def _families(self, manifest, contributor_id, device_id):
        families, crows = {}, {}
        for spec in manifest.families:
            family = self.families.add(
                contributor_id, device_id, spec["name"], notes=spec.get("notes"),
                client_uuid=f"{manifest.batch}:family:{spec['key']}")
            families[spec["key"]] = family["id"]
            for name in spec.get("crows", []):
                crows[name] = self._crow(family["id"], contributor_id, name,
                                         f"{manifest.batch}:crow:{name}")
        return families, crows

    def _crow(self, family_id, contributor_id, name, client_uuid):
        with self.families._connect() as conn:
            row = conn.execute("SELECT id FROM crows WHERE family_id = ? AND name = ?",
                               (family_id, name)).fetchone()
            if row:
                return row["id"]
            return conn.execute(
                "INSERT INTO crows (family_id, name, created_at, client_uuid, "
                "contributor_id) VALUES (?, ?, ?, ?, ?)",
                (family_id, name, utc_now(), client_uuid, contributor_id)).lastrowid

    def _clip(self, manifest, clip, contributor_id, device_id, families, crows, version):
        source = Media(manifest.folder / clip.file)
        duration = source.duration()
        capture = self.captures.add(
            contributor_id, device_id, region=manifest.contributor.get("region"),
            duration_sec=duration, notes=clip.notes, name=clip.title or clip.file,
            family_id=families.get(clip.family), client_uuid=clip.uuid(manifest.batch, "capture"),
            keep=True, observer_role=clip.observer_role, provenance="shared",
            generator_excluded=manifest.generator_excluded)
        capture_id = capture["id"]

        audio = self._upload_audio(manifest, clip, capture_id, source)
        self._upload_original(manifest, clip, capture_id, source)
        self.captures.set_status(capture_id, "uploaded")

        label = self.labels.add(
            capture_id, audio["id"], contributor_id, device_id, manifest.species,
            clip.call_type, start_sec=0.0, end_sec=duration, label_source="human",
            notes=clip.label_notes, client_uuid=clip.uuid(manifest.batch, "label"),
            config_version=version, crow_id=crows.get(clip.caller),
            caller_role=clip.caller_role)
        for key in clip.contexts:
            self.contexts.add(capture_id, contributor_id, device_id, key,
                              label_id=label["id"], start_sec=0.0, end_sec=duration,
                              client_uuid=clip.uuid(manifest.batch, f"context:{key}"),
                              config_version=version)

        if not self._has_job(capture_id):
            self.analysis.enqueue(capture_id, audio["id"])
            self.captures.set_status(capture_id, "analyzing")
        return capture_id

    def _has_job(self, capture_id) -> bool:
        with self.analysis._connect() as conn:
            return conn.execute("SELECT 1 FROM analysis_jobs WHERE capture_id = ?",
                                (capture_id,)).fetchone() is not None

    def _upload_audio(self, manifest, clip, capture_id, source):
        slot = self.media.create(capture_id, kind="audio", format="wav",
                                 sample_rate=48000, channels=1,
                                 client_uuid=clip.uuid(manifest.batch, "audio"))
        if slot["upload_state"] == "complete":
            return slot
        with tempfile.TemporaryDirectory() as scratch:
            wav = Path(scratch) / "audio.wav"
            source.extract_wav(wav)
            return self._write(slot, wav)

    def _upload_original(self, manifest, clip, capture_id, source):
        extension = source.path.suffix.lower().lstrip(".")
        slot = self.media.create(capture_id, kind="video", format=extension,
                                 client_uuid=clip.uuid(manifest.batch, "video"))
        if slot["upload_state"] == "complete":
            return slot
        return self._write(slot, source.path)

    def _write(self, slot, path: Path):
        offset = 0
        if slot["upload_state"] == "partial":
            self.media.path(slot).unlink(missing_ok=True)
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                self.media.append(slot["id"], chunk, offset)
                offset += len(chunk)
        return self.media.finalize(slot["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db_path = Path(os.environ.get("FIELD_DB") or DEFAULT_DB)
    manifest = Manifest.load(args.manifest.resolve())
    importer = SharedImporter(db_path)
    try:
        importer.apply(manifest) if args.apply else importer.plan(manifest)
    except ManifestError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
