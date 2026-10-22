"""Would storing FLAC instead of WAV be free, and how much would it save?

Storage is the only cost in this project that grows: two captures a day per
contributor is ~2.4 GB a year, permanently, and CPU and bandwidth are noise
beside it. FLAC is the obvious lever — if it is genuinely lossless on this
audio then it is a pure win, and if it is not, nothing else about it matters.

So two questions, in order:

  1. Do the samples survive exactly? Anything less makes the rest moot. A
     corpus is a measurement instrument, and 0004 already showed detection
     confidence collapsing with noise — a codec that alters the waveform even
     slightly would move numbers nobody would think to re-check.

  2. How much does it actually save *on this audio*? Published FLAC ratios are
     measured on music, which is loud and dense. Field recordings peak around
     -30 dBFS with long quiet stretches, and quiet audio has fewer bits of
     entropy per sample. The saving here should be better than the brochure,
     and the seeded archive clips are the control: louder, denser, and a
     preview of what a corpus of recordings taken closer to the birds would do.

Encoding goes through ffmpeg, which the analyzer already depends on, rather
than the `flac` binary, which is not installed and would be one more thing to
put on a server.
"""

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import DEFAULT_DB, media_dir  # noqa: E402

# ffmpeg's FLAC levels run 0-12. 5 is the default; 8 is where the published
# advice stops; 12 is included to show where the curve flattens, because "use
# the slowest setting" is a decision worth making on evidence.
LEVELS = (5, 8, 12)


def corpus() -> list[dict]:
    """Every complete audio file, with what the capture is, from the database."""
    db = Path(os.environ.get("FIELD_DB", DEFAULT_DB))
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT m.storage_ref, m.bytes, c.id AS capture_id, c.keep, "
            "       c.duration_sec, c.name "
            "  FROM media m JOIN captures c ON c.id = m.capture_id "
            " WHERE m.kind = 'audio' AND m.upload_state = 'complete' AND m.bytes > 0 "
            " ORDER BY c.id"
        ).fetchall()
    out = []
    for row in rows:
        path = media_dir() / row["storage_ref"]
        if path.exists() and path.suffix.lower() == ".wav":
            out.append({**dict(row), "path": path})
    return out


def pcm_digest(path: Path) -> str:
    """The samples, hashed, with the container taken out of the question.

    Both sides are decoded by the same tool to raw signed 16-bit little-endian,
    so this compares audio to audio rather than file to file — a WAV header
    differing by a LIST chunk is not a loss of anything.
    """
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-acodec",
         "pcm_s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    return hashlib.sha256(raw).hexdigest()


def encode(source: Path, target: Path, level: int) -> float:
    started = time.perf_counter()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source),
         "-compression_level", str(level), str(target)],
        check=True, capture_output=True,
    )
    return time.perf_counter() - started


def decode_seconds(path: Path) -> float:
    started = time.perf_counter()
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-acodec",
         "pcm_s16le", "-"],
        check=True, capture_output=True,
    )
    return time.perf_counter() - started


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")

    files = corpus()
    if not files:
        raise SystemExit("no WAV audio found — is FIELD_MEDIA set?")

    work = Path(tempfile.mkdtemp(prefix="flac-"))
    totals = {level: {"wav": 0, "flac": 0, "seconds": 0.0} for level in LEVELS}
    groups = {"kept": {"wav": 0, "flac": 0, "n": 0}, "other": {"wav": 0, "flac": 0, "n": 0}}
    identical = 0
    decode_wav = 0.0
    decode_flac = 0.0
    audio_seconds = 0.0

    print(f"{len(files)} audio files, {sum(f['bytes'] for f in files) / 1e6:.0f} MB of WAV\n")

    for index, item in enumerate(files, start=1):
        source = item["path"]
        original = pcm_digest(source)
        for level in LEVELS:
            target = work / f"{source.stem}-{level}.flac"
            totals[level]["seconds"] += encode(source, target, level)
            totals[level]["wav"] += source.stat().st_size
            totals[level]["flac"] += target.stat().st_size
            if level == LEVELS[1]:
                # Losslessness is a property of the format, not of the level —
                # checked once per file at the level being recommended.
                if pcm_digest(target) == original:
                    identical += 1
                bucket = groups["kept" if item["keep"] else "other"]
                bucket["wav"] += source.stat().st_size
                bucket["flac"] += target.stat().st_size
                bucket["n"] += 1
                decode_wav += decode_seconds(source)
                decode_flac += decode_seconds(target)
                audio_seconds += item["duration_sec"] or 0
            target.unlink(missing_ok=True)
        if index % 20 == 0:
            print(f"  … {index}/{len(files)}")

    print("\ncompression by level")
    for level in LEVELS:
        row = totals[level]
        ratio = row["flac"] / row["wav"]
        print(f"  level {level:>2}: {ratio * 100:.1f}% of WAV "
              f"({(1 - ratio) * 100:.1f}% saved), "
              f"{row['seconds'] / len(files) * 1000:.0f} ms per file to encode")

    print("\nby what the audio is")
    for name, row in groups.items():
        if row["n"] == 0:
            continue
        ratio = row["flac"] / row["wav"]
        label = "kept (real field recordings)" if name == "kept" else "seeded and test uploads"
        print(f"  {label:<30} n={row['n']:<3} {ratio * 100:.1f}% of WAV")

    print(f"\nlossless: {identical}/{len(files)} files decode to identical samples")
    print(f"decode to PCM: WAV {decode_wav / audio_seconds:.4f} s per audio-second, "
          f"FLAC {decode_flac / audio_seconds:.4f}")

    # What it means for the thing that actually costs money.
    saved = 1 - groups["kept"]["flac"] / max(groups["kept"]["wav"], 1)
    per_user_year_wav = 3.28e6 * 2 * 365 / 1e9
    print(f"\nper contributor per year at 2 captures a day: "
          f"{per_user_year_wav:.2f} GB as WAV, "
          f"{per_user_year_wav * (1 - saved):.2f} GB as FLAC")

    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
