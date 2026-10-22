"""Did the scrape's diversity actually arrive in the bout store?

0064's split verdict needs this half: v3 sounded identical to v2, but that is
two hypotheses wearing one null — either the new sources' promised diversity
never survived the corvid gate into the corpus, or it arrived and the model
cannot use it. Different follow-ups: the first says the drive-by-clip theory
was wrong, the second points at conditioning and context.

Measured per source, American Crow bouts only (the species anyone judges):

    dispersion   mean pairwise cosine distance among a source's own bouts —
                 how varied is what it contributed
    novelty      fraction of a source's bouts whose nearest curated-corpus
                 neighbour is farther than the curated corpus's own held-out
                 95th-percentile self-distance — bouts occupying regions the
                 old corpus does not

"Curated" = the two big archive sources the pre-scrape corpus was built
from; "new" = everything the 2026-08 scrape added. Embeddings are BirdNET's,
through embed_indexed — the wrapper that keeps row indices, per 0040's
warning, because BirdNET silently returns nothing for clips it finds no
segment in and positional joins have already drifted once.

Sources are recovered by joining recording_id back to the crawl database on
(species, source_ref); the handful of ambiguous numeric ids that collide
across sources are dropped rather than guessed.
"""
import json
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

from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data")
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
PER_SOURCE = 400          # bouts sampled per source, seed-fixed
CURATED = {"xeno_canto", "macaulay"}
SEED = 0
SR = 24000


def source_map():
    db = sqlite3.connect(DATA / "corvid.db")
    rows = db.execute(
        "SELECT slug, species, source_ref, source FROM recordings "
        "WHERE source_ref IS NOT NULL")
    mapping, ambiguous = {}, set()
    for slug, species, ref, source in rows:
        # The newest sources' rows carry no slug — it arrived with the corpus
        # unify and the crawler doesn't write it — so fall back to slugifying
        # the species name, which is exactly what extraction stores.
        slug = slug or (species or "").lower().strip().replace(" ", "-")
        key = (slug, str(ref))
        if key in mapping and mapping[key] != source:
            ambiguous.add(key)
        mapping[key] = source
    return mapping, ambiguous


def main():
    run = Run("0065 — DID THE DIVERSITY ARRIVE", ["group", "embed", "measure"])
    results = {}
    try:
        store = BoutStore(DATA / "crowgpt" / "bouts")
        mapping, ambiguous = source_map()

        with run.stage("group") as stage:
            rng = np.random.default_rng(SEED)
            by_source = defaultdict(list)
            dropped = 0
            for i, row in enumerate(store.index):
                if row["species"] != SPECIES or row["n_samples"] < SR:
                    continue
                rid = str(row["recording_id"])
                key = (SPECIES, rid)
                if key not in mapping and "_" in rid:
                    # File-stem ids (`inat_<ref>_<x>`, `<src>_<ref>` shapes)
                    # carry the bare ref in a segment — the miss that silently
                    # excluded the two biggest pools on the first run.
                    for part in rid.split("_"):
                        if (SPECIES, part) in mapping:
                            key = (SPECIES, part)
                            break
                if key in ambiguous:
                    dropped += 1
                    continue
                source = mapping.get(key)
                if source:
                    by_source[source].append(i)
            chosen = {
                s: list(rng.choice(idx, size=min(PER_SOURCE, len(idx)),
                                   replace=False))
                for s, idx in by_source.items() if len(idx) >= 40
            }
            stage.say(" · ".join(f"{s}:{len(v)}" for s, v in chosen.items()))
            run.note(f"{dropped} bouts dropped as source-ambiguous")

        with run.stage("embed") as stage:
            from crowgpt.birdnet import BirdNet

            birdnet = BirdNet(sample_rate=SR)
            emb, done, total = {}, 0, sum(len(v) for v in chosen.values())
            for source, indices in chosen.items():
                clips = [store.audio(store.index[i]) for i in indices]
                vectors, kept = birdnet.embed_indexed(clips)
                emb[source] = np.asarray(vectors)
                done += len(indices)
                stage.update(done, total, extra=f"{source}: {len(kept)} embedded")

        with run.stage("measure") as stage:
            def dispersion(x, cap=200):
                x = x[: cap] / np.linalg.norm(x[: cap], axis=1, keepdims=True)
                sim = x @ x.T
                mask = ~np.eye(len(x), dtype=bool)
                return float((1 - sim)[mask].mean())

            curated = np.concatenate([emb[s] for s in CURATED if s in emb])
            rng = np.random.default_rng(SEED)
            rng.shuffle(curated)
            half = len(curated) // 2
            ref, held = curated[:half], curated[half:]
            refn = ref / np.linalg.norm(ref, axis=1, keepdims=True)

            def nn_dist(x):
                xn = x / np.linalg.norm(x, axis=1, keepdims=True)
                return 1 - (xn @ refn.T).max(axis=1)

            threshold = float(np.percentile(nn_dist(held), 95))
            results["novelty_threshold_p95_curated_self"] = round(threshold, 4)
            for source, x in emb.items():
                results[source] = {
                    "n": len(x),
                    "dispersion": round(dispersion(x), 4),
                    "novelty": round(float((nn_dist(x) > threshold).mean()), 3),
                }
                run.note(f"{source}: dispersion {results[source]['dispersion']} "
                         f"· novelty {results[source]['novelty']}")
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
