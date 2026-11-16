"""Promoting a kept scan to a capture.

A contribution is a stranger's file with a model's guess and, if they used
the labelling desk, their own answers. Promotion is the operator saying it is
worth having: it becomes a capture like one shared by hand
(tools/import_shared.py does the same over a manifest), its audio queued for
the real analysis, and the visitor's answers carried across as labels and
context events.

What marks it afterwards, so it can never be mistaken for a field recording:

  - `provenance = 'scan'`, and never ★ Keep. Keep is the recordist's word
    that they were there; nobody on the project was.
  - `generator_excluded`, since where the audio came from is unknown.
  - `label_source = 'visitor'` on every label carried over. They are a
    stranger's answers on a web page, not the recordist's ground truth, and
    anything counting human labels can tell them apart.
  - one shared contributor, "Scan visitors", whose only device is revoked.

Promoting twice is safe: every row is keyed on the contribution's id.
"""

import tempfile
from pathlib import Path

from .transcode import run_ffmpeg

PLATFORM = "scan"
ACTOR = "Scan visitors"
LABEL_SOURCE = "visitor"
CHUNK = 8 * 1024 * 1024
DEFAULT_SPECIES = "American Crow"


class NotPromotable(ValueError):
    pass


class ScanPromotion:
    def __init__(self, desk, config, contributors, devices, captures, media, labels,
                 context, analysis):
        self.desk = desk
        self.config = config
        self.contributors = contributors
        self.devices = devices
        self.captures = captures
        self.media = media
        self.labels = labels
        self.context = context
        self.analysis = analysis

    def promote(self, contribution: dict) -> dict:
        if contribution["kind"] not in ("audio", "video"):
            raise NotPromotable("only a recording or a video can become a capture")
        source = self.desk.path(contribution)
        if not source.exists():
            raise NotPromotable("the kept file is gone")
        contributor_id, device_id = self._actor()
        result = contribution["result"] or {}
        capture = self.captures.add(
            contributor_id, device_id,
            latitude=contribution["latitude"], longitude=contribution["longitude"],
            recorded_at=contribution["created_at"], duration_sec=result.get("duration_sec"),
            name=f"Scan contribution {contribution['id']}",
            client_uuid=self._uuid(contribution, "capture"),
            keep=False, provenance=PLATFORM, generator_excluded=True)
        audio = self._audio(contribution, capture["id"], source)
        if contribution["kind"] == "video":
            self._original(contribution, capture["id"], source)
        self.captures.set_status(capture["id"], "uploaded")
        self._answers(contribution, capture["id"], audio["id"], contributor_id, device_id)
        if contribution["silent_confirmed_at"]:
            self.captures.confirm_silent(capture["id"])
        if not self._has_job(capture["id"]):
            self.analysis.enqueue(capture["id"], audio["id"])
            self.captures.set_status(capture["id"], "analyzing")
        self.desk.mark_promoted(contribution["id"], capture["id"])
        return self.captures.get(capture["id"])

    def _actor(self):
        with self.devices._connect() as conn:
            row = conn.execute(
                "SELECT id, contributor_id FROM devices WHERE platform = ? AND label = ?",
                (PLATFORM, ACTOR)).fetchone()
        if row:
            return row["contributor_id"], row["id"]
        contributor, _ = self.contributors.create(ACTOR)
        device, _ = self.devices.register(contributor["id"], label=ACTOR, platform=PLATFORM)
        self.devices.revoke(device["id"])
        return contributor["id"], device["id"]

    def _answers(self, contribution, capture_id, media_id, contributor_id, device_id):
        label_ids = {}
        for label in self.desk.labels(contribution["id"]):
            row = self.labels.add(
                capture_id, media_id, contributor_id, device_id,
                self._species(contribution, label), label["call_type"],
                start_sec=label["start_sec"], end_sec=label["end_sec"],
                label_source=LABEL_SOURCE, caller_role=label["caller_role"],
                client_uuid=self._uuid(contribution, f"label:{label['client_uuid']}"),
                config_version=label["config_version"])
            label_ids[label["client_uuid"]] = row["id"]
        for event in self.desk.context(contribution["id"]):
            if event["label_uuid"] and event["label_uuid"] not in label_ids:
                continue
            self.context.add(
                capture_id, contributor_id, device_id, event["key"],
                label_id=label_ids.get(event["label_uuid"]),
                start_sec=event["start_sec"], end_sec=event["end_sec"],
                client_uuid=self._uuid(contribution, f"context:{event['client_uuid']}"),
                config_version=event["config_version"])

    def _species(self, contribution, label) -> str:
        """The species of the detection the label sits on, when there is one.
        A label that trains nothing claims no species, as on the phone."""
        if self.config.core_for_label(label["call_type"]) is None:
            return "unknown"
        overlapping = [
            call for call in self.desk.calls(contribution)
            if call.get("species")
            and call["start_sec"] < label["end_sec"] and call["end_sec"] > label["start_sec"]]
        if overlapping:
            return max(overlapping, key=lambda call: min(call["end_sec"], label["end_sec"])
                       - max(call["start_sec"], label["start_sec"]))["species"]
        return DEFAULT_SPECIES

    def _audio(self, contribution, capture_id, source: Path):
        slot = self.media.create(capture_id, kind="audio", format="wav", sample_rate=48000,
                                 channels=1, client_uuid=self._uuid(contribution, "audio"))
        if slot["upload_state"] == "complete":
            return slot
        with tempfile.TemporaryDirectory() as scratch:
            wav = Path(scratch) / "audio.wav"
            run_ffmpeg(["-y", "-i", str(source), "-map", "0:a:0", "-ac", "1", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(wav)],
                       "could not read the kept file's audio")
            return self._write(slot, wav)

    def _original(self, contribution, capture_id, source: Path):
        slot = self.media.create(capture_id, kind="video",
                                 format=source.suffix.lower().lstrip("."),
                                 client_uuid=self._uuid(contribution, "video"))
        if slot["upload_state"] == "complete":
            return slot
        return self._write(slot, source)

    def _write(self, slot, path: Path):
        if slot["upload_state"] == "partial":
            self.media.path(slot).unlink(missing_ok=True)
        offset = 0
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                self.media.append(slot["id"], chunk, offset)
                offset += len(chunk)
        return self.media.finalize(slot["id"])

    def _has_job(self, capture_id) -> bool:
        with self.analysis._connect() as conn:
            return conn.execute("SELECT 1 FROM analysis_jobs WHERE capture_id = ?",
                                (capture_id,)).fetchone() is not None

    @staticmethod
    def _uuid(contribution, suffix) -> str:
        return f"scan:{contribution['id']}:{suffix}"
