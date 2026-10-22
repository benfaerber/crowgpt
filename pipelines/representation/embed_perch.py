"""Perch 2.0 embeddings of the label corpus, at a chosen amount of context.

Perch 2.0 (Google DeepMind, arXiv 2508.04665) is the current state of the art on
BirdSet and on BEANS linear probing, and — the reason it is here rather than
BirdAVES — its own paper validates on the Weldy **call-type** dataset. Call-type
recognition is one of the things it was selected to do, not a hoped-for side
effect of species training.

    .venv/bin/python ../embed_perch.py --check
    .venv/bin/python ../embed_perch.py --seconds 5
    .venv/bin/python ../embed_perch.py --seconds 3 --pad noise

`--seconds` is the context ladder and it is the point. Perch's native window is
5 s against BirdNET's 3 s, so a bare comparison hands it two extra seconds of
audio and then reports the difference as a fact about the model. Running it at
1, 3 and 5 s turns that into a measurement: if Perch at 1 s already beats
BirdNET at 3 s, the objection is dead — it had a third of the audio.

Two honest limits of this arm, both worth reading before the numbers:

  * **The model pads, and we cannot mask it.** perch-hoplite's `embed()` returns
    one 1536-d vector per 5 s window, already pooled — the 5x3x1536 spatial grid
    the paper describes is not exposed. So a 3 s arm is 3 s of audio and 2 s of
    padding averaged together, and `--pad noise` is how we find out what that
    costs rather than assuming it costs nothing.
  * **Perch peak-normalises internally** (zoo_interface.py divides each frame by
    its peak). Every other arm here is fed unnormalised audio because the
    deployed path does none and experiment 0022 showed level moves BirdNET's
    numbers. This one arm normalises because the model insists, and that is a
    difference between arms rather than a choice.

TensorFlow, so it runs in perch/.venv and never in the same process as
birdnetlib — which sets CUDA_VISIBLE_DEVICES="" at import and would silently
strand this model on the CPU forever.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Before TensorFlow is imported, not after. TF reserves all *free* VRAM at
# session start, and this box may be running a torch job on the same card.
os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments" / "lib"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from corpus import LabelCorpus  # noqa: E402
from excerpts import DATA, ExcerptCache, real_fraction, segment_keys  # noqa: E402
from features import Features  # noqa: E402
from crowgpt.progress import Run  # noqa: E402

EXPERIMENT = REPO / "experiments" / "0025-is-birdnet-the-bottleneck"
CACHE_DIR = DATA / "experiments" / "0025"
ARMS = EXPERIMENT / "arms"

#: Keep the 400 MB of weights in the gitignored corpus directory so they
#: survive a venv rebuild.
os.environ.setdefault("KAGGLEHUB_CACHE", str(DATA / "models"))

MODEL_NAME = "perch_v2"


class Perch:
    """Perch 2.0, embedding one padded window at a time."""

    def __init__(self, name=MODEL_NAME):
        try:
            from perch_hoplite.zoo import model_configs
        except ImportError:
            raise SystemExit(
                "perch_hoplite is not importable. This script runs in its own "
                "interpreter:\n  pipelines/representation/perch/.venv/bin/python "
                "pipelines/representation/embed_perch.py\nCreate it with "
                "`cd pipelines/representation/perch && uv sync`."
            )
        self.model = model_configs.load_model_by_name(name)
        self.name = name

    @property
    def sample_rate(self):
        return int(self.model.sample_rate)

    @property
    def window_sec(self):
        return float(self.model.window_size_s)

    def embed(self, samples):
        """One 1536-d vector for a buffer of exactly one window.

        Perch pads a short buffer up to its window internally and returns one
        frame; anything longer returns several. This arm always feeds exactly
        one window, so more than one frame means the caller got the arithmetic
        wrong and averaging them would hide it.
        """
        out = self.model.embed(np.asarray(samples, dtype=np.float32))
        emb = np.asarray(out.embeddings, dtype=np.float64)
        if emb.shape[0] != 1:
            raise SystemExit(
                f"Perch returned {emb.shape[0]} frames for one window "
                f"({emb.shape}); the input length is wrong."
            )
        return emb.reshape(-1)


def build(seconds, pad, limit=None):
    corpus = LabelCorpus(dataset="all-public")
    segments = {s.key: s for s in corpus.labeled_segments(require_audio=True)}
    cache = ExcerptCache(CACHE_DIR)
    data, cached_keys = cache.load()
    index = {k: i for i, k in enumerate(cached_keys)}

    keys = [k for k in segment_keys(corpus) if k in index]
    if limit:
        keys = keys[:limit]

    arm = f"c-perch-{seconds:g}s" + ("-noisepad" if pad == "noise" else "")
    run = Run(f"0025 ARM {arm.upper()}",
              ["load Perch 2.0", f"embed {len(keys)} segments", "write npz"])
    with run.stage("load Perch 2.0"):
        perch = Perch()
    print(f"{arm}: embedding {len(keys)} segments — {seconds:g} s of audio in a "
          f"{perch.window_sec:g} s window at {perch.sample_rate} Hz, {pad} pad")

    rng = np.random.default_rng(0)
    X, Y, groups, kept = [], [], [], []
    real = None
    with run.stage(f"embed {len(keys)} segments") as stage:
        stage.say(f"{seconds:g}s of audio in a {perch.window_sec:g}s window, "
                  f"{pad} pad")
        for n, key in enumerate(keys, 1):
            seg = segments[key]
            samples, mask = cache.padded(data[index[key]], seconds,
                                         perch.window_sec, perch.sample_rate,
                                         pad=pad, rng=rng)
            real = real_fraction(mask)
            vec = perch.embed(samples)
            if not np.isfinite(vec).all():
                continue
            X.append(vec)
            Y.append(sorted(seg.labels))
            groups.append(seg.file_id)
            kept.append(key)
            if n % 100 == 0:
                stage.update(n, len(keys))

    with run.stage("write npz"):
        feats = Features(np.array(X), Y, np.array(groups), kept,
                         f"perch_v2_{seconds:g}s" + (f"_{pad}pad" if pad != "zero" else ""),
                         {"backbone": "perch_v2", "seconds": seconds,
                          "window_sec": perch.window_sec, "pad": pad,
                          "real_fraction": real, "sr": perch.sample_rate,
                          "peak_normalised_by_model": True})
        out = feats.write(ARMS / f"{arm}.npz")
    run.note(f"wrote {len(feats)} rows x {feats.dim}-d, "
             f"{real:.0%} real audio per window")
    print(f"wrote {len(feats)} rows x {feats.dim}-d -> {out}")
    print(f"  {real:.0%} of each {perch.window_sec:g} s window was real audio")
    return feats


def check():
    """Load the model, embed one excerpt each way, print the shapes. 20 seconds.

    Catches a missing venv, absent Kaggle weights and a wrong window length
    before the caller spends an hour finding out.
    """
    perch = Perch()
    print(f"model {perch.name}: window {perch.window_sec:g} s @ "
          f"{perch.sample_rate} Hz")
    corpus = LabelCorpus(dataset="all-public")
    cache = ExcerptCache(CACHE_DIR)
    data, keys = cache.load()
    row = data[0]
    print(f"\n{'seconds':>8}{'real':>7}{'shape':>12}{'norm':>9}")
    for secs in (1.0, 3.0, 5.0):
        samples, mask = cache.padded(row, secs, perch.window_sec,
                                     perch.sample_rate)
        vec = perch.embed(samples)
        print(f"{secs:>8.0f}{real_fraction(mask):>7.0%}{str(vec.shape):>12}"
              f"{np.linalg.norm(vec):>9.2f}")
    print(f"\ncache row 0 = {keys[0]}; {len(keys)} rows available")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=5.0,
                        help="how much real audio to give it (the ladder)")
    parser.add_argument("--pad", choices=["zero", "noise"], default="zero")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        build(args.seconds, args.pad, args.limit)


if __name__ == "__main__":
    main()
