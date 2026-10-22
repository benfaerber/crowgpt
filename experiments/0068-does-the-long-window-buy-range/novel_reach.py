"""0068's missing cell: does either arm reach the NOVEL regions better?

The main run's real reference came from bouts-6s' test split, which is 88%
macaulay — 0065's novel-source regions (archive #3 93% novel, the soundscape
archive 42%, the community archive 12%) were barely in it, so "coverage of real crow space" mostly
meant the curated core, and the range prediction's home cell went unmeasured.

This embeds novel-source American Crow bouts from the whole store (any
split — both arms trained on these sources, so training exposure is equal
footing, and the question is reach, not generalisation) and measures each
arm's nearest-draw distance to them, per source. Draw embeddings come from
the main run's embeddings.npz — nothing is resampled.
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
from scipy.stats import wilcoxon

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA_ROOT = Path(os.environ.get("DATA_DIR") or REPO / "data")
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
#: The store's source slugs, named in the environment so the tree stays
#: source-agnostic: NOVEL_SOURCES="archive-3-slug,soundscape-slug,community-slug".
NOVEL = tuple((os.environ.get("NOVEL_SOURCES") or "archive_3,soundscape_archive,community_archive").split(","))
PER_SOURCE = 150
#: Only where a source has bouts to spare — archive #3 holds 47 bouts total
#: in bouts-6s and a 2-per-recording cap left it under the 20-bout bar, so the
#: two small sources go uncapped (sibling bouts of one recording are near-twins;
#: the per-source cells say so in n, and the paired test is per-bout regardless).
PER_RECORDING = {NOVEL[2]: 2}
SEED = 0


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


def main():
    run = Run("0068 — NOVEL REACH", ["gather", "embed", "measure"])
    results = {}
    try:
        blob = np.load(OUT / "embeddings.npz", allow_pickle=False)
        arms = {"model-longctx": blob["model-longctx_emb"],
                "model-units": blob["model-units_emb"]}

        with run.stage("gather") as stage:
            store = BoutStore(DATA_ROOT / "crowgpt" / "bouts-6s")
            mapping, ambiguous = source_map()
            rng = np.random.default_rng(SEED)
            by_source, per_rec = defaultdict(list), defaultdict(int)
            for i, row in enumerate(store.index):
                if row["species"] != SPECIES or row["n_samples"] < SAMPLE_RATE:
                    continue
                src = source_of(row["recording_id"], mapping, ambiguous)
                cap = PER_RECORDING.get(src, float("inf"))
                if src in NOVEL and per_rec[(src, row["recording_id"])] < cap:
                    per_rec[(src, row["recording_id"])] += 1
                    by_source[src].append(i)
            chosen = {
                s: list(rng.choice(idx, size=min(PER_SOURCE, len(idx)),
                                   replace=False))
                for s, idx in by_source.items() if len(idx) >= 20
            }
            stage.say(" · ".join(f"{s}:{len(v)}" for s, v in chosen.items()))

        with run.stage("embed") as stage:
            from crowgpt.birdnet import BirdNet

            birdnet = BirdNet(sample_rate=SAMPLE_RATE)
            emb, recs, done = {}, {}, 0
            total = sum(len(v) for v in chosen.values())
            for src, indices in chosen.items():
                clips = [normalise(store.audio(store.index[i])) for i in indices]
                vectors, kept = birdnet.embed_indexed(clips)
                emb[src] = np.asarray(vectors)
                recs[src] = [str(store.index[indices[k]]["recording_id"])
                             for k in kept]
                done += len(indices)
                stage.update(done, total, extra=f"{src}: {len(kept)} embedded")

        with run.stage("measure") as stage:
            all_diffs, rec_means = [], []
            for src, x in emb.items():
                d = {a: nn_dist(x, draws) for a, draws in arms.items()}
                diff = d["model-longctx"] - d["model-units"]
                all_diffs.append(diff)
                by_rec = defaultdict(list)
                for r, value in zip(recs[src], diff):
                    by_rec[r].append(value)
                means = [float(np.mean(v)) for v in by_rec.values()]
                rec_means.extend(means)
                results[src] = {
                    "n": len(x),
                    "n_recordings": len(by_rec),
                    "mean_dist_longctx": round(float(d["model-longctx"].mean()), 4),
                    "mean_dist_twin": round(float(d["model-units"].mean()), 4),
                    "longctx_closer_share": round(float((diff < 0).mean()), 3),
                    "wilcoxon_p": round(float(wilcoxon(diff).pvalue), 5),
                }
                run.note(f"{src}: {results[src]}")
            pooled = np.concatenate(all_diffs)
            # Sibling bouts of one recording are not independent draws from the
            # region — the recording-level test is the one the uncapped sources
            # have to pass for the pooled p to mean anything.
            results["pooled"] = {
                "n": len(pooled),
                "mean_diff_longctx_minus_twin": round(float(pooled.mean()), 5),
                "longctx_closer_share": round(float((pooled < 0).mean()), 3),
                "wilcoxon_p": round(float(wilcoxon(pooled).pvalue), 5),
                "n_recordings": len(rec_means),
                "recording_level_closer_share": round(
                    float(np.mean(np.array(rec_means) < 0)), 3),
                "recording_level_wilcoxon_p": round(
                    float(wilcoxon(rec_means).pvalue), 5),
            }
            stage.update(1, 1)

        (OUT / "novel_reach.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
