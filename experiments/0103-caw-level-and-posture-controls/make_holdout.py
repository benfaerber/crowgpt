"""Step E — Lock a fixed temporal holdout split BEFORE running caw-level or posture experiments.

Sets aside every strict zero-raptor American Crow owl/hawk recording in Experiment 0102
recorded on or after CUTOFF_DATE (2023-01-01). No acoustic features or model decisions
touch the holdout until the single final evaluation at the end of Experiment 0103.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CUTOFF_DATE = "2023-01-01"


def main():
    lbls = json.loads((REPO / "experiments/0102-archive-remarks-semantics/labels.json").read_text())
    lbl_map = {r["id"]: r for r in lbls if r.get("witnessed")}
    meta = json.loads((REPO / "data/experiments/0102-archive-remarks/records.json").read_text())

    con = sqlite3.connect(str(REPO / "data/corvid.db"))
    id_to_meta = {
        rid: {
            "date": (date or "")[:10],
            "source": src,
            "lat": lat,
            "lng": lng,
            "recordist": rec or "",
            "file_path": fp or "",
            "raw_json": raw or "{}",
        }
        for rid, date, src, lat, lng, rec, fp, raw in con.execute(
            "SELECT id, date, source, lat, lng, recordist, file_path, raw "
            "FROM recordings WHERE source IN ('xeno_canto', 'macaulay')"
        ).fetchall()
    }
    con.close()

    dev_rows, holdout_rows = [], []
    seen = set()
    for r in meta:
        rid = r["id"]
        if rid in seen or rid not in lbl_map:
            continue
        if r.get("slug") != "american-crow" or not r.get("witnessed"):
            continue
        if r.get("context") not in ("owl_mobbing", "hawk_mobbing"):
            continue
        if r.get("pred_vocal") or r.get("max_raptor_conf", 0.0) >= 0.05:
            continue
        seen.add(rid)
        dm = id_to_meta.get(rid, {})
        rec_date = dm.get("date", "")
        entry = {
            "id": rid,
            "context": r["context"],
            "date": rec_date,
            "source": r.get("source") or dm.get("source", ""),
            "recordist": r.get("recordist") or dm.get("recordist", ""),
        }
        if rec_date >= CUTOFF_DATE:
            holdout_rows.append(entry)
        else:
            dev_rows.append(entry)

    dev_rows.sort(key=lambda x: (x["date"], x["id"]))
    holdout_rows.sort(key=lambda x: (x["date"], x["id"]))
    dev_recs = {x["recordist"].strip().lower() for x in dev_rows if x["recordist"]}
    ho_recs = {x["recordist"].strip().lower() for x in holdout_rows if x["recordist"]}
    shared_recs = sorted(dev_recs & ho_recs)

    payload = {
        "cutoff_date": CUTOFF_DATE,
        "rule": "Strict zero-raptor American Crow owl_mobbing/hawk_mobbing in 0102/labels.json split strictly by recording date (< cutoff = dev, >= cutoff = untouched holdout).",
        "dev_counts": dict(Counter(x["context"] for x in dev_rows)),
        "holdout_counts": dict(Counter(x["context"] for x in holdout_rows)),
        "dev_n": len(dev_rows),
        "holdout_n": len(holdout_rows),
        "shared_recordists_count": len(shared_recs),
        "dev_ids": [x["id"] for x in dev_rows],
        "holdout_ids": [x["id"] for x in holdout_rows],
        "holdout_zero_overlap_ids": [
            x["id"] for x in holdout_rows if x["recordist"].strip().lower() not in dev_recs
        ],
    }
    out_path = HERE / "holdout_2023.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Locked temporal holdout (date >= {CUTOFF_DATE}) -> {out_path.name}")
    print(f"  Dev:     n={len(dev_rows)} {payload['dev_counts']}")
    print(f"  Holdout: n={len(holdout_rows)} {payload['holdout_counts']} (zero-recordist-overlap n={len(payload['holdout_zero_overlap_ids'])})")


if __name__ == "__main__":
    main()
