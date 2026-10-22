"""0071's verdict: join Ben's tags to the hidden stats and score the AUC.

Usage: python analyse.py <rating-*.json downloaded from the page>
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments"))

from lib.dustprobe import auc

OUT = Path(__file__).resolve().parent


def main(session_path):
    manifest = {row["clip_id"]: row
                for row in json.loads((OUT / "manifest.json").read_text())}
    session = json.loads(Path(session_path).read_text())

    rows = []
    for trial in session["trials"]:
        stats = manifest[trial["clip_id"]]
        rows.append((trial["rating"], stats))
    tags = {r for r, _ in rows}
    counts = {tag: sum(1 for r, _ in rows if r == tag) for tag in sorted(tags)}

    results = {"n": len(rows), "counts": counts,
               "unsure_dropped": counts.get("unsure", 0)}
    decided = [(r, s) for r, s in rows if r in ("scream", "no-scream")]
    screams = [s for r, s in decided if r == "scream"]
    normals = [s for r, s in decided if r == "no-scream"]
    for stat in ("duty_cycle", "churn0", "longest_run_s", "crest_db",
                 "hf_share", "units_per_sec"):
        pos = [s[stat] for s in screams]
        neg = [s[stat] for s in normals]
        results[stat] = {
            # Signed so "higher predicts scream"; 0059's nomination is duty
            # LOW in screams, so its predictive AUC is 1 - this value.
            "auc_scream_higher": round(auc(pos, neg), 3) if pos and neg else None,
            "scream_mean": round(float(np.mean(pos)), 3) if pos else None,
            "no_scream_mean": round(float(np.mean(neg)), 3) if neg else None,
        }
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
