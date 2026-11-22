"""Experiment 0104 — the pre-registered perched owl vs. perched hawk test, and the exploratory arms.

Reads labels.json (this folder; opaque clip keys, frozen before this script was
first run) and the masked features under data/experiments/0104-perched-posture/.
Writes metrics.json next to this file.

  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0104-does-owl-vs-hawk-survive-perched/eval.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
FEATS = DATA_DIR / "experiments" / "0104-perched-posture"
ARCHIVE = DATA_DIR / "experiments" / "0102-archive-remarks"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

OWLS = ("great_horned_owl", "barred_owl", "other_owl")
HAWKS = ("red_tailed_hawk", "coopers_hawk", "red_shouldered_hawk", "other_hawk")
N_PERM = 400
MAX_PER_CHANNEL = 2


class Clip:
    """One labelled clip joined to its masked audio record."""

    def __init__(self, label: dict, record: dict, row: int):
        self.key = label["key"]
        self.channel = label["channel"]
        self.seen = label["predator_seen"]
        self.state = label["predator_state"]
        self.clean = bool(label["clean_wildlife"])
        self.north_america = bool(label["north_america"])
        self.record = record
        self.row = row

    @property
    def predator(self) -> str | None:
        if self.seen in OWLS:
            return "owl"
        if self.seen in HAWKS:
            return "hawk"
        if self.seen == "bald_eagle":
            return "eagle"
        return None

    @property
    def eligible(self) -> bool:
        return self.clean and self.north_america and self.predator is not None and self.record["n_pure_crow_w"] >= 1

    @property
    def strict(self) -> bool:
        return self.record["max_raptor_conf"] < 0.05

    def density(self) -> list[float]:
        return [self.record["duration_s"], self.record["pure_crow_frac"], float(self.record["n_pure_crow_w"])]


class ClipSet:
    """Labels + records + features, with the subset selectors the protocol names."""

    def __init__(self):
        labels = json.loads((HERE / "labels.json").read_text())
        records = {r["key"]: r for r in json.loads((FEATS / "records.json").read_text())}
        npz = np.load(FEATS / "features.npz")
        row_of = {k: i for i, k in enumerate(npz["keys"].tolist())}
        self.emb = npz["emb_pure_mean"]
        self.caw_x = npz["caw_x"]
        self.caw_rec = npz["caw_rec"]
        self.clips = [Clip(lb, records[lb["key"]], row_of[lb["key"]]) for lb in labels if lb["key"] in records]

    def cell(self, predator: str, state: str, strict: bool) -> list[Clip]:
        return [
            c for c in self.clips
            if c.eligible and c.predator == predator and c.state == state and (c.strict or not strict)
        ]

    @staticmethod
    def cap_per_channel(clips: list[Clip]) -> list[Clip]:
        taken = defaultdict(int)
        kept = []
        for c in sorted(clips, key=lambda c: c.key):
            if taken[c.channel] < MAX_PER_CHANNEL:
                taken[c.channel] += 1
                kept.append(c)
        return kept

    def inventory(self) -> dict:
        out = {}
        for strict in (False, True):
            counts = Counter((c.predator, c.state) for c in self.clips if c.eligible and (c.strict or not strict))
            out["strict" if strict else "all"] = {f"{p}_{s}": n for (p, s), n in sorted(counts.items())}
        out["labelled"] = len(self.clips)
        out["excluded_not_clean"] = sum(not c.clean for c in self.clips)
        out["excluded_not_north_america"] = sum(c.clean and not c.north_america for c in self.clips)
        out["excluded_predator_not_visible_or_other"] = sum(
            c.clean and c.north_america and c.predator is None for c in self.clips
        )
        return out


class GroupedTest:
    """Channel-grouped 5-fold ROC-AUC with a group-level permutation test."""

    def __init__(self, C: float):
        self.C = C

    def _oof(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> np.ndarray | None:
        n_splits = min(5, int(y.sum()), int((1 - y).sum()), len(set(groups)))
        if n_splits < 2:
            return None
        probs = np.zeros(len(y))
        for tr, te in StratifiedGroupKFold(n_splits=n_splits).split(X, y, groups):
            if len(set(y[tr])) < 2:
                return None
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=self.C, solver="liblinear", class_weight="balanced", max_iter=2000),
            ).fit(X[tr], y[tr])
            probs[te] = clf.predict_proba(X[te])[:, 1]
        return probs

    def auc(self, X, y, groups) -> float | None:
        probs = self._oof(X, y, groups)
        return None if probs is None else float(roc_auc_score(y, probs))

    def run(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray, permute: bool, on_step=None) -> dict:
        out = {"n": int(len(y)), "pos": int(y.sum()), "neg": int((1 - y).sum()), "channels": int(len(set(groups)))}
        obs = self.auc(X, y, groups)
        out["auc"] = None if obs is None else round(obs, 4)
        if obs is None or not permute:
            return out
        rng = np.random.default_rng(42)
        uniq = np.array(sorted(set(groups)))
        g_y = np.array([int(round(float(np.mean(y[groups == g])))) for g in uniq])
        hits, vals = 0, []
        for k in range(N_PERM):
            mapping = dict(zip(uniq, rng.permutation(g_y)))
            py = np.array([mapping[g] for g in groups])
            a = self.auc(X, py, groups)
            if a is not None:
                vals.append(a)
                hits += a >= obs
            if on_step and (k + 1) % 20 == 0:
                on_step(k + 1)
        out["perm_p"] = round((hits + 1) / (len(vals) + 1), 4)
        out["perm_mean"] = round(float(np.mean(vals)), 4) if vals else None
        return out


class CawTest:
    """Exploratory: 0103's inverse-recording-weighted per-caw ROC-AUC on the 44-d caw features."""

    def __init__(self, clipset: ClipSet):
        self.clipset = clipset

    def run(self, pos: list[Clip], neg: list[Clip]) -> dict:
        rows, y, groups, rec = [], [], [], []
        for label, clips in ((1, pos), (0, neg)):
            for c in clips:
                idx = np.where(self.clipset.caw_rec == c.row)[0]
                rows.extend(idx.tolist())
                y.extend([label] * len(idx))
                groups.extend([c.channel] * len(idx))
                rec.extend([c.row] * len(idx))
        y, groups, rec = np.array(y), np.array(groups), np.array(rec)
        if len(y) == 0 or len(set(y)) < 2:
            return {"n_caws": int(len(y)), "auc_weighted": None}
        X = self.clipset.caw_x[rows]
        counts = Counter(rec.tolist())
        w = np.array([1.0 / counts[r] for r in rec])
        uniq = sorted(counts)
        r_y = np.array([int(y[rec == r][0]) for r in uniq])
        r_g = np.array([str(groups[rec == r][0]) for r in uniq])
        n_splits = min(5, int(r_y.sum()), int((1 - r_y).sum()), len(set(r_g)))
        if n_splits < 2:
            return {"n_caws": int(len(y)), "n_recs": len(uniq), "auc_weighted": None}
        probs = np.zeros(len(y))
        for tr_r, te_r in StratifiedGroupKFold(n_splits=n_splits).split(np.zeros((len(uniq), 1)), r_y, r_g):
            tr = np.isin(rec, [uniq[i] for i in tr_r])
            te = np.isin(rec, [uniq[i] for i in te_r])
            wt = w[tr].copy()
            for cls in (0, 1):
                m = y[tr] == cls
                wt[m] *= 0.5 / max(wt[m].sum(), 1e-12)
            sc = StandardScaler().fit(X[tr])
            clf = LogisticRegression(C=0.1, solver="liblinear", max_iter=2000).fit(
                sc.transform(X[tr]), y[tr], sample_weight=wt * len(wt)
            )
            probs[te] = clf.predict_proba(sc.transform(X[te]))[:, 1]
        rec_p = np.array([float(np.mean(probs[rec == r])) for r in uniq])
        return {
            "n_caws": int(len(y)),
            "n_recs": len(uniq),
            "auc_weighted": round(float(roc_auc_score(y, probs, sample_weight=w)), 4),
            "auc_rec_mean": round(float(roc_auc_score(r_y, rec_p)), 4),
        }


