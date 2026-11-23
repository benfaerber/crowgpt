"""0116 step 3: evaluate enlarged strict archive perched owl vs. perched hawk (plus Perch/CrowGPT,
within-hawk perched vs. flying, and pooled archive + 0104 video perched meta-analysis).

Reads frozen checklist_posture_labels.json (ids and discrete codes only).

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0116-sibling-checklist-posture-recovery/eval.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import warnings
from collections import Counter
from importlib import util
from pathlib import Path

import librosa
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
EXP112 = REPO / "experiments" / "0112-does-crowgpt-hear-what-birdnet-misses"
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


exp104 = load_module("exp104_0116", sets.EXP104 / "eval.py")
exp112_eval = load_module("exp112_0116", EXP112 / "evaluate.py")


def holm_adjust(p_map: dict[str, float | None]) -> dict[str, float | None]:
    valid = {k: v for k, v in p_map.items() if v is not None}
    ordered = sorted(valid, key=valid.get)
    running = 0.0
    out: dict[str, float | None] = {k: None for k in p_map}
    for rank, k in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * valid[k]))
        out[k] = round(running, 4)
    return out


class DomainResidualisedTest:
    """5-fold group-stratified ROC-AUC with domain indicator regressed out inside each fold
    and within-domain group permutations."""

    def __init__(self, C: float = 0.05, n_perm: int = 400):
        self.C = C
        self.n_perm = n_perm

    def _auc(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray, domain: np.ndarray) -> float | None:
        n_splits = min(5, int(y.sum()), int((1 - y).sum()), len(set(groups)))
        if n_splits < 2:
            return None
        probs = np.zeros(len(y))
        z = np.column_stack([np.ones(len(X)), domain.astype(np.float64)])
        for tr, te in StratifiedGroupKFold(n_splits=n_splits).split(X, y, groups):
            if len(set(y[tr])) < 2:
                return None
            beta, *_ = np.linalg.lstsq(z[tr], X[tr], rcond=None)
            Xr = X - z @ beta
            clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=self.C, solver="liblinear", class_weight="balanced", max_iter=2000),
            ).fit(Xr[tr], y[tr])
            probs[te] = clf.predict_proba(Xr[te])[:, 1]
        return float(roc_auc_score(y, probs))

    def run(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray, domain: np.ndarray) -> dict:
        obs = self._auc(X, y, groups, domain)
        out = {
            "n": int(len(y)),
            "pos_owl": int(y.sum()),
            "neg_hawk": int((1 - y).sum()),
            "archive_n": int((domain == 0).sum()),
            "video_n": int((domain == 1).sum()),
            "groups": int(len(set(groups))),
            "auc": None if obs is None else round(obs, 4),
        }
        if obs is None:
            return out
        rng = np.random.default_rng(42)
        # Permute group labels strictly within each domain (archive vs video)
        dom_groups = {}
        for d_val in (0, 1):
            mask_d = domain == d_val
            ug = np.array(sorted(set(groups[mask_d])))
            gy = np.array([int(round(float(np.mean(y[(groups == g) & mask_d])))) for g in ug])
            dom_groups[d_val] = (ug, gy)

        vals = []
        for _ in range(self.n_perm):
            mp = {}
            for d_val, (ug, gy) in dom_groups.items():
                mp.update(zip(ug, rng.permutation(gy)))
            py = np.array([mp[g] for g in groups])
            a = self._auc(X, py, groups, domain)
            if a is not None:
                vals.append(a)
        out["perm_p"] = round((sum(v >= obs for v in vals) + 1) / (len(vals) + 1), 4)
        out["perm_mean"] = round(float(np.mean(vals)), 4) if vals else None
        return out


def main():
    coded = json.loads((HERE / "checklist_posture_labels.json").read_text())
    coded_by_id = {r["id"]: r for r in coded["labels"]}

    meta_102 = {r["id"]: r for r in json.loads((sets.ARCHIVE_CACHE / "records.json").read_text())}
    labs_102 = {r["id"]: r for r in json.loads((sets.EXP102 / "labels.json").read_text())}

    con = sqlite3.connect(f"file:{sets.DB}?mode=ro", uri=True)
    db_rows = {
        rid: (fp, rec, dur)
        for rid, fp, rec, dur in con.execute(
            f"SELECT id, file_path, recordist, duration_seconds FROM recordings WHERE id IN ({','.join(map(str, coded_by_id))})"
        ).fetchall()
    }
    con.close()

    reps = exp112_eval.Representations()
    run = Run("0116 sibling checklist posture evaluation", ["inventory", "primary", "secondary"])

    records = []
    missing_windows = 0
    for rid, c in sorted(coded_by_id.items()):
        key = f"a{rid}"
        if not sets.WindowTable.exists(key):
            missing_windows += 1
            continue
        table = sets.WindowTable(key)
        pure = table.pure() & (table.raptor < 0.05)
        if not pure.any():
            continue
        m102 = meta_102.get(rid, {})
        l102 = labs_102.get(rid, {})
        fp, rec_name, dur_db = db_rows.get(rid, (None, "", None))
        path = sets.resolve_audio_path(fp)
        dur_s = float(dur_db) if dur_db else (float(librosa.get_duration(path=path)) if path else float(len(table.start) * 3.0))

        bn_vec = reps.window_mean("birdnet", table, pure)
        pe_vec = reps.window_mean("perch", table, pure)
        cg_vec = reps.window_mean("crowgpt_b4", table, pure)
        if bn_vec is None:
            continue

        strict_zero_raptor = (
            not bool(l102.get("pred_vocal"))
            and not bool(c.get("pred_vocal_checklist"))
            and float(m102.get("max_raptor_conf", 0.0)) < 0.05
            and float(table.raptor.max()) < 0.05
        )
        records.append({
            "id": rid,
            "key": key,
            "context": c["context"],
            "posture": c["posture"],
            "posture_0103_preserved": c["posture_preserve_0103"],
            "strict": strict_zero_raptor,
            "group": (rec_name or f"rec:{rid}").strip().lower(),
            "density": np.array([dur_s, float(pure.mean()), float(pure.sum())], dtype=np.float64),
            "birdnet": bn_vec,
            "perch": pe_vec,
            "crowgpt_b4": cg_vec,
        })

    with run.stage("inventory") as st:
        before_counts = Counter((c["context"], c.get("posture_0103") or "not_in_0103") for c in coded["labels"])
        after_all_counts = Counter((c["context"], c["posture"]) for c in coded["labels"])
        strict_counts = Counter((r["context"], r["posture"]) for r in records if r["strict"])
        nonstrict_counts = Counter((r["context"], r["posture"]) for r in records)
        inventory = {
            "total_witnessed_owl_hawk_0102": len(coded["labels"]),
            "missing_window_tables": missing_windows,
            "usable_pure_crow_recordings": len(records),
            "strict_usable_recordings": sum(r["strict"] for r in records),
            "new_pred_vocal_caught_by_checklist": sum(bool(c.get("pred_vocal_checklist")) and not bool(labs_102[c["id"]].get("pred_vocal")) for c in coded["labels"]),
            "posture_recovered_from_unknown": sum((c.get("posture_0103") in (None, "unknown")) and c["posture"] != "unknown" for c in coded["labels"]),
            "before_0103_table": {f"{ctx}_{p}": n for (ctx, p), n in sorted(before_counts.items())},
            "after_checklist_all_coded": {f"{ctx}_{p}": n for (ctx, p), n in sorted(after_all_counts.items())},
            "strict_pure_crow_cells": {f"{ctx}_{p}": n for (ctx, p), n in sorted(strict_counts.items())},
            "nonstrict_pure_crow_cells": {f"{ctx}_{p}": n for (ctx, p), n in sorted(nonstrict_counts.items())},
        }
        st.update(1, 1)

    emb_test = exp104.GroupedTest(C=0.05)
    null_test = exp104.GroupedTest(C=0.5)

    def eval_subset(rows: list[dict], pos_fn, rep_name: str = "birdnet", permute: bool = True) -> dict:
        sub = [r for r in rows if r[rep_name] is not None]
        if not sub:
            return {"n": 0, "auc": None}
        X = np.stack([r[rep_name] for r in sub])
        D = np.stack([r["density"] for r in sub])
        y = np.array([1 if pos_fn(r) else 0 for r in sub])
        g = np.array([r["group"] for r in sub])
        res = emb_test.run(X, y, g, permute=permute)
        res["density_null"] = null_test.run(D, y, g, permute=False)
        return res

    with run.stage("primary") as st:
        strict_perched = [r for r in records if r["strict"] and r["posture"] == "perched"]
        primary = eval_subset(strict_perched, lambda r: r["context"] == "owl_mobbing", "birdnet", permute=True)
        d_auc = primary["density_null"]["auc"] or 0.5
        primary["power_status"] = (
            "uninterpretable (<15 in a class)" if min(primary.get("pos", 0), primary.get("neg", 0)) < 15
            else ("underpowered (<50 in a class)" if min(primary.get("pos", 0), primary.get("neg", 0)) < 50 else "powered (>=50/class)")
        )
        primary["passes"] = bool(
            min(primary.get("pos", 0), primary.get("neg", 0)) >= 15
            and primary["auc"] is not None
            and primary["auc"] >= 0.65
            and primary.get("perm_p", 1.0) < 0.05
            and (primary["auc"] - d_auc) >= 0.05
        )
        # Sensitivity: keeping all 59 non-unknown 0103 labels strictly unchanged
        strict_perched_pres = [r for r in records if r["strict"] and r["posture_0103_preserved"] == "perched"]
        primary["sensitivity_preserve_0103_non_unknown"] = eval_subset(
            strict_perched_pres, lambda r: r["context"] == "owl_mobbing", "birdnet", permute=True
        )
        st.update(1, 1)

    with run.stage("secondary") as st:
        s1 = {
            "perch": eval_subset(strict_perched, lambda r: r["context"] == "owl_mobbing", "perch", permute=True),
            "crowgpt_b4": eval_subset(strict_perched, lambda r: r["context"] == "owl_mobbing", "crowgpt_b4", permute=True),
        }
        st.update(1, 3)

        hawk_strict_pf = [r for r in records if r["strict"] and r["context"] == "hawk_mobbing" and r["posture"] in ("perched", "flying")]
        hawk_nonstrict_pf = [r for r in records if r["context"] == "hawk_mobbing" and r["posture"] in ("perched", "flying")]
        s2 = {
            "strict_birdnet": eval_subset(hawk_strict_pf, lambda r: r["posture"] == "perched", "birdnet", permute=True),
            "strict_perch": eval_subset(hawk_strict_pf, lambda r: r["posture"] == "perched", "perch", permute=True),
            "nonstrict_birdnet": eval_subset(hawk_nonstrict_pf, lambda r: r["posture"] == "perched", "birdnet", permute=True),
            "nonstrict_perch": eval_subset(hawk_nonstrict_pf, lambda r: r["posture"] == "perched", "perch", permute=True),
        }
        st.update(2, 3)

        # S3: Pooled strict perched owl vs perched hawk: Archive (0116) + Video (0104)
        cs = exp104.ClipSet()
        vid_owl = cs.cap_per_channel(cs.cell("owl", "perched", strict=True))
        vid_hawk = cs.cap_per_channel(cs.cell("hawk", "perched", strict=True))
        dom_test = DomainResidualisedTest(C=0.05, n_perm=400)
        s3 = {}
        for rep_name in ("birdnet", "perch", "crowgpt_b4"):
            arc_sub = [r for r in strict_perched if r[rep_name] is not None]
            vid_vecs = {}
            for c in vid_owl + vid_hawk:
                vkey = f"v{c.key}"
                if sets.WindowTable.exists(vkey):
                    vt = sets.WindowTable(vkey)
                    vv = reps.window_mean(rep_name, vt, vt.pure())
                    if vv is not None:
                        vid_vecs[c.key] = vv
            vo = [c for c in vid_owl if c.key in vid_vecs]
            vh = [c for c in vid_hawk if c.key in vid_vecs]
            X_pool = np.vstack([
                *[r[rep_name] for r in arc_sub],
                *[vid_vecs[c.key] for c in vo + vh],
            ])
            y_pool = np.array([
                *[1 if r["context"] == "owl_mobbing" else 0 for r in arc_sub],
                *([1] * len(vo)),
                *([0] * len(vh)),
            ])
            g_pool = np.array([
                *[f"arc:{r['group']}" for r in arc_sub],
                *[f"vid:{c.channel}" for c in vo + vh],
            ])
            d_pool = np.array([0] * len(arc_sub) + [1] * (len(vo) + len(vh)))
            s3[rep_name] = dom_test.run(X_pool, y_pool, g_pool, d_pool)
        st.update(3, 3)

        p_family = {
            "S1_perch": s1["perch"].get("perm_p"),
            "S1_crowgpt_b4": s1["crowgpt_b4"].get("perm_p"),
            "S2_hawk_strict_birdnet": s2["strict_birdnet"].get("perm_p"),
            "S2_hawk_nonstrict_birdnet": s2["nonstrict_birdnet"].get("perm_p"),
            "S3_pooled_birdnet": s3["birdnet"].get("perm_p"),
            "S3_pooled_perch": s3["perch"].get("perm_p"),
        }
        holm_sec = holm_adjust(p_family)

    report = {
        "inventory": inventory,
        "PRIMARY_strict_archive_perched_owl_vs_hawk_birdnet": primary,
        "S1_strict_archive_perched_other_reps": s1,
        "S2_within_hawk_perched_vs_flying_archive": s2,
        "S3_pooled_archive_plus_video_strict_perched": s3,
        "secondary_holm_p": holm_sec,
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    run.note(
        f"Primary strict perched n={primary.get('pos')}/{primary.get('neg')} "
        f"AUC={primary.get('auc')} p={primary.get('perm_p')}; "
        f"Pooled S3 BirdNET n={s3['birdnet']['pos_owl']}/{s3['birdnet']['neg_hawk']} AUC={s3['birdnet']['auc']}"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
