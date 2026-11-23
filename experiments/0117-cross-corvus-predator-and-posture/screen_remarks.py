"""0117 step 1a: screen non-American-Crow Corvus remarks in corvid.db and write a blind text-only
candidate sheet under data/experiments/0117-cross-corvus/blind_candidates.json (zero audio, zero scores).

    python3 experiments/0117-cross-corvus-predator-and-posture/screen_remarks.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0117-cross-corvus"
DB_PATH = DATA_DIR / "corvid.db"

SPECIES_SLUGS = (
    "hooded-crow",
    "common-raven",
    "carrion-crow",
    "eurasian-jackdaw",
    "rook",
    "large-billed-crow",
)

SCREEN_RE = re.compile(
    r"\b("
    r"mob|mobbing|mobbed|scold|scolding|chasing|chase|chased|harass\w*|attack\w*|dive[- ]?bomb\w*|"
    r"owl|tawny|eagle[- ]owl|barn owl|little owl|ural owl|long[- ]eared|short[- ]eared|snowy owl|bubo|strix|asio|athene|"
    r"hawk|goshawk|sparrowhawk|buzzard|common buzzard|rough[- ]legged|honey buzzard|buteo|accipiter|"
    r"eagle|white[- ]tailed|golden eagle|booted eagle|spotted eagle|haliaeetus|aquila|"
    r"falcon|peregrine|kestrel|hobby|merlin|gyrfalcon|harrier|marsh harrier|hen harrier|kite|red kite|black kite|osprey|raptor|bird of prey|predator|"
    r"fox|red fox|cat|cats|housecat|dog|dogs|badger|marten|pine marten|stoat|weasel|mink|wolf|wolves|jackal|squirrel|hare|rabbit|mammal|"
    r"human|person|people|man|woman|observer|recordist|intruder|hiker|walker"
    r")\b",
    re.IGNORECASE,
)


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Also load existing 0102 non-american-crow rows so we can audit & extend consistently
    prev_102 = {
        r["id"]: r
        for r in json.loads((REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json").read_text())
        if r.get("slug") in SPECIES_SLUGS
    }

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    placeholders = ",".join("?" for _ in SPECIES_SLUGS)
    rows = con.execute(
        f"SELECT id, slug, source, source_ref, raw FROM recordings "
        f"WHERE downloaded = 1 AND source IN ('xeno_canto', 'macaulay') AND slug IN ({placeholders}) "
        f"ORDER BY id",
        SPECIES_SLUGS,
    ).fetchall()
    con.close()

    candidates = []
    by_slug = Counter()
    for rid, slug, src, sref, raw in rows:
        d = json.loads(raw or "{}")
        text = (d.get("rmk") or d.get("mediaNotes") or "").strip()
        also = d.get("also") or []
        if not text:
            continue
        if SCREEN_RE.search(text) or rid in prev_102:
            by_slug[slug] += 1
            p102 = prev_102.get(rid)
            candidates.append({
                "id": rid,
                "slug": slug,
                "source": src,
                "source_ref": str(sref),
                "text": text,
                "also": also if isinstance(also, list) else [str(also)],
                "prev_0102_context": p102["context"] if p102 else None,
                "prev_0102_witnessed": p102["witnessed"] if p102 else None,
                "prev_0102_pred_vocal": p102["pred_vocal"] if p102 else None,
            })

    (CACHE_DIR / "blind_candidates.json").write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    print(f"Screened {len(rows)} downloaded non-AMECRO archive rows -> {len(candidates)} keyword candidates: {dict(by_slug)}")


if __name__ == "__main__":
    main()
