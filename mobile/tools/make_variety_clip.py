#!/usr/bin/env python3
"""Build one ~2-minute clip containing a deliberate variety of crow calls.

Seeding twelve short clips proves the *plumbing* works. It does not exercise the
things a single long recording does: a waveform with structure worth looking at,
a trim worth dragging, "skip to call" with somewhere to skip to, and an analysis
that returns a spread of call types rather than three identical caws. This makes
one such recording, from real archive material, with each call type
represented.

    python3 mobile/tools/make_variety_clip.py
    python3 mobile/tools/make_variety_clip.py --seconds 90 --out /tmp/variety.wav

Writes a WAV in the recorder's own format (48 kHz mono 16-bit) plus a sidecar
`.sources.json` naming every source segment — which recording it came from, its
recordist, its licence and where it sits in the clip.

That manifest is not paperwork. Recordists are owed attribution, and a
synthetic clip whose provenance has been lost is one you can never cite or
explain a surprising detection in.

Needs ffmpeg on the host, and the corpus DB + audio under `data/`.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS_DB = REPO / "data" / "corvid.db"
DEFAULT_OUT = REPO / "data" / "audio" / "variety_clip.wav"

SAMPLE_RATE = 48000
CHANNELS = 1
SAMPLE_WIDTH = 2

# The call types worth having represented, in the order they appear in the clip.
# Ordered loosest-to-most-specific so the common "call" doesn't swallow the
# slots: `call` matches almost every recording's tag list, and picking it first
# would leave nothing distinctive behind it.
WANTED = [
    "alarm call",
    "flight call",
    "song",
    "begging call",
    "rattle",
    "call",
]

# A beat of near-silence between segments, so calls are separable and the
# analyzer doesn't read the join as one continuous vocalisation.
GAP_SECONDS = 1.2


class ClipError(RuntimeError):
    pass


@dataclass
class Segment:
    call_type: str
    source_ref: str
    recordist: str
    license: str
    page_url: str
    start_sec: float
    end_sec: float


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise ClipError("ffmpeg is not on PATH — needed to decode the mp3 sources")


def pick_sources(conn: sqlite3.Connection, wanted: list[str], rng: random.Random):
    """One recording per call type, longest first so there is material to cut.

    Matching is substring-based because the archive tags are free-form lists
    ("alarm call, call, flight call"), so an exact match would discard most of
    the corpus. Each recording is used at most once — the same bird twice is not
    variety.
    """
    chosen: dict[str, sqlite3.Row] = {}
    used: set[str] = set()

    for call_type in wanted:
        row = conn.execute(
            """
            SELECT source_ref, call_type, recordist, license, page_url, file_path, length
            FROM recordings
            WHERE downloaded = 1 AND species = 'American Crow'
              AND call_type LIKE ? AND file_path IS NOT NULL
              AND source_ref NOT IN (%s)
            ORDER BY quality, LENGTH(call_type), RANDOM()
            LIMIT 1
            """ % (",".join("?" * len(used)) or "''"),
            (f"%{call_type}%", *used),
        ).fetchone()
        if row and Path(row["file_path"]).exists():
            chosen[call_type] = row
            used.add(row["source_ref"])

    if not chosen:
        raise ClipError(
            "no downloaded American Crow recordings found — the corpus must supply them first"
        )
    return chosen


def decode(path: Path, out: Path, offset: float, seconds: float) -> None:
    """Decode a slice to the recorder's exact format, so the app sees a real capture."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
         "-ss", f"{offset:.2f}", "-t", f"{seconds:.2f}", "-i", str(path),
         "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16",
         str(out)],
        check=True,
    )


def read_frames(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != SAMPLE_RATE or handle.getnchannels() != CHANNELS:
            raise ClipError(f"{path} decoded to the wrong format")
        return handle.readframes(handle.getnframes())


def build(seconds: float, out: Path, seed: int | None) -> list[Segment]:
    require_ffmpeg()
    if not CORPUS_DB.exists():
        raise ClipError(f"no corpus database at {CORPUS_DB}")

    rng = random.Random(seed)
    conn = sqlite3.connect(CORPUS_DB)
    conn.row_factory = sqlite3.Row
    sources = pick_sources(conn, WANTED, rng)

    gap = b"\x00" * int(SAMPLE_RATE * GAP_SECONDS) * SAMPLE_WIDTH
    total_gap = GAP_SECONDS * (len(sources) - 1)
    per_segment = max(4.0, (seconds - total_gap) / len(sources))

    segments: list[Segment] = []
    frames: list[bytes] = []
    position = 0.0

    with tempfile.TemporaryDirectory() as tmp:
        for index, (call_type, row) in enumerate(sources.items()):
            piece = Path(tmp) / f"{index}.wav"
            # Skip the first couple of seconds: archive recordings often open
            # with handling noise or the recordist announcing the species.
            decode(Path(row["file_path"]), piece, offset=2.0, seconds=per_segment)
            data = read_frames(piece)
            if not data:
                continue
            duration = len(data) / SAMPLE_WIDTH / SAMPLE_RATE

            if frames:
                frames.append(gap)
                position += GAP_SECONDS
            frames.append(data)
            segments.append(Segment(
                call_type=call_type,
                source_ref=row["source_ref"],
                recordist=row["recordist"] or "unknown",
                license=row["license"] or "unknown",
                page_url=row["page_url"] or "",
                start_sec=round(position, 2),
                end_sec=round(position + duration, 2),
            ))
            position += duration

    if not segments:
        raise ClipError("every source decoded to nothing — is ffmpeg working?")

    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"".join(frames))

    manifest = out.with_suffix(".sources.json")
    manifest.write_text(json.dumps({
        "clip": out.name,
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "duration_sec": round(position, 2),
        "note": "Built from archive recordings; each segment keeps its own "
                "recordist. Attribution travels with the clip.",
        "segments": [asdict(s) for s in segments],
    }, indent=2) + "\n")

    return segments


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=float, default=120.0,
                        help="target clip length (default 120)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=None,
                        help="fix the source choice so the clip is reproducible")
    args = parser.parse_args()

    try:
        segments = build(args.seconds, args.out, args.seed)
    except (ClipError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    total = segments[-1].end_sec
    print(f"{args.out}  ({total:.1f}s, {len(segments)} call types)")
    for s in segments:
        print(f"  {s.start_sec:6.1f}–{s.end_sec:6.1f}s  {s.call_type:<14} "
              f"#{s.source_ref} · {s.recordist}")
    print(f"\nsources: {args.out.with_suffix('.sources.json')}")
    print("seed it onto the phone with:")
    print(f"  python3 mobile/tools/seed_captures.py --clip {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
