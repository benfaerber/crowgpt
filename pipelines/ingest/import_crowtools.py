"""Lift the crow-tools labels into this repo, once, so the fork can go.

crow-tools is abandonware, and everything Cawtalker took from it splits cleanly
in two.

THE AUDIO IS REPLACEABLE. Every labelled recording sits in a public catalogue
and is re-fetchable by id — that fetching lives with the private corpus
tooling, which reads the committed labels and fills
`data/species/american-crow/audio`. Nothing is lost by re-downloading it into
`data/` where the rest of the corpus lives.

THE LABELS ARE NOT. 3,162 hand-reviewed segments across 1,549 recordings, which
is the only substantial human ground truth this project has — an order of
magnitude more than the 35 field labels. It exists because somebody sat and
listened. It cannot be re-fetched, re-derived, or reconstructed from anything on
disk, and it currently survives only inside an unmaintained fork's gitignored
cache directory. That is the whole reason this script exists.

So it comes across as a committed file, not into data/, which is gitignored. A
megabyte of JSON in git is a fine price for the one artifact in this project
that money cannot replace.

Not imported, deliberately: auto.json (31 MB of the detector's own guesses, not
human, and regenerable), embeddings-3d.json (derived), and the audio.

    python pipelines/ingest/import_crowtools.py            # writes the labels
    python pipelines/ingest/import_crowtools.py --plan     # just say what it would do

THIS IS THE ONLY SCRIPT THAT KNOWS WHAT A FORK IS. The migration is done and the
rest of the project reads the committed file, so fork resolution lives here
rather than in corpus.py — where it used to sit and where it made `make corpus`
fail on a checkout that had everything it needed. It stays because re-importing
should be one command if upstream ever changes, not an archaeology exercise.
"""

import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

import corpus  # sibling script, not a package

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "crowtools"
LABELS_PATH = OUT_DIR / "labels.json"
CATALOG_NUMBER = "ML Catalog Number"

# Where the fork is looked for, in order, when nothing names it explicitly. The
# sibling checkout comes first because it is *derived* rather than assumed: clone
# the two next to each other anywhere — /srv, a laptop with no ~/Code — and this
# finds it. ~/Code/crow-tools stays as the second guess so the layout that has
# always worked keeps working.
SEARCH_PATH = (REPO.parent / "crow-tools", Path.home() / "Code" / "crow-tools")

CLONE_HINT = "git clone https://github.com/CrowCall/crow-tools"


def looks_like_fork(path):
    """A fork that has been set up at least once has fetched its datasets."""
    return (path / ".cache" / "datasets").is_dir()


def resolve_fork(explicit=None, env_file=None):
    """Find the fork: --fork, CROW_TOOLS_DIR, .env, then the search path.

    A path someone named by hand is checked and *not* fallen back on. Searching
    past a wrong CROW_TOOLS_DIR would quietly re-import whichever corpus happened
    to be lying around instead, and a run that succeeds against the wrong data is
    worse than one that refuses.
    """
    from_env_file = None
    named = explicit or os.environ.get("CROW_TOOLS_DIR")
    if not named:
        named = from_env_file = corpus.env_file_value("CROW_TOOLS_DIR", env_file)
    if named:
        path = Path(named).expanduser().resolve()
        if not looks_like_fork(path):
            source = ("--fork" if explicit
                      else "CROW_TOOLS_DIR in .env" if from_env_file
                      else "CROW_TOOLS_DIR")
            raise FileNotFoundError(
                f"{source} points at {path}, which has no .cache/datasets — that is "
                f"not a set-up crow-tools fork. Clone it ({CLONE_HINT}) and run its "
                f"download once, or point {source} somewhere else."
            )
        return path
    for candidate in dict.fromkeys(SEARCH_PATH):  # the two collide under ~/Code
        if looks_like_fork(candidate):
            return candidate
    tried = "\n".join(f"  {c}" for c in dict.fromkeys(SEARCH_PATH))
    raise FileNotFoundError(
        f"No crow-tools fork found. Looked in:\n{tried}\n"
        f"Clone it beside this checkout ({CLONE_HINT} {REPO.parent / 'crow-tools'}) "
        f"and run its download, or set CROW_TOOLS_DIR / pass --fork.\n"
        f"Only a re-import needs this — everything else reads {LABELS_PATH}."
    )


