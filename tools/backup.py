"""Copy the irreplaceable half of this project somewhere else.

    make backup              the field recordings and the database
    make backup CORPUS=1     those plus data/, which is large and re-downloadable

Set BACKUP_DIR in the repo-root .env (see .env.example). Nothing is guessed: an
unset or missing destination is an error rather than a directory this creates,
because the failure being guarded against is a backup that silently went to the
wrong place and was never checked.

WHAT IS ACTUALLY IRREPLACEABLE, in order:

  fieldserver/instance/media/   the field recordings. A lost capture does not
                                come back, and the ★ Keep ones are the only real
                                crow audio in a corpus otherwise made of seeded
                                seeded archive clips.
  fieldserver/instance/field.db  every label, count, context tag, merge record
                                and Keep flag. The audio without this is a
                                directory of hex filenames.
  data/                         the seeded corpus and the corpus database. Big,
                                and replaceable by the corpus tooling given time
                                and the API key — so it is opt-in.

It COPIES. A backup that moves is not a backup, it is a relocation with one
copy, and the request for this said "moves" — worth saying plainly rather than
implementing.

Each run writes its own dated folder:

    BACKUP_DIR/cawtalker-20260729-1953/
        field.db          snapshotted through SQLite, integrity-checked
        media/            every recording
        data/             only with CORPUS=1
        MANIFEST.txt      what this is and how to put it back

Self-contained on purpose — a snapshot you have to reassemble from two places is
one you will get wrong at the worst moment. It does not cost a full copy each
time: unchanged files are hardlinked to the previous snapshot with rsync's
--link-dest, so a second run over 160 MB of unchanged audio adds kilobytes.
Deleting any snapshot leaves the others whole, which is the property that makes
hardlinks the right trick here rather than a clever one.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from corpus import env_file_value  # noqa: E402  — the stdlib .env reader

INSTANCE = REPO / "fieldserver" / "instance"


def destination() -> Path:
    named = os.environ.get("BACKUP_DIR") or env_file_value("BACKUP_DIR")
    if not named:
        raise SystemExit(
            "BACKUP_DIR is not set. Put it in .env (see .env.example) or pass it:\n"
            "    make backup BACKUP_DIR=/media/ben/drive/cawtalker")
    path = Path(named).expanduser()
    if not path.is_dir():
        # Deliberately not created. An external drive that is not mounted looks
        # exactly like a directory that does not exist yet, and creating it would
        # write the backup to the local disk under the mount point — succeeding
        # loudly while protecting nothing.
        raise SystemExit(
            f"{path} is not a directory. Mount the drive, or create it on purpose "
            f"first — this refuses to make it, because an unmounted drive and a "
            f"missing folder are indistinguishable from here.")
    return path


def previous_snapshot(root: Path, current: Path) -> Path | None:
    """The newest earlier snapshot, for --link-dest to hardlink against."""
    others = sorted((d for d in root.glob("cawtalker-*")
                     if d.is_dir() and d != current), reverse=True)
    return others[0] if others else None


def snapshot_database(into: Path) -> Path:
    """Copy the live database the only way that is safe while the server runs.

    `cp` on a SQLite file being written produces a torn copy that may not open.
    `.backup` takes a consistent snapshot through the same locking the server
    uses, so this needs no downtime — which matters, because a backup that
    requires stopping the field server is one that gets skipped.
    """
    target = into / "field.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["sqlite3", str(INSTANCE / "field.db"), f".backup '{target}'"],
        check=True)
    # Opened rather than assumed. A backup nobody has read is a hope.
    subprocess.run(["sqlite3", str(target), "PRAGMA integrity_check;"],
                   check=True, capture_output=True)
    return target


def copy_tree(source: Path, into: Path, name: str, link_dest: Path | None) -> None:
    """Copy a directory into this snapshot, hardlinking what has not changed.

    --link-dest is what makes dated snapshots affordable: a file identical to the
    one in the previous snapshot becomes a second name for the same data rather
    than a second copy. Audio never changes once written, so almost everything is
    a link and a nightly snapshot costs almost nothing.

    No --delete, and nothing to delete anyway — each snapshot starts empty. If a
    recording vanished locally by accident, every earlier snapshot still has it.
    """
    if not source.is_dir():
        print(f"  {name}: nothing at {source}, skipped")
        return
    target = into / name
    target.mkdir(parents=True, exist_ok=True)
    args = ["rsync", "-a", "--info=stats2"]
    if link_dest is not None and (link_dest / name).is_dir():
        args.append(f"--link-dest={link_dest / name}")
    subprocess.run([*args, f"{source}/", f"{target}/"], check=True)


def write_manifest(into: Path, stamp: str, link: Path | None) -> None:
    """What this folder is, in the folder, for whoever finds it later.

    Written because the moment a backup is needed is the worst moment to work out
    what the pieces are — quite possibly on a different machine, months later,
    with the repo not to hand.
    """
    media = into / "media"
    corpus = into / "data"
    (into / "MANIFEST.txt").write_text(f"""CrowGPT backup — {stamp}

