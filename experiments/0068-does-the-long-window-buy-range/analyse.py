"""0068's resolution check: is the coverage tie real, or is the radius saturated?

The p95 crow-space radius (0.261) came out nearly equal to real's own mean
pairwise distance (0.263) — in 1024-d the nearest real neighbour is barely
closer than a random one, so p95 balls cover almost everything and coverage
has no room to differentiate (ceiling 0.954, both arms 0.94). Two harder
looks at the same embeddings:

    coverage curves   coverage at the p25/p50/p75/p95 radii, ceiling alongside —
                      if the arms tie at every radius the null is real
    paired distances  per real bout, nearest-longctx minus nearest-twin
                      distance — a paired test with n=298 of power where
                      thresholding threw resolution away
"""
import json
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

OUT = Path(__file__).resolve().parent
SEED = 0


def unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def nn_dist(x, ref):
    return 1 - (unit(x) @ unit(ref).T).max(axis=1)


def main():
    blob = np.load(OUT / "embeddings.npz", allow_pickle=False)
    real, recs = blob["real"], blob["real_recordings"]
    arms = {"model-longctx": blob["model-longctx_emb"],
            "model-units": blob["model-units_emb"]}

    rng = np.random.default_rng(SEED)
    rec_ids = sorted(set(recs.tolist()))
    rng.shuffle(rec_ids)
    ref_recs = set(rec_ids[: len(rec_ids) // 2])
    ref_mask = np.array([r in ref_recs for r in recs.tolist()])
    ref, held = real[ref_mask], real[~ref_mask]
    self_nn = nn_dist(held, ref)

    results = {"coverage_curve": {}}
    d = {a: nn_dist(real, x) for a, x in arms.items()}
    for pctl in (25, 50, 75, 95):
        radius = float(np.percentile(self_nn, pctl))
        results["coverage_curve"][f"p{pctl}"] = {
            "radius": round(radius, 4),
            "ceiling": round(float((nn_dist(ref, held) <= radius).mean()), 3),
            "longctx": round(float((d["model-longctx"] <= radius).mean()), 3),
            "twin": round(float((d["model-units"] <= radius).mean()), 3),
        }

    diff = d["model-longctx"] - d["model-units"]
    results["paired_nn_distance"] = {
        "n_real": len(diff),
        "mean_longctx": round(float(d["model-longctx"].mean()), 4),
        "mean_twin": round(float(d["model-units"].mean()), 4),
        "mean_diff_longctx_minus_twin": round(float(diff.mean()), 5),
        "longctx_closer_share": round(float((diff < 0).mean()), 3),
        "wilcoxon_p": round(float(wilcoxon(diff).pvalue), 5),
    }

    hardest = np.argsort(d["model-units"])[-15:]
    results["hardest_real_points"] = {
        "recordings": sorted(set(recs[hardest].tolist())),
        "mean_dist_longctx": round(float(d["model-longctx"][hardest].mean()), 4),
        "mean_dist_twin": round(float(d["model-units"][hardest].mean()), 4),
    }

    (OUT / "analysis.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
