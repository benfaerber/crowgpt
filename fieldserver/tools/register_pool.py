"""Register a listening pool built by an experiment, from this venv.

    uv run --project fieldserver python fieldserver/tools/register_pool.py POOL.json

Why a tool and not an HTTP POST from the experiment: the route exists and works,
but reaching it means the experiment has to hold the operator secret, and a
sitting is built by a script an agent starts. This runs in fieldserver's own
venv against a database Alembic has already migrated, so it needs no token and no
server to be up — the same reasoning `training.py` gives for reading crowgpt's
progress off disk rather than having crowgpt push it.

It still writes through `ListeningStore`, so the pool is validated by the same
code the API uses and no SQL is duplicated here.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fieldserver.core.paths import database_path  # noqa: E402
from fieldserver.stores.listening import ListeningStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pool", type=Path, help="pool.json from an experiment")
    parser.add_argument("--db", type=Path, default=None,
                        help="database to write to (default: the served one)")
    parser.add_argument("--cooldown", type=int, default=None, metavar="MINUTES",
                        help="minimum gap between doses; omit for none")
    parser.add_argument("--dose-size", type=int, default=None, metavar="N",
                        help="trials handed out at once; rounded down to whole "
                             "balanced blocks, so 15 on blocks of 10 serves 10")
    parser.add_argument("--update", action="store_true",
                        help="change only the pacing (--cooldown, --dose-size) on "
                             "the existing pool of this name, leaving its trials "
                             "and answers alone")
    parser.add_argument("--replace", action="store_true",
                        help="drop an existing pool of the same name first; "
                             "refused if any of its trials have been answered")
    args = parser.parse_args()

    payload = json.loads(args.pool.read_text())

    if args.update:
        # Pacing is not the measurement, so these are the properties that can move
        # under a pool being graded.
        store = ListeningStore(database_path(args.db))
        existing = store.pool_by_name(payload["name"])
        if not existing:
            print(f"no pool named {payload['name']!r}", file=sys.stderr)
            return 1
        try:
            pool = store.set_pacing(
                existing["id"],
                cooldown_minutes=args.cooldown if "--cooldown" in sys.argv else ...,
                dose_size=args.dose_size if args.dose_size is not None else ...)
        except ValueError as error:
            print(f"refused: {error}", file=sys.stderr)
            return 1
        print(f"pool {pool['id']}: doses of {pool['dose_size']}, "
              f"cooldown {pool['cooldown_minutes'] or 'none'} minute(s)")
        return 0

    clip_dir = Path(payload["clip_dir"])
    if not clip_dir.is_dir():
        # Checked here rather than in the store: the store is happy to record a
        # path, and the failure it would otherwise produce is a 404 on the first
        # clip of the first dose — after the pool exists and the name is taken.
        print(f"clip_dir does not exist: {clip_dir}", file=sys.stderr)
        return 1

    missing = sorted({name for trial in payload["trials"]
                      for key in ("anchor_clip", "first_clip", "second_clip")
                      if (name := trial.get(key)) and not (clip_dir / name).exists()})
    if missing:
        print(f"{len(missing)} clip(s) named by trials are not on disk, "
              f"first few: {missing[:5]}", file=sys.stderr)
        return 1

    store = ListeningStore(database_path(args.db))
    if args.replace:
        existing = store.pool_by_name(payload["name"])
        if existing:
            if existing["answered"]:
                # Never silently: a pool with answers in it is a measurement, and
                # a rebuild that discards graded trials is the thing 0039 burned
                # 360 bouts learning to avoid.
                print(f"refused: pool {existing['id']} has "
                      f"{existing['answered']} answered trial(s) — rename the "
                      f"new pool rather than discarding a measurement",
                      file=sys.stderr)
                return 1
            store.delete_pool(existing["id"])
            print(f"replaced pool {existing['id']} ({existing['trials']} "
                  f"unanswered trials dropped)")
    try:
        pool = store.create_pool(
            name=payload["name"], question=payload["question"],
            clip_dir=str(clip_dir), trials=payload["trials"],
            dose_size=args.dose_size or int(payload.get("dose_size", 10)),
            reveal_at=payload.get("reveal_at"), spec=payload.get("spec"),
            cooldown_minutes=args.cooldown)
    except ValueError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1

    print(f"pool {pool['id']}: {pool['name']}")
    print(f"  {pool['trials']} trials in doses of {pool['dose_size']}, "
          f"results at {pool['reveal_at']}")
    if pool["cooldown_minutes"]:
        print(f"  {pool['cooldown_minutes']} minute(s) between doses")
    print("  grade at /listen/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
