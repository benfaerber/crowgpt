"""BirdNET work, in a process that must never import torch.

WHY THIS IS A SEPARATE PROCESS. Importing birdnetlib before torch leaves torch
permanently unable to see the GPU — is_available() False, device_count() 0, no
error. Initialising CUDA first survives in a small script and reproducibly does
not in a real one, so winning the race is not a fix. The only reliable answer is
that the two never share a process.

The rest of the repo has always worked this way: .venv-birdnet holds no torch,
and build_dataset.py hands off to gpu_mlp.py through .npz files. crowgpt was
given one venv holding both, to avoid exactly this seam, and that is what cost a
night of training at 1/240th speed. The seam was load-bearing.

The venv is still shared — the isolation is the process boundary, not a second
set of packages to keep in step. What makes it safe is the assertion at the top:
this refuses to run if torch is present, so the invariant is checked rather than
remembered.

Invoked as a subprocess by crowgpt.birdnet, speaking JSON on stdout:

    python -m crowgpt.birdnet_worker confidence --dir DIR
    python -m crowgpt.birdnet_worker embed --dir DIR --out FILE.npy
    python -m crowgpt.birdnet_worker extract --out DIR [--limit N] [--workers N]
"""

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

# The whole point, checked rather than assumed. If torch is already in this
# process then the caller has made the mistake this module exists to prevent,
# and the failure it causes is invisible later.
if "torch" in sys.modules:
    sys.exit(
        "crowgpt.birdnet_worker: torch is already imported in this process. "
        "This worker exists precisely so that never happens — see crowgpt/gpu.py."
    )

ANALYZER = None


def analyzer():
    global ANALYZER
    if ANALYZER is None:
        from birdnetlib.analyzer import Analyzer

        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            ANALYZER = Analyzer()
    return ANALYZER


def constants():
    from crowgpt.corpus import REPO

    # thresholds, not birdnet: no model load, so no muted stdout either.
    sys.path.insert(0, str(REPO))
    from analyzer import thresholds
    return (thresholds.CROW_TERMS, thresholds.CROW_MIN_CONF,
            thresholds.CANDIDATE_MIN_CONF)


def wavs_in(directory):
    """Sorted numerically, so the caller can match results to inputs by index."""
    return sorted(Path(directory).glob("*.wav"), key=lambda p: int(p.stem))


def cmd_confidence(args):
    from birdnetlib import Recording

    terms, crow_min, candidate_min = constants()
    out = []
    for path in wavs_in(args.dir):
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            recording = Recording(analyzer(), str(path), min_conf=candidate_min)
            recording.analyze()
        best, species = 0.0, None
        for detection in recording.detections:
            name = f"{detection.get('common_name','')} {detection.get('scientific_name','')}".lower()
            if any(term in name for term in terms) and float(detection["confidence"]) > best:
                best, species = float(detection["confidence"]), detection.get("common_name")
        out.append({"file": path.name, "confidence": best, "species": species})
    return {"crow_min": crow_min, "results": out}


def _embed_one(path):
    """One clip -> one 1024-d vector, or None if BirdNET found no segment."""
    import numpy as np
    from birdnetlib import Recording

    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        recording = Recording(analyzer(), str(path), min_conf=0.1)
        recording.extract_embeddings()
    segments = recording.embeddings
    if not segments:
        return None
    # Mean over the 3-second segments, as pipelines/representation does, so one
    # clip is one vector whatever its length.
    return np.mean([s["embeddings"] for s in segments], axis=0)


def cmd_embed(args):
    """Embed a directory of clips, in parallel when there are many.

    Serially this runs at a few hundred clips a minute, so labelling a
    57,000-bout corpus would take hours. One analyzer per worker, the same shape
    extract uses.
    """
    import numpy as np

    paths = wavs_in(args.dir)
    workers = args.workers or max(1, min(24, (os.cpu_count() or 8) - 4))
    if len(paths) < 64 or workers == 1:
        results = [(p, _embed_one(p)) for p in paths]
    else:
        from concurrent.futures import ProcessPoolExecutor
        from multiprocessing import get_context

        with ProcessPoolExecutor(workers, mp_context=get_context("spawn")) as pool:
            results = list(zip(paths, pool.map(_embed_one, paths, chunksize=16)))

    vectors = [(p.name, v) for p, v in results if v is not None]
    array = (np.array([v for _, v in vectors], dtype=np.float64)
             if vectors else np.zeros((0, 1024)))
    np.save(args.out, array)
    return {"embedded": len(vectors), "files": [n for n, _ in vectors],
            "shape": list(array.shape)}


def cmd_extract(args):
    from crowgpt.extract import Extractor

    return Extractor(args.out, limit_per_species=args.limit, workers=args.workers).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("confidence")
    p.add_argument("--dir", required=True)
    p.set_defaults(func=cmd_confidence)

    p = sub.add_parser("embed")
    p.add_argument("--dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=None)
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("extract")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=None)
    p.set_defaults(func=cmd_extract)

    args = parser.parse_args(argv)
    result = args.func(args)
    if "torch" in sys.modules:
        sys.exit("crowgpt.birdnet_worker: something imported torch during the run.")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
