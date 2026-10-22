#!/usr/bin/env python3
"""Seed the field app's local store with captures made from real crow audio.

The app is local-first and push-only, so there is no way to put test data in
front of it from the server side — the list, the map and the sync path all read
the phone's own SQLite. This writes into that store directly: real recordings
from the archive corpus in data/, converted to the same 48 kHz mono 16-bit WAV the
recorder produces, placed around a center point, and left in the `local` state.

Because the audio is real, tapping Sync afterwards is a genuine end-to-end
exercise: the files upload, the worker analyzes them, and actual detected calls
come back — which silence recorded off a desk can never test.

    python3 mobile/tools/seed_captures.py --count 12
    python3 mobile/tools/seed_captures.py --radius 300
    python3 mobile/tools/seed_captures.py --clear

Needs the phone attached with USB debugging, and ffmpeg on the host.

The center comes from MAP_CENTER_LAT / MAP_CENTER_LNG — in the environment or in
`mobile/.env`, which is gitignored. Same variables the backend uses, and for the
same reason: nothing location-specific belongs in the source. Copy
`mobile/.env.example` to `mobile/.env` and fill it in, or pass --center.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS_DB = REPO / "data" / "corvid.db"

PACKAGE = "com.cawtalker.field"
DB_ON_DEVICE = "files/SQLite/cawtalker.db"
AUDIO_ON_DEVICE = "cache"
STAGING = "/data/local/tmp/cawtalker-seed"

ENV_FILE = REPO / "mobile" / ".env"
# What gets written into a seeded capture's notes. Lookups match on SEED_PREFIX
# so rows written under the marker's older wording are still found by --clear.
SEED_MARKER = "seeded from the archive corpus"
SEED_PREFIX = "seeded from"


class SeedError(RuntimeError):
    pass


def load_env_file(path: Path) -> None:
    """Read KEY=value lines into the environment, without clobbering real env vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def resolve_center(explicit: str | None) -> tuple[float, float]:
    """--center wins, then the environment. There is no built-in location."""
    if explicit:
        latitude, longitude = (float(part) for part in explicit.split(","))
        return latitude, longitude

    load_env_file(ENV_FILE)
    latitude = os.environ.get("MAP_CENTER_LAT")
    longitude = os.environ.get("MAP_CENTER_LNG")
    if not latitude or not longitude:
        raise SeedError(
            "no center set. Copy mobile/.env.example to mobile/.env and set "
            "MAP_CENTER_LAT / MAP_CENTER_LNG, or pass --center LAT,LNG"
        )
    return float(latitude), float(longitude)


def adb(*args: str, binary: bool = False) -> bytes | str:
    command = ["adb", *args]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise SeedError(f"{' '.join(command)}\n{result.stderr.decode(errors='replace')}")
    return result.stdout if binary else result.stdout.decode(errors="replace")


def run_as(*args: str, binary: bool = False) -> bytes | str:
    """Run a command inside the app's data dir.

    Only works against a debuggable build. A release install — what `make
    install` puts on a phone for field use — refuses `run-as` outright, so say
    so plainly instead of failing with an opaque adb error.
    """
    try:
        return adb("shell", "run-as", PACKAGE, *args, binary=binary)
    except SeedError as error:
        if "not debuggable" in str(error):
            raise SeedError(
                "the phone has a release build installed, which Android does not let\n"
                "  us reach into. Seeding needs a debuggable build:\n"
                "      make android        # debug build (needs Metro running)\n"
                "  then seed, then `make install` again before going out."
            ) from error
        raise


@dataclass
class Recording:
    source_ref: str
    species: str
    call_type: str | None
    quality: str | None
    recordist: str | None
    path: Path


