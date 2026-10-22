"""Is the embedding space mostly the microphone?

Ben, 2026-08-03, on Phase 3's "call types do not form natural clusters":

    "I still think there is natural sound patterns. It's just the fact that
     maybe the audio is poor quality and maybe not properly normalized."

WHY THAT IS NOT JUST A HUNCH. Phase 3 measured silhouette against CALL-TYPE
labels and got ~0 in every feature space it tried, and concluded "clusters
absent". But a silhouette of zero against call type does not mean there is no
cluster structure — it means **there is none that lines up with call type.** A
space can be violently clustered by something else and score exactly the same.

The obvious something else is the recording. Every archive clip carries one
microphone, one distance, one gain, one background and one MP3 encoder, and all
of those are constant within a recording and different between recordings. That
is a textbook channel confound, and Phase 3 could not have detected it: its
cached features carry only X and y — no recording id — and there are 117 rows in
total across four feature spaces.

So this asks the question Phase 3 did not:

    1. How much of the embedding space IS recording identity? Silhouette by
       recording, on bouts drawn several-per-recording so the question is
       answerable at all.
    2. Does removing it reveal anything? Per-recording mean subtraction is the
       standard channel fix (CMVN). If call-type or species structure appears
       only after it, Ben is right and the normalisation was the problem.
    3. Is there ANY structure, labelled or not? k-means at several k with the
       silhouette of the clustering itself, which needs no labels and is the
       actual "do the sounds clump" question.

SPECIES IS THE POSITIVE CONTROL. Six species that a listener separates easily
must separate here too. If they do not, the embedder is not carrying what the
question needs and nothing else in the run means anything.

THE CORPUS TRAP THIS AVOIDS. Counting over all bouts would mostly measure
the archive corpus — different continents, different recordists, different decades. That
is why the species arm is deliberately small and balanced, and why the
call-type-shaped question is asked inside ONE species.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np

from crowgpt.codec import normalise
from crowgpt.embed import AstEmbedder
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SR = 24000
FOCUS = "american-crow"
PER_RECORDING = 5      # several per recording, or "silhouette by recording" is undefined
N_RECORDINGS = 60
MIN_SECONDS = 1.0


def silhouette(X, labels):
    """Mean silhouette, on cosine distance. Groups of one are skipped.

    Written out rather than imported so the distance is explicit: these are
    embedding vectors whose magnitude carries loudness, and loudness is one of
    the channel effects under test. Cosine drops it; euclidean would let level
    alone create the clusters this is looking for.
    """
    labels = np.asarray(labels)
    unit = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
    distance = 1.0 - unit @ unit.T
    np.fill_diagonal(distance, 0.0)
    scores = []
    for i in range(len(X)):
        same = labels == labels[i]
        same[i] = False
        if not same.any():
            continue
        a = distance[i, same].mean()
        b = min(distance[i, labels == other].mean()
                for other in set(labels) - {labels[i]})
        scores.append((b - a) / max(a, b))
    return float(np.mean(scores)) if scores else float("nan")


def kmeans(X, k, seed=0, iters=60):
    rng = np.random.default_rng(seed)
    unit = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
    centres = unit[rng.choice(len(unit), size=k, replace=False)]
    assign = np.zeros(len(unit), dtype=int)
    for _ in range(iters):
        new = np.argmax(unit @ centres.T, axis=1)
        if (new == assign).all():
            break
        assign = new
        for c in range(k):
            members = unit[assign == c]
            if len(members):
                centres[c] = members.mean(axis=0)
                centres[c] /= np.linalg.norm(centres[c]) + 1e-12
    return assign


def per_group_centre(X, groups):
    """CMVN: subtract each recording's own mean. The standard channel fix."""
    out = X.copy()
    for g in set(groups):
        mask = np.asarray(groups) == g
        out[mask] -= out[mask].mean(axis=0)
    return out


