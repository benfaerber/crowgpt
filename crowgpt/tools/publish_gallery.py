"""Publish a folder of generated clips as a gallery the field server can serve.

    crowgpt/.venv/bin/python crowgpt/tools/publish_gallery.py \
        --from experiments/0055-the-best-generated-calls/candidates.json \
        --name mono-v2

Ben wants a page showing a bunch of CrowGPT output where he can play through it
and download the ones he likes. That is an audition, not a measurement: no
blinding, no pre-registration, no trials — so it gets none of the machinery
`/listen/` carries and no database table either.

FILESYSTEM-BACKED ON PURPOSE. A gallery is a directory of wavs plus a manifest,
read off disk by the server the same way `api/training.py` reads crowgpt's
progress file. Nothing is pushed, nothing migrates, and a gallery built while the
server is down is simply there when it comes back.

WHY NOT SERVE THE EXPERIMENT FOLDER DIRECTLY. It would work and it would be
wrong: an experiment's output is its record, and a page that lets you delete a
clip you did not like would be editing a measurement. A gallery is a copy, and
`source` in the manifest says which experiment it came from.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GALLERY_ROOT = REPO / "crowgpt" / "results" / "gallery"

#: Fields copied into the manifest when the source has them. Anything else in a
#: candidates.json stays behind — a gallery is for listening, so it carries what
#: helps you choose and not the whole measurement.
CARRIED = ("seconds", "birdnet", "churn", "churn_gap", "seed",
           "call_type", "capture_id", "span_snr_db", "clears_both",
           "pitch_strength", "units", "rank")


def rows_from(source: Path, clip_dir: Path):
    """Clip rows out of an experiment's candidates.json.

    EVERY ROW GETS SEVERAL CANDIDATE FILENAMES, tried in order, because `file`
    does not always name a file in this directory. 0055 writes all 203 candidates
    to `candidates/` as `seedNNN.wav` and *also* copies its ten best into
    `shortlist/` under rank-based names — and sets `file` to the shortlist name.
    Trusting `file` therefore dropped exactly the ten best clips, which is the
    worst possible ten to lose and was silent apart from a count.

    0054's rows name a file that really is in the directory, so both shapes work.
    """
    blob = json.loads(source.read_text())
    candidates = blob.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit(f"{source} has no 'candidates' list")

    rows = []
    for row in candidates:
        names = []
        if row.get("seed") is not None:
            names.append(f"seed{int(row['seed']):03d}.wav")
        if row.get("file"):
            names.append(row["file"])
        chosen = next((n for n in names if (clip_dir / n).exists()), None)
        if not chosen:
            continue
        rows.append((chosen, {k: row[k] for k in CARRIED if k in row}))
    return rows, blob


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", type=Path, required=True,
                        help="an experiment's candidates.json")
    parser.add_argument("--name", required=True,
                        help="gallery name, used in the URL")
    parser.add_argument("--clips", type=Path, default=None,
                        help="clip directory (default: candidates/ beside the json)")
    parser.add_argument("--title", default=None)
    parser.add_argument("--note", default=None,
                        help="one line shown on the page")
    parser.add_argument("--limit", type=int, default=None,
                        help="publish only the first N, after sorting")
    parser.add_argument("--sort", default="birdnet",
                        help="metadata key to sort by, descending")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.exists():
        print(f"no such file: {source}", file=sys.stderr)
        return 1
    clip_dir = (args.clips or source.parent / "candidates").resolve()
    if not clip_dir.is_dir():
        print(f"no clip directory at {clip_dir}", file=sys.stderr)
        return 1

    rows, blob = rows_from(source, clip_dir)
    present = rows
    missing = len(json.loads(source.read_text()).get("candidates", ())) - len(rows)

    key = args.sort
    present.sort(key=lambda pair: -(pair[1].get(key) or 0)
                 if isinstance(pair[1].get(key), (int, float)) else 0)
    if args.limit:
        present = present[:args.limit]

    out = GALLERY_ROOT / args.name
    if out.exists():
        if not args.replace:
            print(f"{out} exists; pass --replace", file=sys.stderr)
            return 1
        shutil.rmtree(out)
    (out / "clips").mkdir(parents=True)

    clips = []
    for rank, (name, meta) in enumerate(present, 1):
        shutil.copy2(clip_dir / name, out / "clips" / name)
        clips.append({"file": name, "rank": rank, **meta})

    (out / "meta.json").write_text(json.dumps({
        "name": args.name,
        "title": args.title or args.name,
        "note": args.note,
        "source": str(source.relative_to(REPO)),
        "model": blob.get("model"),
        "sorted_by": key,
        "clips": clips,
    }, indent=2))

    print(f"{out.relative_to(REPO)}: {len(clips)} clips"
          + (f", {missing} named in the json but not on disk" if missing else ""))
    print(f"  browse at /gallery/{args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
