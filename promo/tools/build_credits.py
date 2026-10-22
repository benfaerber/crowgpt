#!/usr/bin/env python3
"""Generate the credits data for the promo site's attribution page.

Credits what was actually *used*, not everything the corpus knows about: a
recording only appears if its audio is on disk. Crediting rows we never
downloaded would inflate the list and misstate what the models learned from.

Xeno-canto only. Its recordings are Creative Commons, and naming recordists is
what those licences ask for. Other sources in the corpus are deliberately not
listed anywhere public.

    python3 promo/tools/build_credits.py

Writes promo/public/credits.json, which the credits page fetches at runtime —
kept out of the JS bundle because it is far larger than the site itself.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = Path(os.environ.get("DATA_DIR", REPO / "data")) / "corvid.db"
AUDIO = Path(os.environ.get("DATA_DIR", REPO / "data")) / "audio" / "xeno_canto"
OUT = REPO / "promo" / "public" / "credits.json"

# The licence strings in the corpus are a mess of URLs, short codes and opaque
# placeholders from other archives. Only Creative Commons URLs are meaningful to
# a reader, so they are normalised to a short name and anything unrecognised is
# reported as such rather than guessed at.
CC_NAMES = {
    "by": "CC BY",
    "by-sa": "CC BY-SA",
    "by-nc": "CC BY-NC",
    "by-nc-sa": "CC BY-NC-SA",
    "by-nc-nd": "CC BY-NC-ND",
    "by-nd": "CC BY-ND",
    "zero": "CC0",
}


def licence_name(raw: str | None) -> str:
    if not raw:
        return "unstated"
    text = raw.strip().lower()
    for key, name in CC_NAMES.items():
        if f"/licenses/{key}/" in text or f"/{key}/" in text and "creativecommons" in text:
            version = text.rstrip("/").split("/")[-1]
            return f"{name} {version}" if version and version[0].isdigit() else name
    if "publicdomain/zero" in text:
        return "CC0"
    if text.startswith("cc"):
        return raw.strip().upper().replace("CC-", "CC ")
    return "other"


def main() -> int:
    if not DB.exists():
        print(f"no corpus DB at {DB}")
        return 1

    on_disk = {p.stem for p in AUDIO.glob("*.mp3")}
    print(f"{len(on_disk)} audio files on disk")

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT source_ref, species, recordist, license FROM recordings "
        "WHERE source = 'xeno_canto' AND source_ref IS NOT NULL"
    ).fetchall()
    db.close()

    by_recordist: dict[str, list[str]] = defaultdict(list)
    licences: Counter[str] = Counter()
    species: set[str] = set()
    used = 0

    for row in rows:
        ref = str(row["source_ref"])
        if ref not in on_disk:
            continue
        used += 1
        by_recordist[(row["recordist"] or "Unnamed recordist").strip()].append(ref)
        licences[licence_name(row["license"])] += 1
        if row["species"]:
            species.add(row["species"])

    # Sorted by surname where there is one, so the list reads like a credit roll
    # rather than a database dump.
    def sort_key(name: str) -> tuple[str, str]:
        parts = name.split()
        return (parts[-1].lower() if parts else "", name.lower())

    payload = {
        "source": "Xeno-canto",
        "url": "https://xeno-canto.org/",
        "counts": {
            "recordings": used,
            "recordists": len(by_recordist),
            "species": len(species),
        },
        "licences": sorted(licences.items(), key=lambda kv: -kv[1]),
        "recordists": [
            {"name": name, "ids": sorted(by_recordist[name], key=lambda r: -int(r) if r.isdigit() else 0)}
            for name in sorted(by_recordist, key=sort_key)
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    size = OUT.stat().st_size / 1024
    print(
        f"{used} recordings by {len(by_recordist)} recordists across {len(species)} species"
        f" -> {OUT.relative_to(REPO)} ({size:.0f} KB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