def main():
    run = Run("0040 — IS THE SPACE MOSTLY THE MICROPHONE",
              ["choose", "embed", "measure"])
    results = {}
    try:
        store = BoutStore(DATA / "bouts")
        with run.stage("choose") as stage:
            splits = store.split(seed=0)
            by_recording = defaultdict(list)
            for i in splits["test"] + splits["val"]:
                row = store.index[i]
                if row["n_samples"] / SR < MIN_SECONDS:
                    continue
                by_recording[(row["species"], row["recording_id"])].append(i)

            crow = {k: v for k, v in by_recording.items()
                    if k[0] == FOCUS and len(v) >= PER_RECORDING}
            chosen = sorted(crow)[:N_RECORDINGS]
            picks, recordings = [], []
            for key in chosen:
                for i in crow[key][:PER_RECORDING]:
                    picks.append(i)
                    recordings.append(key[1])

            # Species arm: the positive control, balanced so corpus mix cannot
            # manufacture the separation.
            species_picks, species_labels = [], []
            for slug in sorted({k[0] for k in by_recording}):
                pool = [k for k in by_recording if k[0] == slug and len(by_recording[k]) >= 2]
                for key in sorted(pool)[:12]:
                    for i in by_recording[key][:2]:
                        species_picks.append(i)
                        species_labels.append(slug)
            stage.say(f"{len(picks)} crow bouts over {len(chosen)} recordings · "
                      f"{len(species_picks)} bouts over {len(set(species_labels))} species")

        crow_audio = [normalise(store.audio(store.index[i])) for i in picks]
        species_audio = [normalise(store.audio(store.index[i])) for i in species_picks]
        spaces = {}
        with run.stage("embed") as stage:
            # BOTH, because Phase 3 found they disagree and only one of them
            # carried anything: BirdNET took flight call to 0.89 AUC where AST
            # sat at 0.74. A channel result measured only in the space that
            # never separated anything would say nothing about the other.
            #
            # BIRDNET GOES THROUGH embed_indexed, NOT embed. It returns nothing
            # for a clip it finds no segment in — 262 rows for 300 clips on the
            # first attempt here — and `BirdNetEmbedder.embed` discards the
            # surviving indices, so labels would silently attach to the wrong
            # rows. birdnet.py's own docstring says so; the wrapper ignores it.
            ast = AstEmbedder()
            spaces["ast"] = (ast.embed(crow_audio, SR), np.arange(len(crow_audio)),
                             ast.embed(species_audio, SR), np.arange(len(species_audio)))
            stage.update(1, 2, extra="ast")
            try:
                from crowgpt.birdnet import BirdNet

                net = BirdNet(sample_rate=SR)
                Xb, xi = net.embed_indexed(crow_audio)
                Sb, si = net.embed_indexed(species_audio)
                if len(Xb) != len(xi) or len(Sb) != len(si):
                    raise RuntimeError("birdnet returned rows and indices of different length")
                spaces["birdnet"] = (Xb, np.asarray(xi), Sb, np.asarray(si))
                run.note(f"birdnet kept {len(xi)}/{len(crow_audio)} crow and "
                         f"{len(si)}/{len(species_audio)} species clips")
            except Exception as exc:  # noqa: BLE001 - one space failing is a result
                run.note(f"birdnet unavailable: {type(exc).__name__}: {exc}")
            stage.update(2, 2, extra="birdnet")
            if not spaces:
                raise SystemExit("no embedder produced features")

        with run.stage("measure") as stage:
            results["n"] = {"crow_bouts": len(picks), "recordings": len(chosen),
                            "species_bouts": len(species_picks)}
            for name, (X, xi, S, si) in spaces.items():
                # Subset the labels to the rows that survived, never the reverse.
                recs = np.asarray(recordings)[xi]
                sp = np.asarray(species_labels)[si]
                centred = per_group_centre(X, recs)
                block = {
                    "n_rows": int(len(X)),
                    "species_control_silhouette": round(silhouette(S, sp), 4),
                    "recording_silhouette": round(silhouette(X, recs), 4),
                    "recording_silhouette_after_cmvn": round(silhouette(centred, recs), 4),
                    "kmeans": {},
                }
                for k in (2, 3, 4, 6, 8):
                    block["kmeans"][str(k)] = {
                        "silhouette_raw": round(silhouette(X, kmeans(X, k)), 4),
                        "silhouette_cmvn": round(silhouette(centred, kmeans(centred, k)), 4),
                    }
                results[name] = block
                ratio = block["recording_silhouette"] / max(1e-9, abs(block["species_control_silhouette"]))
                run.note(f"{name}: species control {block['species_control_silhouette']:+.3f} · "
                         f"recording {block['recording_silhouette']:+.3f} (ratio {ratio:.1f}x)")
            (OUT / "results.json").write_text(json.dumps(results, indent=2))
            stage.say("wrote results.json")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
