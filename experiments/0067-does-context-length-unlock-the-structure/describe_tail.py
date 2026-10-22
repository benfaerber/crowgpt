"""The −2 tail: what actually fails when the long-context model fails hard?

Six compare trials earned a −2 against model-longctx. This rebuilds exactly
those trials as a labelled diagnostic page (one visit, describe don't rank —
the 0057 shape): the real anchor, the longctx clip that failed, and the twin
clip that beat it. Ben's words here decide the next lever — capacity,
sampling, or window — the way "scratchy"/"screaming" decided the decoder.
"""
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

import soundfile as sf

from crowgpt.demo import ComparePage

DB = REPO / "fieldserver" / "instance" / "field.db"
CLIP_DIR = HERE / "results" / "listening-pools" / "longctx-0067"
PAGE = HERE / "results" / "compare-longctx-tail.html"


def main():
    db = sqlite3.connect(DB)
    rows = list(db.execute(
        """SELECT t.first_arm, t.first_clip, t.second_clip, t.anchor_clip, a.grade
           FROM listening_answers a JOIN listening_trials t ON t.id = a.trial_id
           JOIN listening_pools p ON p.id = t.pool_id
           WHERE p.name = 'longctx-0067' AND t.kind = 'compare'"""))

    def clip(name):
        audio, _ = sf.read(CLIP_DIR / name, dtype="float32")
        return audio

    page_rows = []
    for first_arm, first, second, anchor, grade in rows:
        longctx_first = first_arm == "model-longctx"
        # -2 toward the second clip when longctx was first, +2 toward the
        # first when it was second: both mean "the twin was much closer".
        lost_hard = (grade == -2 and longctx_first) or (grade == 2 and not longctx_first)
        if not lost_hard:
            continue
        lc, un = (first, second) if longctx_first else (second, first)
        page_rows.append({
            "species": f"failed trial {len(page_rows) + 1}",
            "arms": [
                ("REAL — the anchor", "the reference you graded against", clip(anchor), None),
                ("model-longctx — the -2", "what failed hard: name it", clip(lc), None),
                ("model-units — the winner", "the twin that beat it", clip(un), None),
            ],
        })

    ComparePage(page_rows, {
        "Question": "what fails in each longctx clip — describe, don't rank",
        "Rows": f"{len(page_rows)} trials graded -2 against model-longctx",
        "Why": "your words choose the next lever: capacity, sampling, or window",
    }).write(PAGE)
    print(f"{len(page_rows)} rows -> {PAGE}")


if __name__ == "__main__":
    main()
