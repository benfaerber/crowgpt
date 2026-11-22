"""The recordings and spans 0112-0114 read. Stdlib + numpy only, so every venv can import it."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0112-representations"
WINDOWS = CACHE / "windows"
DB = DATA_DIR / "corvid.db"

EXP102 = REPO / "experiments" / "0102-archive-remarks-semantics"
EXP103 = REPO / "experiments" / "0103-caw-level-and-posture-controls"
EXP104 = REPO / "experiments" / "0104-does-owl-vs-hawk-survive-perched"
EXP110 = REPO / "experiments" / "0110-which-contexts-are-readable-outside-the-archives"
ARCHIVE_CACHE = DATA_DIR / "experiments" / "0102-archive-remarks"
CAW_CACHE = DATA_DIR / "experiments" / "0103-caw-level"
CLIP_AUDIO = DATA_DIR / "experiments" / "0104-perched-posture" / "audio"

CONTEXTS = ("raptor_mobbing", "begging", "roost_gathering", "food_foraging", "flight_contact")
ARCHIVE_CONTEXT = {"owl_mobbing": "raptor_mobbing", "hawk_mobbing": "raptor_mobbing",
                   **{c: c for c in CONTEXTS[1:]}}
WINDOW_S = 3.0


def resolve_audio_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return path
    if "/data/" in raw:
        candidate = DATA_DIR / raw.split("/data/", 1)[1]
        if candidate.exists():
            return candidate
    return None


def database() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


@dataclass
class Recording:
    key: str
    path: Path
    group: str
    label: str
    extra: dict


class ArchiveSet:
    """The 423 witnessed archive recordings 0110's ArchiveHeads trains on, with the same filter."""

    def __init__(self):
        meta = json.loads((ARCHIVE_CACHE / "records.json").read_text())
        has_clean = np.load(ARCHIVE_CACHE / "features.npz")["has_clean"]
        committed = {(r["source"], str(r["source_ref"])): r["context"]
                     for r in json.loads((EXP102 / "labels.json").read_text()) if r["witnessed"]}
        db = database()
        self.recordings: list[Recording] = []
        for i, r in enumerate(meta):
            if not (r["slug"] == "american-crow" and r["witnessed"] and has_clean[i]
                    and r["context"] in ARCHIVE_CONTEXT
                    and committed.get((r["source"], str(r["source_ref"]))) == r["context"]):
                continue
            row = db.execute("SELECT file_path FROM recordings WHERE id = ?", (r["id"],)).fetchone()
            path = resolve_audio_path(row[0] if row else None)
            if path is None:
                continue
            self.recordings.append(Recording(
                f"a{r['id']}", path, (r["recordist"] or f"rec:{r['id']}").strip().lower(),
                ARCHIVE_CONTEXT[r["context"]],
                {"id": r["id"], "fine_context": r["context"], "pred_vocal": r["pred_vocal"],
                 "max_raptor_conf": r["max_raptor_conf"]}))


class OutsideSet:
    """0110's coded recordings from the rest of the corpus (ids and codes only)."""

    def __init__(self):
        labels = json.loads((EXP110 / "labels.json").read_text())["labels"]
        db = database()
        self.recordings: list[Recording] = []
        for label in labels:
            row = db.execute("SELECT file_path, recordist FROM recordings WHERE id = ?",
                             (label["recording_id"],)).fetchone()
            path = resolve_audio_path(row[0] if row else None)
            if path is None:
                continue
            observer = (row[1] or "").strip() or f"event:{label['event']}"
            self.recordings.append(Recording(f"o{label['recording_id']}", path, observer,
                                             label.get("context") or "", dict(label)))


