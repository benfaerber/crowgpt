"""What both 0095 scripts share: the listening tables and how a judge is scored."""
import sqlite3
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "fieldserver" / "instance" / "field.db"
POOLS_DIR = REPO / "crowgpt" / "results" / "listening-pools"
TRAIN_POOLS = ("churn-spread-0053", "scrape-v3-0064", "longctx-0067",
               "longctx-0067b", "dust-0069")
OPEN_POOLS = ("voice-0078", "capacity-0086")


class Trials:
    """The listening tables, read-only."""

    QUERY = """
        SELECT t.id, t.kind, t.anchor_clip, t.first_clip, t.second_clip,
               t.first_arm, t.second_arm, a.grade
        FROM listening_trials t
        JOIN listening_pools p ON p.id = t.pool_id
        LEFT JOIN listening_answers a ON a.trial_id = t.id
        WHERE p.name = ? ORDER BY t.ordinal"""

    def __init__(self, db=DB):
        self.db = db

    def of(self, pool):
        conn = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(row, pool=pool) for row in conn.execute(self.QUERY, (pool,))]
        finally:
            conn.close()

    def graded(self, pool):
        return [t for t in self.of(pool) if t["grade"] is not None]

    def ungraded(self, pool):
        return [t for t in self.of(pool) if t["grade"] is None]


class Scorer:
    @staticmethod
    def spearman(a, b):
        from scipy.stats import spearmanr
        if np.std(a) == 0 or np.std(b) == 0:
            return 0.0
        return float(spearmanr(a, b).statistic)

    @classmethod
    def fold(cls, predictions, trials):
        grades = np.asarray([t["grade"] for t in trials], dtype=float)
        out = {"n": len(trials), "spearman": round(cls.spearman(predictions, grades), 3)}
        decided = grades != 0
        if decided.any():
            out["sign_agreement"] = round(float(np.mean(
                (predictions[decided] > 0) == (grades[decided] > 0))), 3)
        catches = [(p, t) for p, t in zip(predictions, trials) if t["kind"] == "catch"]
        if catches:
            out["catch_n"] = len(catches)
            out["catch_picks_real"] = round(float(np.mean(
                [(p > 0) == (t["first_arm"] == "real") for p, t in catches])), 3)
        return out