def library_index(cache):
    """file_id -> library token, from each library's own catalogue.

    Read from the CSVs rather than from whatever audio happens to be downloaded,
    so a labelled recording whose audio was never fetched is still attributed and
    still recoverable.

    The token is positional over the fork's sorted catalogue directories
    (`library-1`, `library-2`, …) rather than the directory's own name: which
    catalogue a token stands for is the corpus tooling's business, not this
    repo's, and the sort keeps a re-import writing the same tokens the committed
    file already carries.
    """
    index = {}
    libraries_dir = cache / "libraries"
    catalogues = sorted(p for p in libraries_dir.iterdir()
                        if (p / "library.csv").exists()) if libraries_dir.is_dir() else []
    for position, catalogue_dir in enumerate(catalogues, 1):
        token = f"library-{position}"
        with open(catalogue_dir / "library.csv", newline="",
                  encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                file_id = (row.get(CATALOG_NUMBER) or "").strip()
                if file_id:
                    index.setdefault(file_id, token)
    return index


def gather(dataset="all-public", fork_dir=None):
    fork = resolve_fork(fork_dir)
    cache = fork / ".cache"
    labels = json.loads((cache / "datasets" / dataset / "labels.json").read_text())
    reviewed = {key: flags for key, flags in labels.items() if flags.get("reviewed")}

    config_path = cache / "datasets" / dataset / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}

    index = library_index(cache)
    files = sorted({key.rsplit("-", 2)[0] for key in reviewed})
    libraries = {f: index[f] for f in files if f in index}
    orphans = [f for f in files if f not in libraries]

    return {
        "source": f"crow-tools {dataset}",
        "imported": date.today().isoformat(),
        "label_schema": config.get("label_schema"),
        "libraries": libraries,
        "labels": reviewed,
    }, orphans


def summarise(payload, orphans):
    labels = payload["labels"]
    core = sum(1 for flags in labels.values() if corpus.LabelCorpus.core_labels(flags))
    counts = {}
    for flags in labels.values():
        for label in corpus.LabelCorpus.core_labels(flags):
            counts[label] = counts.get(label, 0) + 1
    by_library = {}
    for library in payload["libraries"].values():
        by_library[library] = by_library.get(library, 0) + 1
    return {
        "segments": len(labels),
        "with_a_core_label": core,
        "recordings": len(payload["libraries"]) + len(orphans),
        "by_library": by_library,
        "unattributed_recordings": len(orphans),
        "core_label_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="all-public")
    parser.add_argument("--fork", default=None,
                        help="path to the crow-tools checkout (default: $CROW_TOOLS_DIR, "
                             "the same key in .env, a sibling of this repo, ~/Code/crow-tools)")
    parser.add_argument("--plan", action="store_true", help="report without writing")
    parser.add_argument("--download", action="store_true",
                        help="gone — the corpus tooling fetches the audio now")
    args = parser.parse_args()

    if args.download:
        # This repo does not fetch audio. The private corpus tooling reads the
        # committed labels and fills corpus.LOCAL_AUDIO; run its
        # fetch_crowtools_audio.py against this file.
        sys.exit(
            "--download moved to the private corpus tooling on 2026-08-07 — this\n"
            f"repo no longer fetches audio. Point its fetch_crowtools_audio.py at\n"
            f"  {LABELS_PATH}\n"
            f"and let it fill {corpus.LOCAL_AUDIO}."
        )

    try:
        payload, orphans = gather(args.dataset, args.fork)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        sys.exit(f"Could not read the fork's labels: {exc}")

    report = summarise(payload, orphans)
    for key, value in report.items():
        print(f"  {key}: {value}")
    if orphans:
        print(f"  note: {len(orphans)} recordings are in no catalogue and cannot be "
              "re-downloaded by id — their labels are kept regardless")

    if args.plan:
        print(f"\nwould write {LABELS_PATH}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.write_text(json.dumps(payload, indent=1, sort_keys=True))
    size = LABELS_PATH.stat().st_size / 1e6
    print(f"\nwrote {LABELS_PATH} ({size:.1f} MB) — commit this, it is the irreplaceable half")
    print("next: have the corpus tooling download the audio it points at, then the "
          "fork is no longer needed")


if __name__ == "__main__":
    main()