def pick_recordings(count: int, species: str | None, rng: random.Random) -> list[Recording]:
    """Corpus recordings that we actually hold audio for."""
    if not CORPUS_DB.exists():
        raise SeedError(f"no corpus DB at {CORPUS_DB} — is data/ populated?")

    conn = sqlite3.connect(CORPUS_DB)
    conn.row_factory = sqlite3.Row
    query = (
        "SELECT source_ref, species, call_type, quality, recordist, file_path "
        "FROM recordings WHERE source_ref IS NOT NULL AND file_path IS NOT NULL"
    )
    params: list[str] = []
    if species:
        query += " AND species LIKE ?"
        params.append(f"%{species}%")

    found: list[Recording] = []
    for row in conn.execute(query, params):
        audio = Path(row["file_path"])
        if audio.exists():
            found.append(
                Recording(
                    source_ref=row["source_ref"],
                    species=row["species"] or "unknown",
                    call_type=row["call_type"],
                    quality=row["quality"],
                    recordist=row["recordist"],
                    path=audio,
                )
            )
    conn.close()

    if not found:
        raise SeedError(
            "no downloaded audio in the corpus"
            + (f" for species like '{species}'" if species else "")
        )
    rng.shuffle(found)
    # Sampling with replacement when the corpus is small beats refusing to run.
    return [found[i % len(found)] for i in range(count)]


def to_capture_wav(source: Path, destination: Path, max_seconds: float) -> tuple[int, float]:
    """Transcode to exactly what the recorder produces. Returns (bytes, seconds)."""
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", str(source),
            "-t", str(max_seconds),
            "-ac", "1", "-ar", "48000", "-sample_fmt", "s16",
            str(destination),
        ],
        check=True,
        capture_output=True,
    )
    with wave.open(str(destination)) as handle:
        seconds = handle.getnframes() / handle.getframerate()
    return destination.stat().st_size, seconds


def scatter(center: tuple[float, float], radius_m: float, rng: random.Random) -> tuple[float, float]:
    """A point uniformly inside a circle, so markers don't pile up on one roof."""
    latitude, longitude = center
    distance = radius_m * math.sqrt(rng.random())
    bearing = rng.random() * 2 * math.pi
    north = distance * math.cos(bearing)
    east = distance * math.sin(bearing)
    return (
        latitude + north / 111_320.0,
        longitude + east / (111_320.0 * math.cos(math.radians(latitude))),
    )


def pull_database(workdir: Path) -> Path:
    """Copy the app's SQLite file to the host, folding in the write-ahead log."""
    local = workdir / "cawtalker.db"
    data = run_as("cat", DB_ON_DEVICE, binary=True)
    if not data:
        raise SeedError(
            "the app's database is empty or missing — launch the app once first"
        )
    local.write_bytes(data)

    for suffix in ("-wal", "-shm"):
        try:
            extra = run_as("cat", DB_ON_DEVICE + suffix, binary=True)
        except SeedError:
            continue
        if extra:
            (workdir / f"cawtalker.db{suffix}").write_bytes(extra)

    # Opening it here replays the WAL; checkpointing folds it into the main file
    # so a single push carries everything and the stale -wal can be discarded.
    conn = sqlite3.connect(local)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
    conn.close()
    return local


def push_database(local: Path) -> None:
    adb("shell", "mkdir", "-p", STAGING)
    adb("push", str(local), f"{STAGING}/cawtalker.db")
    run_as("cp", f"{STAGING}/cawtalker.db", DB_ON_DEVICE)
    # The pushed file already contains everything; a leftover WAL would be older
    # than it and would silently undo the seed on next open.
    for suffix in ("-wal", "-shm"):
        run_as("rm", "-f", DB_ON_DEVICE + suffix)
    adb("shell", "rm", "-rf", STAGING)


