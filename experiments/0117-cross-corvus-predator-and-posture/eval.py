"""0117 step 3: evaluate cross-Corvus predator & posture conservation with zero geography leak:
  - Primary A: Zero-shot Eurasian Corvus -> American Crow (owl vs. hawk, strict)
  - Primary B: Species-deconfounded Avian Raptor vs. Terrestrial Mammal across all Corvus
  - Primary C: Cross-Corvus strict Perched Owl vs. Perched Hawk
  - S1: Perch 2.0 on Primaries A, B, C
  - S2: Cross-Corvus within-hawk Perched vs. Flying + zero-shot Eurasian -> 0104 American Crow videos
  - S3: Per-species breakdown

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0117-cross-corvus-predator-and-posture/eval.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import warnings
from collections import Counter, defaultdict
from importlib import util
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0117-cross-corvus"
WIN_DIR = CACHE_DIR / "windows"
PERCH_OUT = CACHE_DIR / "perch.npz"
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"
EXP116 = REPO / "experiments" / "0116-sibling-checklist-posture-recovery"

sys.path.insert(0, str(EXP112))
import sets  # noqa: E402

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exp104 = load_module("exp104_0117", sets.EXP104 / "eval.py")
exp112_eval = load_module("exp112_0117", EXP112 / "evaluate.py")


def holm_adjust(p_map: dict[str, float | None]) -> dict[str, float | None]:
    valid = {k: v for k, v in p_map.items() if v is not None}
    ordered = sorted(valid, key=valid.get)
    running = 0.0
    out: dict[str, float | None] = {k: None for k in p_map}
    for rank, k in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * valid[k]))
        out[k] = round(running, 4)
    return out


def fit_species_scalers(X: np.ndarray, species: np.ndarray) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], tuple[np.ndarray, np.ndarray]]:
    g_mean = X.mean(axis=0)
    g_std = np.where(X.std(axis=0) > 1e-6, X.std(axis=0), 1.0)
    per_sp = {}
    for sp in set(species.tolist()):
        m = species == sp
        if int(m.sum()) >= 3:
            mu = X[m].mean(axis=0)
            sd = np.where(X[m].std(axis=0) > 1e-6, X[m].std(axis=0), 1.0)
            per_sp[sp] = (mu, sd)
    return per_sp, (g_mean, g_std)


def apply_species_scalers(X: np.ndarray, species: np.ndarray, per_sp: dict, global_stats: tuple) -> np.ndarray:
    out = np.empty_like(X, dtype=np.float64)
    g_mu, g_sd = global_stats
    for i, sp in enumerate(species.tolist()):
        mu, sd = per_sp.get(sp, (g_mu, g_sd))
        out[i] = (X[i] - mu) / sd
    return out


class SpeciesDeconfoundedCV:
    """5-fold recordist-grouped ROC-AUC with within-fold species z-scoring + species one-hot
    orthogonalization, and 400 within-species recordist permutations."""

    def __init__(self, C: float = 0.05, n_perm: int = 400):
        self.C = C
        self.n_perm = n_perm

    def _oof_auc(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray, species: np.ndarray, deconfound: bool = True) -> float | None:
        n_splits = min(5, int(y.sum()), int((1 - y).sum()), len(set(groups)))
        if n_splits < 2:
            return None
        probs = np.zeros(len(y))
        ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore").fit(species.reshape(-1, 1))
        Z = np.column_stack([np.ones(len(X)), ohe.transform(species.reshape(-1, 1))])
        for tr, te in StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=0).split(X, y, groups):
            if len(set(y[tr])) < 2:
                return None
            if deconfound:
                per_sp, glob = fit_species_scalers(X[tr], species[tr])
                Xs = apply_species_scalers(X, species, per_sp, glob)
                beta, *_ = np.linalg.lstsq(Z[tr], Xs[tr], rcond=None)
                Xr = Xs - Z @ beta
            else:
                Xr = X
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=self.C, solver="liblinear", class_weight="balanced", max_iter=2000),
            ).fit(Xr[tr], y[tr])
            probs[te] = clf.predict_proba(Xr[te])[:, 1]
        return float(roc_auc_score(y, probs))

    def run(self, X: np.ndarray, D_meta: np.ndarray, y: np.ndarray, groups: np.ndarray, species: np.ndarray, permute: bool = True) -> dict:
        obs = self._oof_auc(X, y, groups, species, deconfound=True)
        raw_meta_auc = self._oof_auc(D_meta, y, groups, species, deconfound=False)
        deconf_meta_auc = self._oof_auc(D_meta, y, groups, species, deconfound=True)
        out = {
            "n": int(len(y)),
            "pos": int(y.sum()),
            "neg": int((1 - y).sum()),
            "groups": int(len(set(groups))),
            "by_species": {
                sp: {"pos": int(y[species == sp].sum()), "neg": int((1 - y[species == sp]).sum())}
                for sp in sorted(set(species.tolist()))
            },
            "auc": None if obs is None else round(obs, 4),
            "raw_metadata_plus_species_null_auc": None if raw_meta_auc is None else round(raw_meta_auc, 4),
            "species_deconfounded_density_meta_null_auc": None if deconf_meta_auc is None else round(deconf_meta_auc, 4),
        }
        if obs is None or not permute:
            return out

        rng = np.random.default_rng(42)
        sp_blocks = {}
        for sp in sorted(set(species.tolist())):
            m = species == sp
            ug = np.array(sorted(set(groups[m])))
            gy = np.array([int(round(float(np.mean(y[(groups == g) & m])))) for g in ug])
            sp_blocks[sp] = (ug, gy)

        vals = []
        for _ in range(self.n_perm):
            mp = {}
            for sp, (ug, gy) in sp_blocks.items():
                mp[(sp,)] = dict(zip(ug, rng.permutation(gy)))
            py = np.array([mp[(sp,)][g] for sp, g in zip(species, groups)])
            a = self._oof_auc(X, py, groups, species, deconfound=True)
            if a is not None:
                vals.append(a)
        out["perm_p"] = round((sum(v >= obs for v in vals) + 1) / (len(vals) + 1), 4)
        out["perm_mean"] = round(float(np.mean(vals)), 4) if vals else None
        return out


def zero_shot_transfer(X_tr: np.ndarray, y_tr: np.ndarray, sp_tr: np.ndarray, X_te: np.ndarray, y_te: np.ndarray, g_te: np.ndarray) -> dict:
    if len(y_tr) == 0 or int(y_tr.sum()) < 3 or int((1 - y_tr).sum()) < 3 or len(y_te) == 0:
        return {"train_pos": int(y_tr.sum()), "train_neg": int((1 - y_tr).sum()), "test_n": len(y_te), "auc": None}
    per_sp, glob = fit_species_scalers(X_tr, sp_tr)
    X_tr_z = apply_species_scalers(X_tr, sp_tr, per_sp, glob)
    clf = LogisticRegression(C=0.05, solver="liblinear", class_weight="balanced", max_iter=2000).fit(X_tr_z, y_tr)

    # Target species standardized using its own unlabeled marginal mean/std (zero label info)
    X_te_z = StandardScaler().fit_transform(X_te)
    scores = clf.decision_function(X_te_z)
    auc = float(roc_auc_score(y_te, scores))
    mw_p = float(mannwhitneyu(scores[y_te == 1], scores[y_te == 0], alternative="two-sided")[1])

    # Recordist bootstrap 95% CI
    members = defaultdict(list)
    for idx, g in enumerate(g_te.tolist()):
        members[g].append(idx)
    keys = list(members)
    rng = np.random.default_rng(0)
    boot = []
    for _ in range(2000):
        draw = np.concatenate([members[keys[j]] for j in rng.integers(0, len(keys), len(keys))])
        yb = y_te[draw]
        if 0 < yb.sum() < len(yb):
            boot.append(float(roc_auc_score(yb, scores[draw])))
    ci = [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]
    return {
        "train_n": int(len(y_tr)),
        "train_pos": int(y_tr.sum()),
        "train_neg": int((1 - y_tr).sum()),
        "underpowered_train": bool(min(int(y_tr.sum()), int((1 - y_tr).sum())) < 10),
        "test_n": int(len(y_te)),
        "test_pos": int(y_te.sum()),
        "test_neg": int((1 - y_te).sum()),
        "auc": round(auc, 4),
        "ci95": ci,
        "mw_p": round(mw_p, 5),
    }


def main():
    run = Run("0117 cross-Corvus predator & posture evaluation", ["load", "primaries", "secondaries"])

    with run.stage("load") as st:
        labs_0117 = json.loads((HERE / "labels.json").read_text())["labels"]
        perch_0117 = {}
        if PERCH_OUT.exists():
            saved = np.load(PERCH_OUT)
            perch_0117 = dict(zip(saved["ids"].tolist(), saved["embeddings"]))

        # Load DB metadata for all relevant recordings
        labs_102 = json.loads((sets.EXP102 / "labels.json").read_text())
        post_116_path = EXP116 / "checklist_posture_labels.json"
        post_116 = (
            {r["id"]: r for r in json.loads(post_116_path.read_text())["labels"]}
            if post_116_path.exists()
            else {}
        )
        post_103 = json.loads((sets.EXP103 / "posture_labels.json").read_text())
        p103_by_id = (
            {int(k): v["posture"] if isinstance(v, dict) else v for k, v in post_103.items()}
            if isinstance(post_103, dict)
            else {int(r["id"]): r["posture"] for r in post_103}
        )

        all_ids = sorted(
            {r["id"] for r in labs_0117 if r.get("witnessed")}
            | {r["id"] for r in labs_102 if r.get("slug") == "american-crow" and r.get("witnessed")}
        )
        con = sqlite3.connect(f"file:{sets.DB}?mode=ro", uri=True)
        db_meta = {
            rid: {"slug": slug, "recordist": (rec or f"rec:{rid}").strip().lower(), "lat": lat or 0.0, "lng": lng or 0.0, "dur": float(dur or 0.0)}
            for rid, slug, rec, lat, lng, dur in con.execute(
                f"SELECT id, slug, recordist, lat, lng, duration_seconds FROM recordings WHERE id IN ({','.join(map(str, all_ids))})"
            ).fetchall()
        }
        con.close()

        # 1) Non-American Corvus rows (scanned in 0117)
        non_amecro = []
        for r in labs_0117:
            if not r.get("witnessed") or r.get("context") == "none":
                continue
            rid = r["id"]
            wpath = WIN_DIR / f"c{rid}.npz"
            if not wpath.exists() or rid not in db_meta:
                continue
            d = np.load(wpath)
            pure = ((d["target_species"] >= 0.25) | (d["corvid"] >= 0.25)) & (d["non_corvid"] < 0.05) & (d["raptor"] < 0.05)
            if not pure.any():
                continue
            strict = (not bool(r.get("pred_vocal"))) and float(d["raptor"].max()) < 0.05
            bn = d["embedding"][pure].mean(axis=0).astype(np.float32)
            p_vecs = [perch_0117.get(f"c{rid}@{float(s):.2f}") for s in d["start"][pure]]
            p_vecs = [v.astype(np.float32) for v in p_vecs if v is not None]
            pe = np.mean(p_vecs, axis=0) if p_vecs else None
            m = db_meta[rid]
            dur_s = m["dur"] if m["dur"] > 0 else float(len(d["start"]) * 3.0)
            non_amecro.append({
                "id": rid,
                "slug": m["slug"],
                "context": r["context"],
                "posture": r.get("posture", "unknown"),
                "strict": strict,
                "eurasian": (m["lng"] == 0.0 or m["lng"] > -30.0),
                "group": f"{m['slug']}:{m['recordist']}",
                "meta": np.array([m["lat"], m["lng"], dur_s, float(pure.mean()), float(pure.sum())], dtype=np.float64),
                "birdnet": bn,
                "perch": pe,
            })

        # 2) American Crow strict archive rows (from 0112 + 0117 mammal/human scan)
        reps_112 = exp112_eval.Representations()
        meta_102_rec = {r["id"]: r for r in json.loads((sets.ARCHIVE_CACHE / "records.json").read_text())}
        amecro = []
        for r in labs_102:
            if r.get("slug") != "american-crow" or not r.get("witnessed"):
                continue
            ctx = r.get("context")
            if ctx not in ("owl_mobbing", "hawk_mobbing", "mammal_scold", "human_disturbance"):
                continue
            rid = r["id"]
            if rid not in db_meta:
                continue
            m = db_meta[rid]
            if sets.WindowTable.exists(f"a{rid}"):
                wt = sets.WindowTable(f"a{rid}")
                pure = wt.pure() & (wt.raptor < 0.05)
                if not pure.any():
                    continue
                bn = reps_112.window_mean("birdnet", wt, pure)
                pe = reps_112.window_mean("perch", wt, pure)
                p116 = post_116.get(rid)
                pred_voc_cl = bool(p116.get("pred_vocal_checklist")) if p116 else False
                max_rap = max(float(meta_102_rec.get(rid, {}).get("max_raptor_conf", 0.0)), float(wt.raptor.max()))
                strict = (not bool(r.get("pred_vocal"))) and (not pred_voc_cl) and (max_rap < 0.05)
                posture = p116["posture"] if p116 else p103_by_id.get(rid, "unknown")
                dur_s = m["dur"] if m["dur"] > 0 else float(len(wt.start) * 3.0)
                pure_frac, pure_n = float(pure.mean()), float(pure.sum())
            elif (WIN_DIR / f"c{rid}.npz").exists():
                d = np.load(WIN_DIR / f"c{rid}.npz")
                pure = (d["target_species"] >= 0.25) & (d["non_corvid"] < 0.05) & (d["raptor"] < 0.05)
                if not pure.any():
                    continue
                bn = d["embedding"][pure].mean(axis=0).astype(np.float32)
                p_vecs = [perch_0117.get(f"c{rid}@{float(s):.2f}") for s in d["start"][pure]]
                p_vecs = [v.astype(np.float32) for v in p_vecs if v is not None]
                pe = np.mean(p_vecs, axis=0) if p_vecs else None
                strict = (not bool(r.get("pred_vocal"))) and float(d["raptor"].max()) < 0.05
                posture = "unknown"
                dur_s = m["dur"] if m["dur"] > 0 else float(len(d["start"]) * 3.0)
                pure_frac, pure_n = float(pure.mean()), float(pure.sum())
            else:
                continue
            if bn is None:
                continue
            amecro.append({
                "id": rid,
                "slug": "american-crow",
                "context": ctx,
                "posture": posture,
                "strict": strict,
                "eurasian": False,
                "group": f"american-crow:{m['recordist']}",
                "meta": np.array([m["lat"], m["lng"], dur_s, pure_frac, pure_n], dtype=np.float64),
                "birdnet": bn,
                "perch": pe,
            })
        st.update(1, 1)

    inventory = {
        "non_amecro_coded_witnessed": sum(1 for r in labs_0117 if r.get("witnessed") and r.get("context") != "none"),
        "non_amecro_usable_pure": len(non_amecro),
        "non_amecro_strict_by_slug_context": {
            f"{slug}_{ctx}": n
            for (slug, ctx), n in sorted(Counter((r["slug"], r["context"]) for r in non_amecro if r["strict"]).items())
        },
        "non_amecro_strict_raptor_posture": {
            f"{ctx}_{pos}": n
            for (ctx, pos), n in sorted(
                Counter((r["context"], r["posture"]) for r in non_amecro if r["strict"] and r["context"] in ("owl_mobbing", "hawk_mobbing")).items()
            )
        },
        "amecro_strict_by_context": dict(Counter(r["context"] for r in amecro if r["strict"])),
    }

    cv_runner = SpeciesDeconfoundedCV(C=0.05, n_perm=400)

    def run_all_primaries(rep_name: str, permute: bool = True) -> dict:
        # Primary A: Zero-shot Eurasian Corvus -> American Crow (strict owl vs hawk)
        tr_a = [
            r for r in non_amecro
            if r["strict"] and r["eurasian"] and r["context"] in ("owl_mobbing", "hawk_mobbing") and r[rep_name] is not None
        ]
        te_a = [
            r for r in amecro
            if r["strict"] and r["context"] in ("owl_mobbing", "hawk_mobbing") and r[rep_name] is not None
        ]
        X_tr = np.stack([r[rep_name] for r in tr_a]) if tr_a else np.zeros((0, 1))
        y_tr = np.array([1 if r["context"] == "owl_mobbing" else 0 for r in tr_a])
        sp_tr = np.array([r["slug"] for r in tr_a])
        X_te = np.stack([r[rep_name] for r in te_a])
        y_te = np.array([1 if r["context"] == "owl_mobbing" else 0 for r in te_a])
        g_te = np.array([r["group"] for r in te_a])
        pa = zero_shot_transfer(X_tr, y_tr, sp_tr, X_te, y_te, g_te)

        # Primary B: Avian Raptor (owl + hawk) vs Terrestrial Mammal (mammal_scold), strict, all Corvus
        pb_rows = [
            r for r in (non_amecro + amecro)
            if r["strict"] and r["context"] in ("owl_mobbing", "hawk_mobbing", "mammal_scold") and r[rep_name] is not None
        ]
        Xb = np.stack([r[rep_name] for r in pb_rows])
        Db = np.stack([r["meta"] for r in pb_rows])
        yb = np.array([1 if r["context"] == "mammal_scold" else 0 for r in pb_rows])
        gb = np.array([r["group"] for r in pb_rows])
        spb = np.array([r["slug"] for r in pb_rows])
        pb = cv_runner.run(Xb, Db, yb, gb, spb, permute=permute)

        # Primary C: Cross-Corvus strict Perched Owl vs Perched Hawk
        pc_rows = [
            r for r in (non_amecro + amecro)
            if r["strict"] and r["context"] in ("owl_mobbing", "hawk_mobbing") and r["posture"] == "perched" and r[rep_name] is not None
        ]
        if len(pc_rows) >= 6:
            Xc = np.stack([r[rep_name] for r in pc_rows])
            Dc = np.stack([r["meta"] for r in pc_rows])
            yc = np.array([1 if r["context"] == "owl_mobbing" else 0 for r in pc_rows])
            gc = np.array([r["group"] for r in pc_rows])
            spc = np.array([r["slug"] for r in pc_rows])
            pc = cv_runner.run(Xc, Dc, yc, gc, spc, permute=permute)
        else:
            pc = {"n": len(pc_rows), "auc": None}
        return {"A_zeroshot_eurasian_to_amecro_owl_vs_hawk": pa, "B_raptor_vs_mammal_deconfounded": pb, "C_perched_owl_vs_hawk_all_corvus": pc}

    with run.stage("primaries") as st:
        prim = run_all_primaries("birdnet", permute=True)
        holm_p = holm_adjust({
            "A": prim["A_zeroshot_eurasian_to_amecro_owl_vs_hawk"].get("mw_p"),
            "B": prim["B_raptor_vs_mammal_deconfounded"].get("perm_p"),
            "C": prim["C_perched_owl_vs_hawk_all_corvus"].get("perm_p"),
        })
        pa = prim["A_zeroshot_eurasian_to_amecro_owl_vs_hawk"]
        pa["holm_p"] = holm_p["A"]
        pa["passes"] = bool(
            not pa.get("underpowered_train", True)
            and pa.get("auc") is not None and pa["auc"] >= 0.65
            and pa["ci95"][0] > 0.5 and (holm_p["A"] or 1.0) < 0.05
        )
        pb = prim["B_raptor_vs_mammal_deconfounded"]
        pb["holm_p"] = holm_p["B"]
        pb_null = pb.get("species_deconfounded_density_meta_null_auc") or 0.5
        pb["passes"] = bool(
            pb.get("auc") is not None and pb["auc"] >= 0.65
            and (holm_p["B"] or 1.0) < 0.05 and (pb["auc"] - pb_null) >= 0.05
        )
        pc = prim["C_perched_owl_vs_hawk_all_corvus"]
        pc["holm_p"] = holm_p["C"]
        pc_null = pc.get("species_deconfounded_density_meta_null_auc") or 0.5
        pc["passes"] = bool(
            pc.get("auc") is not None and pc["auc"] >= 0.65
            and (holm_p["C"] or 1.0) < 0.05 and (pc["auc"] - pc_null) >= 0.05
        )
        st.update(1, 1)

    with run.stage("secondaries") as st:
        s1_perch = run_all_primaries("perch", permute=True)
        st.update(1, 3)

        # S2: Within-hawk perched vs flying across Corvus + Eurasian zero-shot -> 0104 American Crow hawk videos
        hawk_pf_strict = [
            r for r in (non_amecro + amecro)
            if r["strict"] and r["context"] == "hawk_mobbing" and r["posture"] in ("perched", "flying")
        ]
        hawk_pf_nonstrict = [
            r for r in (non_amecro + amecro)
            if r["context"] == "hawk_mobbing" and r["posture"] in ("perched", "flying")
        ]
        s2 = {}
        for tag, sub in (("strict", hawk_pf_strict), ("nonstrict", hawk_pf_nonstrict)):
            if len(sub) >= 8:
                Xs = np.stack([r["birdnet"] for r in sub])
                Ds = np.stack([r["meta"] for r in sub])
                ys = np.array([1 if r["posture"] == "perched" else 0 for r in sub])
                gs = np.array([r["group"] for r in sub])
                sps = np.array([r["slug"] for r in sub])
                s2[f"all_corvus_{tag}_birdnet"] = cv_runner.run(Xs, Ds, ys, gs, sps, permute=True)
        # Zero-shot Eurasian hawk perched vs flying -> 0104 American Crow hawk perched vs flying
        eur_hawk_pf = [r for r in non_amecro if r["eurasian"] and r["context"] == "hawk_mobbing" and r["posture"] in ("perched", "flying")]
        cs104 = exp104.ClipSet()
        v_hp = cs104.cap_per_channel(cs104.cell("hawk", "perched", strict=False))
        v_hf = cs104.cap_per_channel(cs104.cell("hawk", "flying", strict=False))
        if len(eur_hawk_pf) >= 6:
            X_tr_pf = np.stack([r["birdnet"] for r in eur_hawk_pf])
            y_tr_pf = np.array([1 if r["posture"] == "perched" else 0 for r in eur_hawk_pf])
            sp_tr_pf = np.array([r["slug"] for r in eur_hawk_pf])
            X_te_pf = cs104.emb[[c.row for c in v_hp + v_hf]]
            y_te_pf = np.array([1] * len(v_hp) + [0] * len(v_hf))
            g_te_pf = np.array([c.channel for c in v_hp + v_hf])
            s2["zeroshot_eurasian_hawk_posture_to_0104_video_birdnet"] = zero_shot_transfer(
                X_tr_pf, y_tr_pf, sp_tr_pf, X_te_pf, y_te_pf, g_te_pf
            )
        st.update(2, 3)

        # S3: Per-species breakdown where both sides >= 8
        s3 = {}
        by_sp = defaultdict(list)
        for r in non_amecro + amecro:
            if r["strict"]:
                by_sp[r["slug"]].append(r)
        single_test = exp104.GroupedTest(C=0.05)
        for sp, rows_sp in sorted(by_sp.items()):
            rap = [r for r in rows_sp if r["context"] in ("owl_mobbing", "hawk_mobbing")]
            mam = [r for r in rows_sp if r["context"] == "mammal_scold"]
            if len(rap) >= 8 and len(mam) >= 8:
                sub = mam + rap
                s3[f"{sp}_mammal_vs_raptor"] = single_test.run(
                    np.stack([r["birdnet"] for r in sub]),
                    np.array([1] * len(mam) + [0] * len(rap)),
                    np.array([r["group"] for r in sub]),
                    permute=True,
                )
            owls = [r for r in rows_sp if r["context"] == "owl_mobbing"]
            hawks = [r for r in rows_sp if r["context"] == "hawk_mobbing"]
            if len(owls) >= 8 and len(hawks) >= 8:
                sub = owls + hawks
                s3[f"{sp}_owl_vs_hawk"] = single_test.run(
                    np.stack([r["birdnet"] for r in sub]),
                    np.array([1] * len(owls) + [0] * len(hawks)),
                    np.array([r["group"] for r in sub]),
                    permute=True,
                )
        st.update(3, 3)

    report = {
        "inventory": inventory,
        "PRIMARY_birdnet": prim,
        "S1_perch": s1_perch,
        "S2_hawk_posture_cross_corvus": s2,
        "S3_within_species": s3,
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    run.note(
        f"A(ZS owl/hawk)={prim['A_zeroshot_eurasian_to_amecro_owl_vs_hawk'].get('auc')}, "
        f"B(mam/rap)={prim['B_raptor_vs_mammal_deconfounded'].get('auc')}, "
        f"C(perched)={prim['C_perched_owl_vs_hawk_all_corvus'].get('auc')}"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
