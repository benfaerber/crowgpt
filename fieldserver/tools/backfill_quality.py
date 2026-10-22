"""Measure audio quality for every capture that has none recorded.

The worker writes `capture_quality` as it analyses; everything analysed before
the table existed has audio and no numbers. This measures it — retroactive over
the whole corpus, because quality needs nothing from the recordist.

Runs in the BirdNET venv like the worker (the fieldserver venv has no numpy),
and decodes through the same `to_wav` so the numbers here and the numbers the
worker writes are identical by construction:

    ../pipelines/representation/.venv-birdnet/bin/python tools/backfill_quality.py           # say what it would do
    ../pipelines/representation/.venv-birdnet/bin/python tools/backfill_quality.py --apply   # do it
    ../pipelines/representation/.venv-birdnet/bin/python tools/backfill_quality.py --apply --all   # remeasure everything

Doubles as the audit: with nothing to do it prints so, and a capture that keeps
reappearing here is one whose measurement keeps failing.
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
REPO = FIELDSERVER.parent
sys.path.insert(0, str(FIELDSERVER / "src"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from fieldserver.stores.media import MediaStore  # noqa: E402
from fieldserver.stores.quality import QualityStore  # noqa: E402

from analyzer import birdnet, quality  # noqa: E402
from crowgpt.progress import Run  # noqa: E402


def worklist(qualities, remeasure_all: bool) -> list[int]:
    if not remeasure_all:
        return qualities.missing()
    with qualities._connect() as conn:  # noqa: SLF001 — a tool, on its own database
        return [r["capture_id"] for r in conn.execute(
            "SELECT DISTINCT capture_id FROM media "
            "WHERE kind = 'audio' AND upload_state = 'complete' "
            "ORDER BY capture_id")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually measure; without it, only report")
    parser.add_argument("--all", action="store_true",
                        help="remeasure every capture with complete audio, "
                             "not just the ones missing a row")
    parser.add_argument("--db", default=os.environ.get(
        "FIELD_DB", FIELDSERVER / "instance" / "field.db"))
    args = parser.parse_args()

    db = Path(args.db)
    media = MediaStore(db, db.parent / "media")
    qualities = QualityStore(db)

    ids = worklist(qualities, args.all)
    if not ids:
        print("nothing to do — every capture with complete audio has a quality row")
        return 0

    print(f"{len(ids)} capture(s) to measure: {ids}")
    if not args.apply:
        print("dry run — pass --apply to measure")
        return 0

    failed = []
    run = Run("quality backfill", ["measure"])
    with run.stage("measure") as stage:
        for index, capture_id in enumerate(ids, start=1):
            stage.update(index - 1, len(ids),
                         extra=f"capture {capture_id}, {len(failed)} failed")
            row = media.complete_audio_for(capture_id)
            if not row:
                # `missing()` requires complete audio, so this is --all racing a
                # deletion, not a corpus problem.
                failed.append(capture_id)
                print(f"  [{index}/{len(ids)}] capture {capture_id}: no complete audio")
                continue
            wav = None
            try:
                wav = birdnet.to_wav(media.path(row))
                metrics = quality.measure(wav)
                qualities.upsert(capture_id, row["id"], metrics)
                snr = metrics["band_snr_db"]
                print(f"  [{index}/{len(ids)}] capture {capture_id}: "
                      f"SNR {'unmeasurable' if snr is None else f'{snr:.1f} dB'}, "
                      f"floor {metrics['noise_floor_band_dbfs']:.1f} dBFS, "
                      f"{metrics['clip_events']} clip event(s)")
            except Exception as exc:  # noqa: BLE001 — one bad file must not stop the sweep
                failed.append(capture_id)
                print(f"  [{index}/{len(ids)}] capture {capture_id}: FAILED — {exc}")
            finally:
                if wav:
                    wav.unlink(missing_ok=True)

    done = len(ids) - len(failed)
    run.note(f"{done} measured, {len(failed)} failed"
             + (f": {failed}" if failed else ""))
    print(f"\n{done} measured, {len(failed)} failed")
    if failed:
        print(f"failed, and still missing: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