def insert_captures(db: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(db)
    conn.executemany(
        """INSERT INTO captures (uuid, media_uuid, name, recorded_at, duration_ms,
                                 sample_rate, channels, audio_path, bytes, latitude,
                                 longitude, location_name, notes, sync_state,
                                 uploaded_bytes, attempts)
           VALUES (:uuid, :media_uuid, :name, :recorded_at, :duration_ms, 48000, 1,
                   :audio_path, :bytes, :latitude, :longitude, NULL, :notes,
                   'local', 0, 0)""",
        rows,
    )
    conn.commit()
    conn.close()


def clear_seeded() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        db = pull_database(workdir)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        # `keep` is the user's own mark for "this is real". Never delete one,
        # even if it somehow carries the seed marker — losing a field recording
        # to a reseed is the failure this flag exists to prevent.
        kept = conn.execute(
            "SELECT COUNT(*) FROM captures WHERE keep = 1 AND notes LIKE ?",
            (f"{SEED_PREFIX}%",),
        ).fetchone()[0]
        doomed = [
            row["audio_path"]
            for row in conn.execute(
                "SELECT audio_path FROM captures WHERE notes LIKE ? AND COALESCE(keep, 0) = 0",
                (f"{SEED_PREFIX}%",),
            )
        ]
        conn.execute(
            "DELETE FROM captures WHERE notes LIKE ? AND COALESCE(keep, 0) = 0",
            (f"{SEED_PREFIX}%",),
        )
        if kept:
            print(f"  keeping {kept} marked capture(s) that would otherwise match")
        conn.commit()
        conn.close()
        push_database(db)

    for path in doomed:
        try:
            run_as("rm", "-f", path.replace(f"/data/user/0/{PACKAGE}/", ""))
        except SeedError:
            pass
    return len(doomed)


def report_at_risk() -> None:
    """Warn about kept captures that exist only on this phone.

    A `keep` flag protects against the seeder, but nothing protects against
    `adb uninstall` or clearing app data. The only real protection is a copy on
    the server, so say plainly which captures do not have one yet.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db = pull_database(Path(tmp))
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT COUNT(*) FROM captures "
                "WHERE COALESCE(keep, 0) = 1 AND sync_state != 'synced'"
            ).fetchone()[0]
            if rows:
                print(f"WARNING: {rows} kept capture(s) are not synced — "
                      "they exist only on this phone. Sync before wiping anything.")
    except SeedError:
        pass


def seed_clip(clip: Path, center: tuple[float, float]) -> int:
    """Put one long, varied recording on the phone.

    Twelve short clips prove the plumbing. One two-minute recording is what
    actually exercises the parts that only matter at length: a waveform with
    structure, a trim worth dragging, "skip to call" with somewhere to skip to,
    and an analysis that returns a spread of call types rather than three
    identical caws.
    """
    if not clip.exists():
        print(f"no clip at {clip} — build one with make_variety_clip.py", file=sys.stderr)
        return 1

    manifest_path = clip.with_suffix(".sources.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    segments = manifest.get("segments", [])
    # Attribution travels with the capture: the sources are CC-licensed, and a
    # synthetic clip whose provenance was left behind on the build machine is one
    # nobody can publish or explain a surprising detection in.
    credits = ", ".join(
        f"#{s['source_ref']} ({s['call_type']}, rec. {s['recordist']})" for s in segments
    )

    with wave.open(str(clip), "rb") as handle:
        seconds = handle.getnframes() / handle.getframerate()

    device_dir = f"/data/user/0/{PACKAGE}/{AUDIO_ON_DEVICE}"
    name = f"seeded_{secrets.token_hex(8)}.wav"
    adb("shell", "mkdir", "-p", STAGING)
    adb("push", str(clip), f"{STAGING}/{name}")
    run_as("cp", f"{STAGING}/{name}", f"{AUDIO_ON_DEVICE}/{name}")
    adb("shell", "rm", "-rf", STAGING)

    row = {
        "uuid": secrets.token_hex(16),
        "media_uuid": secrets.token_hex(16),
        "name": f"Variety sample · {len(segments) or '?'} call types",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int(seconds * 1000),
        "audio_path": f"{device_dir}/{name}",
        "bytes": clip.stat().st_size,
        "latitude": center[0],
        "longitude": center[1],
        "notes": f"{SEED_MARKER} variety clip — {credits}" if credits
                 else f"{SEED_MARKER} variety clip",
    }

    with tempfile.TemporaryDirectory() as tmp:
        db = pull_database(Path(tmp))
        insert_captures(db, [row])
        push_database(db)

    print(f"seeded 1 clip: {seconds:.0f}s, {len(segments)} call types")
    for s in segments:
        print(f"  {s['start_sec']:6.1f}–{s['end_sec']:6.1f}s  {s['call_type']}")
    print("\nRestart the app to see it.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=12, help="how many captures (default 12)")
    parser.add_argument("--center",
                        help="LAT,LNG to scatter around (default: MAP_CENTER_LAT/LNG)")
    parser.add_argument("--radius", type=float, default=250.0,
                        help="scatter radius in metres (default 250)")
    parser.add_argument("--days", type=float, default=7.0,
                        help="spread recording times over this many past days (default 7)")
    parser.add_argument("--max-seconds", type=float, default=20.0,
                        help="trim each clip to at most this long (default 20)")
    parser.add_argument("--species", help="only use recordings whose species matches")
    parser.add_argument("--seed", type=int, help="fix the RNG for a reproducible run")
    parser.add_argument("--clip", type=Path,
                        help="seed one long clip built by make_variety_clip.py "
                             "instead of many short ones")
    parser.add_argument("--clear", action="store_true",
                        help="remove previously seeded captures and exit")
    args = parser.parse_args()

    if not shutil.which("adb"):
        print("adb is not on PATH", file=sys.stderr)
        return 1
    if not shutil.which("ffmpeg"):
        print("ffmpeg is not on PATH", file=sys.stderr)
        return 1
    if not adb("devices").strip().splitlines()[1:]:
        print("no device attached", file=sys.stderr)
        return 1

    if args.clear:
        report_at_risk()
        removed = clear_seeded()
        print(f"removed {removed} seeded capture(s)")
        print("restart the app to see the change")
        return 0

    latitude, longitude = resolve_center(args.center)
    rng = random.Random(args.seed)

    if args.clip:
        return seed_clip(args.clip, (latitude, longitude))

    recordings = pick_recordings(args.count, args.species, rng)

    print(f"seeding {len(recordings)} capture(s) around {latitude:.5f}, {longitude:.5f}")
    # The app writes recordings into its cache dir; seeded ones live beside them
    # so nothing has to special-case where a capture's audio came from.
    device_dir = f"/data/user/0/{PACKAGE}/{AUDIO_ON_DEVICE}"
    adb("shell", "mkdir", "-p", STAGING)

    rows: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for index, recording in enumerate(recordings):
            name = f"seeded_{secrets.token_hex(8)}.wav"
            local_wav = workdir / name
            size, seconds = to_capture_wav(recording.path, local_wav, args.max_seconds)

            adb("push", str(local_wav), f"{STAGING}/{name}")
            run_as("cp", f"{STAGING}/{name}", f"{AUDIO_ON_DEVICE}/{name}")

            spot_lat, spot_lng = scatter((latitude, longitude), args.radius, rng)
            when = datetime.now(timezone.utc) - timedelta(
                seconds=rng.random() * args.days * 86400
            )
            detail = ", ".join(
                part for part in (recording.call_type, f"quality {recording.quality}"
                                  if recording.quality else None) if part
            )
            rows.append({
                "uuid": secrets.token_hex(16),
                "media_uuid": secrets.token_hex(16),
                "name": f"#{recording.source_ref} · {recording.call_type or 'call'}",
                "recorded_at": when.isoformat(),
                "duration_ms": int(seconds * 1000),
                "audio_path": f"{device_dir}/{name}",
                "bytes": size,
                "latitude": spot_lat,
                "longitude": spot_lng,
                "notes": (
                    f"{SEED_MARKER} #{recording.source_ref} — {recording.species}"
                    + (f" ({detail})" if detail else "")
                    + (f", rec. {recording.recordist}" if recording.recordist else "")
                ),
            })
            print(f"  {index + 1:2}. #{recording.source_ref:<8} {recording.species:<24} "
                  f"{seconds:5.1f}s  {size / 1024:6.0f} KB")

        adb("shell", "rm", "-rf", STAGING)

        db = pull_database(workdir)
        insert_captures(db, rows)
        push_database(db)

    print(f"\nseeded {len(rows)} capture(s). Restart the app to see them:")
    print(f"  adb shell am force-stop {PACKAGE}")
    print("They are in the 'local' state — tap Sync to upload and analyze for real.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SeedError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