field.db      the field server's database: every capture, label, context tag,
              count, merge record and Keep flag. Snapshotted through SQLite so
              it is consistent even though the server was running, and checked
              with PRAGMA integrity_check before this file was written.
media/        {len(list(media.glob('*'))) if media.is_dir() else 0} recordings. The names are content hashes and mean
              nothing on their own — field.db is what says which is which.
data/         {'present' if corpus.is_dir() else 'not in this snapshot (replaceable by the corpus tooling)'}

TO RESTORE

  1. Stop the field server.
  2. Copy field.db to      fieldserver/instance/field.db
  3. Copy media/ to        fieldserver/instance/media/
  4. Start it. `make -C fieldserver schema-check` should say the schema matches.

Restore BOTH or neither. A database newer than its audio refers to recordings
that are not there; audio without the database is a directory of hex filenames
with no species, no labels and no way to tell a real field recording from a
seeded clip.

{'Unchanged files in this snapshot are hardlinked to ' + link.name + '. Deleting' + chr(10) + 'either folder leaves the other complete.' if link else 'This is a full copy.'}
""")


def size_of(path: Path) -> str:
    """Bytes actually on disk, counting a hardlinked file once.

    Summing st_size naively reports two snapshots sharing 160 MB of audio as
    320 MB, which is the opposite of the thing --link-dest is doing. A backup
    tool that overstates its own footprint invites deleting snapshots that were
    nearly free to keep.
    """
    seen: set[tuple[int, int]] = set()
    total = 0
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        info = f.stat()
        key = (info.st_dev, info.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += info.st_size
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return f"{total:.0f} {unit}" if unit == "B" else f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} GB"


def main() -> None:
    for tool in ("sqlite3", "rsync"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} is not installed")

    root = destination()
    # Stamped by the caller so a re-run inside the same minute lands in the same
    # folder rather than leaving two nearly-identical ones. Makefile supplies it.
    stamp = os.environ.get("BACKUP_STAMP") or "manual"
    into = root / f"cawtalker-{stamp}"
    link = previous_snapshot(root, into)
    into.mkdir(parents=True, exist_ok=True)

    print(f"snapshot {into.name} in {root}")
    if link:
        print(f"  hardlinking unchanged files against {link.name}")

    snapshot_database(into)
    print(f"  field.db: snapshotted and integrity-checked")

    print("  media:")
    copy_tree(INSTANCE / "media", into, "media", link)

    if os.environ.get("CORPUS"):
        print("  corpus (data/):")
        copy_tree(REPO / "data", into, "data", link)
    else:
        print("  corpus (data/): skipped — re-downloadable. `make backup CORPUS=1`")

    write_manifest(into, stamp, link)
    print(f"\ndone. {size_of(into)} in this snapshot; "
          f"{size_of(root)} on disk for all {len(list(root.glob('cawtalker-*')))} of them")
    print(f"\nRestoring: see {into.name}/MANIFEST.txt")


if __name__ == "__main__":
    main()
