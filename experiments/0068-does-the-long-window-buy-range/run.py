"""0068: polish vs range — does the long window buy coverage of real crow space?

0067's contradiction: the gate says the 6 s window taught real structure, the
sitting says the ear prefers the 3 s twin. The hypothesis under test is that
pairwise preference structurally rewards the conservative arm — polish — while
the project's goal is range. Range is not dispersion (a model can spread into
non-crow noise); range is landing draws in the regions real crows occupy.

Per arm, draws equalised, embeddings BirdNET's via embed_indexed (embed()
silently drops rows, per 0040):

    dispersion      0065's mean pairwise cosine distance — variety, crow or not
    in_space        fraction of draws within the crow-space radius of some
                    real bout (precision — polish lives here)
    coverage        fraction of real test bouts with a draw within the radius
                    (recall — range lives here), bootstrap CI on the difference
    by source       real bouts join back to their corpus source, so any extra
                    reach is located: novel regions or more of the curated core

The crow-space radius is the p95 nearest-neighbour distance between real
halves split BY RECORDING — two bouts of one recording are near-twins and
would shrink the radius if they straddled the halves.
"""
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import torch

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.tokens import BoutStore

DATA_ROOT = Path(os.environ.get("DATA_DIR") or REPO / "data")
DATA = DATA_ROOT / "crowgpt"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
N_DRAWS = 300
N_REAL = 400
PER_RECORDING = 2
SEED = 0
BOOTSTRAPS = 2000
ARMS = {
    "model-longctx": (HERE / "results" / "model-longctx" / "model.pt", 460),
    "model-units": (HERE / "results" / "model-units" / "model.pt", 230),
}


def source_map():
    db = sqlite3.connect(DATA_ROOT / "corvid.db")
    rows = db.execute(
        "SELECT slug, species, source_ref, source FROM recordings "
        "WHERE source_ref IS NOT NULL")
    mapping, ambiguous = {}, set()
    for slug, species, ref, source in rows:
        slug = slug or (species or "").lower().strip().replace(" ", "-")
        key = (slug, str(ref))
        if key in mapping and mapping[key] != source:
            ambiguous.add(key)
        mapping[key] = source
    return mapping, ambiguous


def source_of(recording_id, mapping, ambiguous):
    rid = str(recording_id)
    key = (SPECIES, rid)
    if key not in mapping and "_" in rid:
        for part in rid.split("_"):
            if (SPECIES, part) in mapping:
                key = (SPECIES, part)
                break
    return None if key in ambiguous else mapping.get(key)


def unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def nn_dist(x, ref):
    return 1 - (unit(x) @ unit(ref).T).max(axis=1)


def dispersion(x, cap=200):
    x = unit(x[: cap])
    sim = x @ x.T
    mask = ~np.eye(len(x), dtype=bool)
    return float((1 - sim)[mask].mean())