class ArchiveTransfer:
    """Exploratory: 0102's strict archive owl-vs-hawk model, scored on these clips without refitting."""

    def __init__(self):
        meta = json.loads((ARCHIVE / "records.json").read_text())
        npz = np.load(ARCHIVE / "features.npz")
        idx = [
            i for i, r in enumerate(meta)
            if r["slug"] == "american-crow" and r["witnessed"]
            and r["context"] in ("owl_mobbing", "hawk_mobbing")
            and not r["pred_vocal"] and r["max_raptor_conf"] < 0.05 and npz["has_clean"][i]
        ]
        y = np.array([1 if meta[i]["context"] == "owl_mobbing" else 0 for i in idx])
        self.n_train = len(idx)
        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced", max_iter=2000),
        ).fit(npz["emb_clean"][idx, :1024], y)

    def run(self, emb: np.ndarray, pos: list[Clip], neg: list[Clip]) -> dict:
        if len(pos) < 3 or len(neg) < 3:
            return {"n": len(pos) + len(neg), "auc": None}
        sp = self.model.predict_proba(emb[[c.row for c in pos]])[:, 1]
        sn = self.model.predict_proba(emb[[c.row for c in neg]])[:, 1]
        y = np.array([1] * len(sp) + [0] * len(sn))
        return {
            "n": int(len(y)), "pos": len(sp), "neg": len(sn), "train_n": self.n_train,
            "auc": round(float(roc_auc_score(y, np.concatenate([sp, sn]))), 4),
            "mw_p": round(float(mannwhitneyu(sp, sn, alternative="two-sided")[1]), 4),
            "median_p_owl_pos": round(float(np.median(sp)), 3),
            "median_p_owl_neg": round(float(np.median(sn)), 3),
        }