class ClipSet:
    """0104's labelled video clips, by opaque key."""

    def __init__(self):
        labels = json.loads((EXP104 / "labels.json").read_text())
        files = {m["key"]: resolve_audio_path(m["file"])
                 for m in json.loads((CLIP_AUDIO.parent / "manifest.json").read_text())}
        self.recordings: list[Recording] = []
        for label in labels:
            path = files.get(label["key"])
            if path is not None and path.exists():
                self.recordings.append(Recording(f"v{label['key']}", path, label["channel"],
                                                 label.get("bucket") or "", dict(label)))


class CawList:
    """0103's segmented caws, in caws.json order."""

    def __init__(self):
        self.caws = json.loads((CAW_CACHE / "caws.json").read_text())
        db = database()
        self.paths = {}
        for rec_id in {c["rec_id"] for c in self.caws}:
            row = db.execute("SELECT file_path FROM recordings WHERE id = ?", (rec_id,)).fetchone()
            self.paths[rec_id] = resolve_audio_path(row[0] if row else None)


class WindowTable:
    """One recording's BirdNET windows, as the scan cached them."""

    def __init__(self, key: str):
        data = np.load(WINDOWS / f"{key}.npz")
        self.key = key
        self.start = data["start"]
        self.corvid = data["corvid"]
        self.american_crow = data["american_crow"]
        self.raptor = data["raptor"]
        self.other = data["other"]
        self.embedding = data["embedding"]

    @staticmethod
    def exists(key: str) -> bool:
        return (WINDOWS / f"{key}.npz").exists()

    def clean(self) -> np.ndarray:
        """0102's rule: a corvid at 0.25 or more, no raptor at 0.05."""
        return (self.corvid >= 0.25) & (self.raptor < 0.05)

    def pure(self) -> np.ndarray:
        """0103's rule: American Crow at 0.25 or more, nothing else detected at 0.05."""
        return (self.american_crow >= 0.25) & (self.other < 0.05)

    def crow(self) -> np.ndarray:
        return (self.corvid >= 0.25) | (self.american_crow >= 0.25)


@dataclass(frozen=True)
class Span:
    """A stretch of one file to embed. `isolated` spans are a single caw, heard alone."""

    span_id: str
    path: str
    start: float
    end: float
    isolated: bool = False


class SpanCatalogue:
    """Every span 0112 embeds: crow windows of the scanned recordings, 0103's caws, 0109's windows."""

    def __init__(self):
        self.windows = self._windows()
        self.caws = self._caws()
        self.segment_windows, self.segment_span = self._segments()

    @staticmethod
    def _windows() -> list[Span]:
        spans = []
        recordings = ArchiveSet().recordings + OutsideSet().recordings + ClipSet().recordings
        seen = set()
        for r in recordings:
            if r.key in seen or not WindowTable.exists(r.key):
                continue
            seen.add(r.key)
            table = WindowTable(r.key)
            for start in table.start[table.crow()]:
                spans.append(Span(f"{r.key}@{float(start):.2f}", str(r.path), float(start), float(start) + WINDOW_S))
        return spans

    @staticmethod
    def _caws() -> list[Span]:
        caws = CawList()
        return [Span(f"caw{i}", str(caws.paths[c["rec_id"]]), float(c["onset"]), float(c["offset"]), True)
                for i, c in enumerate(caws.caws)]

    @staticmethod
    def _segments() -> tuple[list[Span], list[str]]:
        """0109's segments in its own order (crowCount 1, 2 or 4), each mapped to its 3 s window."""
        import sys

        sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
        from corpus import LabelCorpus

        segments = [s for s in LabelCorpus().labeled_segments() if s.flags.get("crowCount") in (1, 2, 4)]
        unique, order = {}, []
        for s in segments:
            start = WINDOW_S * (int(s.start) // int(WINDOW_S))
            span_id = f"seg:{s.file_id}@{start:.0f}"
            unique.setdefault(span_id, Span(span_id, str(s.audio_path), start, start + WINDOW_S))
            order.append(span_id)
        return list(unique.values()), order

    def all(self) -> list[Span]:
        return self.windows + self.caws + self.segment_windows
