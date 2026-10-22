"""Export field-server human labels into a train_species.py manifest.

Closes the retrain loop: reads the field DB's `labels` table for one species,
maps each field label to its CORE class via `label_defs.core_mapping` (the same
mapping the fleet's /api/config serves), and appends {path, type, labels} records
to data/species/<slug>/manifest.json — the exact file train_species.py already
reads. So field labels train through the same door as the archive corpus.

`labels` carries the word the human chose, next to the CORE class it folds into,
so a head trained on a finer class can select the rows that say it instead of
inferring the rest said no. See the note on by_file below.

  python pipelines/ingest/export_manifest.py --slug american-crow
  # then:  make train SLUG=american-crow

Note: train_species pools whole clips, so each labelled clip contributes its
call type(s) as one manifest record. Short foreground captures (one bird, one
call) fit this well; per-segment fidelity for multi-call clips is a later upgrade
(mirror build_dataset.py's covering-window pooling).
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import manifest as manifest_mod  # sibling script, not a package

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--slug", required=True)
    parser.add_argument("--field-db", default=str(DEFAULT_FIELD_DB))
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)

    field_db = Path(args.field_db)
    data_dir = Path(args.data_dir or os.environ.get("DATA_DIR") or REPO / "data")
    media_dir = field_db.parent / "media"
    if not field_db.exists():
        sys.exit(f"no field DB at {field_db}")

    con = sqlite3.connect(field_db)
    con.row_factory = sqlite3.Row
    tax = con.execute("SELECT common_name FROM taxonomy WHERE slug = ?",
                      (args.slug,)).fetchone()
    if not tax:
        sys.exit(f"no taxonomy entry for slug '{args.slug}' in {field_db}")
    common_name = tax["common_name"]
    # trains=0 labels are judgements about a detection — "not a crow", "can't
    # tell". Leaving them out here means the loop below drops them on `if
    # mapped`, so a rejection can never become a class the model predicts.
    core = {r["key"]: r["core_mapping"]
            for r in con.execute(
                "SELECT key, core_mapping FROM label_defs WHERE trains = 1")}
    rows = con.execute(
        "SELECT m.storage_ref AS ref, l.call_type AS call_type "
        "FROM labels l JOIN media m ON l.media_id = m.id WHERE l.species = ?",
        (common_name,)).fetchall()
    con.close()

    # one manifest record per labelled file; type = comma-joined distinct CORE
    # classes, labels = the words the humans actually chose.
    #
    # Both, because they answer different questions and the coarse one cannot
    # stand in for the fine one. `mobbing` and `alarm call` both map to the CORE
    # class "alarm call", so `type` alone cannot tell a recordist who said
    # "mobbing" from one who said "alarm call" — and a finer head trained on that
    # would have to treat every coarse label as *not* mobbing to make up the
    # difference. That is the trap experiments/0012 measured in crow-tools, whose
    # `scold` column was only ever put to a human on 1,089 of 2,494 segments and
    # scored 0.581 read as though the rest had answered no.
    #
    # So the rule this file enforces: a label supplies positives for what it says
    # and nothing about what it does not say. Selecting on `labels` picks the rows
    # where somebody chose that word; the coarse rows are absent from that head
    # rather than sitting in it as negatives.
    by_file: dict[str, set] = {}
    keys_by_file: dict[str, set] = {}
    for r in rows:
        mapped = core.get(r["call_type"])
        if mapped:
            by_file.setdefault(r["ref"], set()).add(mapped)
            keys_by_file.setdefault(r["ref"], set()).add(r["call_type"])
    # `source` is what stops the corpus tooling's next run over this species
    # overwriting these: it replaces its own records and keeps everything else.
    field_recs = [
        {"path": str(media_dir / ref), "type": ",".join(sorted(cores)),
         "labels": ",".join(sorted(keys_by_file[ref])),
         "source": manifest_mod.FIELD}
        for ref, cores in by_file.items()
        if (media_dir / ref).exists()
    ]

    out_dir = data_dir / "species" / args.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = ({"recordings": []} if not manifest_path.exists()
                else json.loads(manifest_path.read_text()))
    manifest.setdefault("slug", args.slug)
    seen = {rec["path"] for rec in manifest.get("recordings", [])}
    added = [r for r in field_recs if r["path"] not in seen]
    manifest.setdefault("recordings", []).extend(added)
    meta = {k: v for k, v in manifest.items() if k != "recordings"}
    manifest_mod.write(manifest_path, manifest["recordings"], **meta)

    print(f"export {args.slug} ({common_name}): {len(field_recs)} labelled files, "
          f"{len(added)} new -> {manifest_path}")
    print(f"  manifest now has {len(manifest['recordings'])} recordings")
    print(f"  next: make train SLUG={args.slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
