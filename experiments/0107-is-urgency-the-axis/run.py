"""0107 — is a single urgency measure what the owl-versus-hawk result is about?

    pipelines/representation/.venv-birdnet/bin/python experiments/0107-is-urgency-the-axis/run.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0107-urgency"
ARCHIVE_CACHE = DATA_DIR / "experiments" / "0102-archive-remarks"
LABELS = REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
sys.path.insert(0, str(REPO / "experiments" / "0105-does-calling-change-when-the-recordist-says-so"))
from crowgpt.progress import Run  # noqa: E402
from run import CallingIntensity  # noqa: E402

AROUSAL_RANK = {"softSong": 0, "alert": 1, "mob": 2}
OTHER_FLAGS = ("scold", "rattle", "begging", "grief")


def _file_duties(task):
    """Duty cycle over each requested span of one file; (None, None) is the whole file."""
    key, path, spans = task
    try:
        intensity = CallingIntensity(Path(path))
    except Exception:  # noqa: BLE001 — an unreadable file is a missing row, not a crash
        return key, None
    return key, [
        intensity.duty_cycle(0.0, intensity.duration_s) if start is None
        else intensity.duty_cycle(float(start), float(end))
        for start, end in spans
    ]


class DutyCache:
    """Measures duty cycles in parallel and remembers them between runs."""

    def __init__(self, name: str):
        self.path = CACHE / f"{name}.json"

    def measure(self, tasks: list[tuple], stage) -> dict:
        if self.path.exists():
            stage.update(len(tasks), len(tasks), extra="cached")
            return json.loads(self.path.read_text())
        out = {}
        with ProcessPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_file_duties, t) for t in tasks]
            for done, future in enumerate(as_completed(futures), 1):
                key, duties = future.result()
                out[str(key)] = duties
                if done % 20 == 0 or done == len(tasks):
                    stage.update(done, len(tasks))
        CACHE.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(out))
        return out


class HumanSortedSegments:
    """One-second crow-tools segments flagged with exactly one arousal class."""

    def __init__(self):
        from corpus import LabelCorpus

        self.segments = [
            s for s in LabelCorpus().labeled_segments()
            if sum(bool(s.flags.get(f)) for f in AROUSAL_RANK) == 1
            and not any(s.flags.get(f) for f in OTHER_FLAGS)
        ]

    def tasks(self):
        by_file = defaultdict(list)
        for s in self.segments:
            by_file[(s.file_id, str(s.audio_path))].append((s.start, s.end))
        return [(file_id, path, spans) for (file_id, path), spans in by_file.items()]

    def table(self, duties: dict) -> dict:
        position = defaultdict(int)
        rows = []
        for s in self.segments:
            measured = duties.get(str(s.file_id))
            index = position[s.file_id]
            position[s.file_id] += 1
            if measured is None:
                continue
            flag = next(f for f in AROUSAL_RANK if s.flags.get(f))
            rows.append((s.file_id, flag, str(s.flags.get("crowCount")), measured[index]))
        return {
            "file": np.array([r[0] for r in rows]),
            "flag": np.array([r[1] for r in rows]),
            "crow_count": np.array([r[2] for r in rows]),
            "u": np.array([r[3] for r in rows], dtype=float),
        }

    @staticmethod
    def ordering(table: dict, mask: np.ndarray, resamples: int = 2000) -> dict:
        files, flags, u = table["file"][mask], table["flag"][mask], table["u"][mask]
        rank = np.array([AROUSAL_RANK[f] for f in flags])
        rho = float(spearmanr(rank, u)[0])
        by_file = defaultdict(list)
        for i, f in enumerate(files):
            by_file[f].append(i)
        groups = list(by_file.values())
        rng = np.random.default_rng(0)
        boot = []
        for _ in range(resamples):
            picked = np.concatenate([groups[g] for g in rng.integers(0, len(groups), len(groups))])
            boot.append(spearmanr(rank[picked], u[picked])[0])
        medians = {f: round(float(np.median(u[flags == f])), 4) for f in AROUSAL_RANK}
        return {
            "n": {f: int(np.sum(flags == f)) for f in AROUSAL_RANK},
            "files": len(groups),
            "median_u": medians,
            "monotone": medians["softSong"] < medians["alert"] < medians["mob"],
            "spearman_rho": round(rho, 4),
            "ci95": [round(float(np.nanpercentile(boot, 2.5)), 4), round(float(np.nanpercentile(boot, 97.5)), 4)],
            "auc_alert_vs_softSong": round(float(roc_auc_score(
                flags[flags != "mob"] == "alert", u[flags != "mob"])), 4),
            "auc_mob_vs_alert": round(float(roc_auc_score(
                flags[flags != "softSong"] == "mob", u[flags != "softSong"])), 4),
        }


class ArchiveRecordings:
    """0102's witnessed American crow recordings, with whole-recording duty cycle."""

    def __init__(self):
        self.meta = json.loads((ARCHIVE_CACHE / "records.json").read_text())
        self.features = np.load(ARCHIVE_CACHE / "features.npz")
        committed = {
            (r["source"], str(r["source_ref"])): r["context"]
            for r in json.loads(LABELS.read_text()) if r["witnessed"]
        }
        self.rows = [
            i for i, r in enumerate(self.meta)
            if r["slug"] == "american-crow" and r["witnessed"] and self.features["has_clean"][i]
            and committed.get((r["source"], str(r["source_ref"]))) == r["context"]
        ]

    def tasks(self):
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        out = []
        for i in self.rows:
            (raw,) = db.execute("SELECT file_path FROM recordings WHERE id = ?", (self.meta[i]["id"],)).fetchone()
            path = Path(raw)
            if not path.exists() and "/data/" in raw:
                path = DATA_DIR / raw.split("/data/", 1)[1]
            out.append((self.meta[i]["id"], str(path), [(None, None)]))
        return out

    def by_context(self, duties: dict) -> dict:
        grouped = defaultdict(list)
        for i in self.rows:
            measured = duties.get(str(self.meta[i]["id"]))
            if measured is not None:
                grouped[self.meta[i]["context"]].append(measured[0])
        return {c: {"n": len(v), "median_u": round(float(np.median(v)), 4),
                    "iqr": [round(float(np.percentile(v, 25)), 4), round(float(np.percentile(v, 75)), 4)]}
                for c, v in sorted(grouped.items())}

    def owl_versus_hawk(self, duties: dict) -> dict:
        strict = [
            i for i in self.rows
            if self.meta[i]["context"] in ("owl_mobbing", "hawk_mobbing")
            and not self.meta[i]["pred_vocal"] and self.meta[i]["max_raptor_conf"] < 0.05
            and duties.get(str(self.meta[i]["id"])) is not None
        ]
        y = np.array([self.meta[i]["context"] == "owl_mobbing" for i in strict]).astype(int)
        groups = np.array([(self.meta[i].get("recordist") or str(self.meta[i]["id"])).strip().lower() for i in strict])
        u = np.array([duties[str(self.meta[i]["id"])][0] for i in strict])[:, None]
        embedding = self.features["emb_clean"][strict][:, :1024]
        raw, residual, u_only = np.zeros(len(y)), np.zeros(len(y)), np.zeros(len(y))
        for train, test in StratifiedGroupKFold(n_splits=5).split(embedding, y, groups):
            head = lambda: make_pipeline(  # noqa: E731
                StandardScaler(), LogisticRegression(C=0.05, max_iter=3000, class_weight="balanced"))
            raw[test] = head().fit(embedding[train], y[train]).predict_proba(embedding[test])[:, 1]
            remover = LinearRegression().fit(u[train], embedding[train])
            cleaned_train = embedding[train] - remover.predict(u[train])
            cleaned_test = embedding[test] - remover.predict(u[test])
            residual[test] = head().fit(cleaned_train, y[train]).predict_proba(cleaned_test)[:, 1]
            u_only[test] = LogisticRegression(class_weight="balanced").fit(u[train], y[train]).predict_proba(u[test])[:, 1]
        return {
            "n": int(len(y)), "owl": int(y.sum()), "hawk": int((1 - y).sum()), "recordists": len(set(groups)),
            "median_u": {"owl": round(float(np.median(u[y == 1])), 4), "hawk": round(float(np.median(u[y == 0])), 4)},
            "auc_u_alone": round(float(roc_auc_score(y, u_only)), 4),
            "auc_embedding": round(float(roc_auc_score(y, raw)), 4),
            "auc_embedding_u_removed": round(float(roc_auc_score(y, residual)), 4),
        }


def main():
    run = Run("0107 urgency axis", ["segments", "archive"])
    segments, archive = HumanSortedSegments(), ArchiveRecordings()
    with run.stage("segments") as stage:
        table = segments.table(DutyCache("segments").measure(segments.tasks(), stage))
    with run.stage("archive") as stage:
        archive_duties = DutyCache("archive").measure(archive.tasks(), stage)
    everything = np.ones(len(table["u"]), dtype=bool)
    report = {
        "A_all_segments": segments.ordering(table, everything),
        "A_control_single_crow": segments.ordering(table, table["crow_count"] == "1"),
        "B_owl_versus_hawk": archive.owl_versus_hawk(archive_duties),
        "C_by_context": archive.by_context(archive_duties),
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    run.note(f"rho={report['A_all_segments']['spearman_rho']} single-crow rho={report['A_control_single_crow']['spearman_rho']}")


if __name__ == "__main__":
    main()