def arrays(clipset: ClipSet, pos: list[Clip], neg: list[Clip]):
    clips = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg))
    groups = np.array([c.channel for c in clips])
    emb = clipset.emb[[c.row for c in clips]]
    dens = np.array([c.density() for c in clips], dtype=np.float64)
    return emb, dens, y, groups


def density_summary(clips: list[Clip]) -> dict:
    if not clips:
        return {"n": 0}
    return {
        "n": len(clips),
        "pure_crow_frac_median": round(float(np.median([c.record["pure_crow_frac"] for c in clips])), 3),
        "duty_cycle_median": round(float(np.median([c.record["duty_cycle"] for c in clips])), 3),
        "n_pure_windows_median": float(np.median([c.record["n_pure_crow_w"] for c in clips])),
        "duration_median_s": round(float(np.median([c.record["duration_s"] for c in clips])), 1),
    }


def main():
    clipset = ClipSet()
    run = Run("0104 perched owl vs hawk evaluation", ["primary", "exploratory"])
    report = {"inventory": clipset.inventory()}
    emb_test, null_test = GroupedTest(C=0.05), GroupedTest(C=0.5)

    with run.stage("primary") as st:
        owl = clipset.cap_per_channel(clipset.cell("owl", "perched", strict=True))
        hawk = clipset.cap_per_channel(clipset.cell("hawk", "perched", strict=True))
        emb, dens, y, groups = arrays(clipset, owl, hawk)
        primary = emb_test.run(emb, y, groups, permute=True, on_step=lambda k: st.update(k, N_PERM))
        primary["density_null"] = null_test.run(dens, y, groups, permute=False)
        primary["owl_density"] = density_summary(owl)
        primary["hawk_density"] = density_summary(hawk)
        report["PRIMARY_perched_owl_vs_perched_hawk_strict"] = primary
        st.update(N_PERM, N_PERM)

    with run.stage("exploratory") as st:
        expl = {}
        owl_ns = clipset.cap_per_channel(clipset.cell("owl", "perched", strict=False))
        hawk_ns = clipset.cap_per_channel(clipset.cell("hawk", "perched", strict=False))
        emb, dens, y, groups = arrays(clipset, owl_ns, hawk_ns)
        expl["perched_owl_vs_hawk_nonstrict"] = {
            **emb_test.run(emb, y, groups, permute=True), "density_null": null_test.run(dens, y, groups, permute=False),
        }
        st.update(1, 7)
        owl_nc, hawk_nc = clipset.cell("owl", "perched", strict=True), clipset.cell("hawk", "perched", strict=True)
        emb, dens, y, groups = arrays(clipset, owl_nc, hawk_nc)
        expl["perched_owl_vs_hawk_strict_no_channel_cap"] = emb_test.run(emb, y, groups, permute=True)
        st.update(2, 7)

        caw = CawTest(clipset)
        expl["caw_44d_perched_owl_vs_hawk_strict"] = caw.run(owl, hawk)
        expl["caw_44d_perched_owl_vs_hawk_nonstrict"] = caw.run(owl_ns, hawk_ns)
        st.update(3, 7)

        hawk_fly = clipset.cap_per_channel(clipset.cell("hawk", "flying", strict=False))
        emb, dens, y, groups = arrays(clipset, hawk_ns, hawk_fly)
        expl["within_hawk_perched_vs_flying_nonstrict"] = {
            **emb_test.run(emb, y, groups, permute=True), "density_null": null_test.run(dens, y, groups, permute=False),
        }
        st.update(4, 7)
        eagle = clipset.cap_per_channel(clipset.cell("eagle", "perched", strict=False))
        emb, dens, y, groups = arrays(clipset, hawk_ns, eagle)
        expl["perched_hawk_vs_perched_eagle_nonstrict"] = emb_test.run(emb, y, groups, permute=True)
        st.update(5, 7)

        transfer = ArchiveTransfer()
        expl["archive_model_zero_shot"] = {
            "perched_owl_vs_perched_hawk_strict": transfer.run(clipset.emb, owl, hawk),
            "perched_owl_vs_perched_hawk_nonstrict": transfer.run(clipset.emb, owl_ns, hawk_ns),
            "perched_owl_vs_flying_hawk_nonstrict": transfer.run(clipset.emb, owl_ns, hawk_fly),
            "perched_hawk_vs_flying_hawk_nonstrict": transfer.run(clipset.emb, hawk_ns, hawk_fly),
        }
        st.update(6, 7)
        expl["density_by_cell_nonstrict"] = {
            "owl_perched": density_summary(owl_ns), "hawk_perched": density_summary(hawk_ns),
            "hawk_flying": density_summary(hawk_fly), "eagle_perched": density_summary(eagle),
        }
        report["EXPLORATORY"] = expl
        st.update(7, 7)

    (HERE / "metrics.json").write_text(json.dumps(report, indent=2))
    p = report["PRIMARY_perched_owl_vs_perched_hawk_strict"]
    run.note(f"primary AUC={p['auc']} perm_p={p.get('perm_p')} n={p['pos']} owl / {p['neg']} hawk")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