def main():
    run = Run("0068 — POLISH VS RANGE",
              list(ARMS) + ["real", "embed", "measure"])
    results, audio, seeds_used = {}, {}, {}
    try:
        for arm, (ckpt, frames) in ARMS.items():
            with run.stage(arm) as stage:
                sampler = Sampler(ckpt, token_dir=None, decoder_state="finetuned")
                clips, seeds, seed = [], [], 0
                while len(clips) < N_DRAWS and seed < N_DRAWS * 6:
                    flat = sampler.tokens(SPECIES, seed=seed, max_frames=frames)
                    grid = sampler.codec.unflatten(flat)
                    wave = np.asarray(sampler.codec.decode(
                        torch.from_numpy(grid))[0], dtype=np.float32)
                    if wave.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
                        clips.append(normalise(wave))
                        seeds.append(seed)
                    seed += 1
                    stage.update(len(clips), N_DRAWS, extra=f"seed {seed}")
                audio[arm], seeds_used[arm] = clips, seeds
                run.note(f"{arm}: {len(clips)} draws from {seed} seeds, "
                         f"mean {np.mean([len(c) / SAMPLE_RATE for c in clips]):.2f}s")
                del sampler
                torch.cuda.empty_cache()

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts-6s")
            splits = store.split(seed=0)
            per_rec, clips, recs = defaultdict(int), [], []
            for i in splits["test"]:
                r = store.index[i]
                rid = r["recording_id"]
                if r["species"] != SPECIES or r["n_samples"] < SAMPLE_RATE \
                        or per_rec[rid] >= PER_RECORDING:
                    continue
                per_rec[rid] += 1
                clips.append(normalise(store.audio(r)))
                recs.append(str(rid))
                if len(clips) >= N_REAL:
                    break
            audio["real"], real_recs = clips, recs
            run.note(f"real-6s test: {len(clips)} bouts, "
                     f"{len(set(recs))} recordings")
            stage.update(1, 1)

        with run.stage("embed") as stage:
            from crowgpt.birdnet import BirdNet

            birdnet = BirdNet(sample_rate=SAMPLE_RATE)
            emb, kept, done = {}, {}, 0
            total = sum(len(v) for v in audio.values())
            for name, clips in audio.items():
                vectors, indices = birdnet.embed_indexed(clips)
                emb[name] = np.asarray(vectors)
                kept[name] = indices
                done += len(clips)
                stage.update(done, total, extra=f"{name}: {len(indices)} embedded")
            rng = np.random.default_rng(SEED)
            m = min(len(emb[a]) for a in ARMS)
            for a in ARMS:
                keep = rng.permutation(len(emb[a]))[: m]
                emb[a] = emb[a][keep]
                kept[a] = [kept[a][i] for i in keep]
            run.note(f"arms equalised at {m} draws each")

        with run.stage("measure") as stage:
            real = emb["real"]
            real_rec_kept = [real_recs[i] for i in kept["real"]]
            rng = np.random.default_rng(SEED)
            rec_ids = sorted(set(real_rec_kept))
            rng.shuffle(rec_ids)
            ref_recs = set(rec_ids[: len(rec_ids) // 2])
            ref_mask = np.array([r in ref_recs for r in real_rec_kept])
            ref, held = real[ref_mask], real[~ref_mask]
            radius = float(np.percentile(nn_dist(held, ref), 95))
            results["crow_space_radius_p95"] = round(radius, 4)
            results["real_n"] = len(real)
            results["coverage_ceiling_real_vs_real"] = round(
                float((nn_dist(ref, held) <= radius).mean()), 3)

            covered = {}
            for arm in ARMS:
                x = emb[arm]
                covered[arm] = nn_dist(real, x) <= radius
                results[arm] = {
                    "n": len(x),
                    "dispersion": round(dispersion(x), 4),
                    "in_space": round(float((nn_dist(x, real) <= radius).mean()), 3),
                    "coverage": round(float(covered[arm].mean()), 3),
                }
                run.note(f"{arm}: {results[arm]}")
            results["dispersion_real"] = round(dispersion(real), 4)

            a, b = covered["model-longctx"], covered["model-units"]
            results["coverage_exclusive"] = {
                "longctx_only": int((a & ~b).sum()), "twin_only": int((~a & b).sum()),
                "both": int((a & b).sum()), "neither": int((~a & ~b).sum()),
            }
            diffs = []
            for _ in range(BOOTSTRAPS):
                idx = rng.integers(0, len(real), len(real))
                diffs.append(float(a[idx].mean() - b[idx].mean()))
            lo, hi = np.percentile(diffs, [2.5, 97.5])
            results["coverage_diff_longctx_minus_twin"] = {
                "point": round(float(a.mean() - b.mean()), 3),
                "ci95": [round(float(lo), 3), round(float(hi), 3)],
            }

            try:
                mapping, ambiguous = source_map()
                by_source = defaultdict(list)
                for i, rid in enumerate(real_rec_kept):
                    src = source_of(rid, mapping, ambiguous)
                    if src:
                        by_source[src].append(i)
                results["coverage_by_source"] = {
                    src: {"n": len(idx),
                          "longctx": round(float(a[idx].mean()), 3),
                          "twin": round(float(b[idx].mean()), 3)}
                    for src, idx in sorted(by_source.items())
                    if len(idx) >= 20
                }
            except Exception as exc:
                run.note(f"source join skipped: {type(exc).__name__}: {exc}")
            stage.update(1, 1)

        np.savez_compressed(
            OUT / "embeddings.npz",
            real=emb["real"], real_recordings=np.array(real_rec_kept),
            **{f"{a}_emb": emb[a] for a in ARMS},
            **{f"{a}_seeds": np.array([seeds_used[a][i] for i in kept[a]])
               for a in ARMS})
        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
