"""0116 step 1: fetch sibling eBird v2 checklists for 0102's witnessed American Crow owl/hawk recordings
and dump a blind text-only coding sheet (zero audio features, zero model scores, zero dates/splits).

    python3 experiments/0116-sibling-checklist-posture-recovery/fetch_checklists.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0116-checklist-posture"
CL_DIR = CACHE_DIR / "checklists"
DB_PATH = DATA_DIR / "corvid.db"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

RAPTOR_SPECIES_PREFIXES = (
    "grhowl", "brdowl", "easowl", "wesowl", "snoowl", "loeowl", "sheowl", "nswowl", "brnowl", "spoowl", "nohowl", "pygowl", "burrow", "owl",
    "rethaw", "coohaw", "reshaw", "shshaw", "brwhaw", "swahaw", "ferhaw", "rolhaw", "harhaw", "norgos", "goshaw", "hawk",
    "baleag", "goleag", "eagle", "amerke", "merlin", "perfal", "prafal", "gyrfal", "osprey", "norhar", "turvul", "blkvul", "miskite", "whtkit",
)
RAPTOR_WORDS = (
    "owl", "hawk", "eagle", "falcon", "kestrel", "merlin", "osprey", "harrier", "goshawk", "kite", "bubo", "strix", "buteo", "accipiter", "haliaeetus", "falco",
)


def load_ebird_key() -> str:
    if os.environ.get("EBIRD_API_KEY"):
        return os.environ["EBIRD_API_KEY"].strip()
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "EBIRD_API_KEY":
                    return v.strip().strip('"').strip("'")
    raise RuntimeError("EBIRD_API_KEY not found in environment or .env")


def is_raptor_code_or_text(species_code: str, comment: str) -> bool:
    sc = (species_code or "").lower()
    if any(sc.startswith(p) or p in sc for p in RAPTOR_SPECIES_PREFIXES):
        return True
    cm = (comment or "").lower()
    return any(w in cm for w in RAPTOR_WORDS)


def main():
    CL_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_ebird_key()

    labs_102 = json.loads((REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json").read_text())
    post_103 = json.loads((REPO / "experiments" / "0103-caw-level-and-posture-controls" / "posture_labels.json").read_text())
    p103_by_id = {int(k): v for k, v in post_103.items()} if isinstance(post_103, dict) else {r["id"]: r for r in post_103}

    targets = [
        r for r in labs_102
        if r.get("slug") == "american-crow" and r.get("witnessed") and r.get("context") in ("owl_mobbing", "hawk_mobbing")
    ]
    ids = [r["id"] for r in targets]

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    q = f"SELECT id, source, source_ref, raw FROM recordings WHERE id IN ({','.join(map(str, ids))})"
    rec_raw = {}
    sub_ids = set()
    for rid, src, sref, raw in con.execute(q).fetchall():
        d = json.loads(raw or "{}")
        sub_id = (d.get("ebirdChecklistId") or "").strip()
        rec_raw[rid] = {
            "source": src,
            "source_ref": sref,
            "sub_id": sub_id,
            "crow_notes": d.get("mediaNotes") or d.get("rmk") or "",
            "crow_tags": d.get("tags") or [],
            "crow_behaviors": d.get("behaviors") or "",
        }
        if sub_id:
            sub_ids.add(sub_id)
    con.close()

    todo = sorted(s for s in sub_ids if not (CL_DIR / f"{s}.json").exists())
    run = Run("0116 eBird checklist fetch", ["fetch", "sheet"])
    errors = {}
    with run.stage("fetch") as st:
        st.update(0, max(len(todo), 1), extra=f"{len(sub_ids) - len(todo)} cached")
        for idx, sub_id in enumerate(todo, 1):
            url = f"https://api.ebird.org/v2/product/checklist/view/{sub_id}"
            req = urllib.request.Request(url, headers={"X-eBirdApiToken": api_key, "User-Agent": "CrowGPT-Research/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                (CL_DIR / f"{sub_id}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            except urllib.error.HTTPError as exc:
                errors[sub_id] = f"HTTP {exc.code}"
            except Exception as exc:  # noqa: BLE001
                errors[sub_id] = str(exc)[:120]
            if idx % 10 == 0 or idx == len(todo):
                st.update(idx, max(len(todo), 1), extra=f"{len(errors)} err")
            time.sleep(0.26)

    # Build strictly blind text sheet under data/ (never committed)
    blind_rows = []
    with run.stage("sheet") as st:
        for r in sorted(targets, key=lambda x: x["id"]):
            rid = r["id"]
            info = rec_raw.get(rid, {})
            sub_id = info.get("sub_id", "")
            cl_path = CL_DIR / f"{sub_id}.json" if sub_id else None
            cl_comments = ""
            sibling_obs = []
            if cl_path and cl_path.exists():
                cl = json.loads(cl_path.read_text())
                cl_comments = (cl.get("comments") or "").strip()
                for ob in cl.get("obs") or []:
                    sp = ob.get("speciesCode") or ""
                    cm = (ob.get("comments") or "").strip()
                    aux = [a.get("value") or a.get("auxCode") for a in (ob.get("obsAux") or [])]
                    media_cnt = ob.get("mediaCounts") or {}
                    if sp.startswith("amecro") or sp.startswith("norcro") or is_raptor_code_or_text(sp, cm):
                        sibling_obs.append({
                            "speciesCode": sp,
                            "howMany": ob.get("howManyAtleast") or ob.get("howManyStr"),
                            "aux": [x for x in aux if x],
                            "mediaCounts": media_cnt,
                            "comments": cm,
                        })
            prev_103 = p103_by_id.get(rid)
            blind_rows.append({
                "id": rid,
                "context": r["context"],
                "pred_vocal_0102": bool(r.get("pred_vocal")),
                "in_0103_strict": prev_103 is not None,
                "posture_0103": prev_103["posture"] if isinstance(prev_103, dict) else prev_103,
                "sub_id_present": bool(sub_id and cl_path and cl_path.exists()),
                "crow_notes": info.get("crow_notes", ""),
                "crow_tags": info.get("crow_tags", []),
                "checklist_comments": cl_comments,
                "sibling_obs": sibling_obs,
            })
        (CACHE_DIR / "blind_coding_sheet.json").write_text(json.dumps(blind_rows, indent=2, ensure_ascii=False))
        st.update(1, 1)

    with_new_text = sum(
        1 for b in blind_rows
        if b["checklist_comments"] or any(o["comments"] or o["aux"] for o in b["sibling_obs"] if not o["speciesCode"].startswith("amecro"))
    )
    msg = (
        f"targets={len(targets)}, unique_checklists={len(sub_ids)}, fetched_ok={len(sub_ids) - len(errors)}, "
        f"errors={len(errors)}, rows_with_checklist_or_raptor_obs_notes={with_new_text}"
    )
    run.note(msg)
    print(msg)


if __name__ == "__main__":
    main()
