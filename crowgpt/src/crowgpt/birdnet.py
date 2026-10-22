"""Talking to BirdNET from the GPU side, without letting it into this process.

Everything here writes audio to a temp directory, runs crowgpt.birdnet_worker as
a subprocess, and reads JSON back. That is slower than calling birdnetlib
directly and it is the point: birdnetlib in this process would silently cost the
GPU, and a subprocess cannot.

The cost is real and bounded — a few hundred milliseconds of interpreter and
model startup per call, so callers should batch, which is why every method here
takes a list rather than a clip.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[2]
SRC = HERE / "src"
DEFAULT_PYTHON = HERE / ".venv" / "bin" / "python"


class BirdNetError(RuntimeError):
    pass


class BirdNet:
    """A BirdNET that lives somewhere else."""

    def __init__(self, python=None, sample_rate=24000):
        self.python = Path(python) if python else DEFAULT_PYTHON
        self.sample_rate = sample_rate
        if not self.python.exists():
            raise BirdNetError(f"no interpreter at {self.python} — run `make -C crowgpt venv`")

    def _run(self, argv, timeout=3600):
        """One worker invocation. stdout is JSON; stderr is for humans."""
        completed = subprocess.run(
            [str(self.python), "-m", "crowgpt.birdnet_worker", *argv],
            cwd=str(HERE), env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin",
                                "HOME": str(Path.home())},
            capture_output=True, text=True, timeout=timeout,
        )
        if completed.returncode != 0:
            tail = "\n".join(completed.stderr.strip().splitlines()[-8:])
            raise BirdNetError(f"birdnet worker failed:\n{tail}")
        try:
            return json.loads(completed.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise BirdNetError(f"worker gave no JSON: {completed.stdout[-400:]}") from exc

    def _stage(self, clips, directory):
        """Numbered wavs, so results come back in the order they were sent."""
        import soundfile as sf

        kept = []
        for i, clip in enumerate(clips):
            clip = np.asarray(clip, dtype=np.float32)
            if clip.size == 0:
                continue
            sf.write(str(Path(directory) / f"{i:06d}.wav"), clip, self.sample_rate,
                     subtype="PCM_16")
            kept.append(i)
        return kept

    def confidence(self, clips):
        """Max corvid confidence per clip, None where the clip was empty."""
        out = [None] * len(clips)
        if not len(clips):
            return out, 0.25
        with tempfile.TemporaryDirectory() as directory:
            staged = self._stage(clips, directory)
            if not staged:
                return out, 0.25
            payload = self._run(["confidence", "--dir", directory])
        for row in payload["results"]:
            out[int(Path(row["file"]).stem)] = row["confidence"]
        return out, payload["crow_min"]

    def embed(self, clips):
        """BirdNET's 1024-d features, one row per clip that produced any."""
        return self.embed_indexed(clips)[0]

    def embed_indexed(self, clips):
        """Embeddings plus the input indices they belong to.

        BirdNET returns nothing for a clip it finds no segment in, so the output
        is shorter than the input and silently misaligned unless the caller is
        told which rows survived. Anything joining embeddings back to labels
        needs this rather than embed().
        """
        if not len(clips):
            return np.zeros((0, 1024)), []
        with tempfile.TemporaryDirectory() as directory:
            if not self._stage(clips, directory):
                return np.zeros((0, 1024)), []
            out_path = Path(directory) / "embeddings.npy"
            payload = self._run(["embed", "--dir", directory, "--out", str(out_path)])
            index = [int(Path(name).stem) for name in payload["files"]]
            return np.load(out_path), index

    def extract(self, out_dir, limit=None, workers=None):
        argv = ["extract", "--out", str(out_dir)]
        if limit:
            argv += ["--limit", str(limit)]
        if workers:
            argv += ["--workers", str(workers)]
        return self._run(argv, timeout=24 * 3600)


def assert_clean():
    """Refuse to proceed if birdnetlib has already been imported here.

    The mirror of the check in birdnet_worker. Between them the invariant is
    enforced from both sides rather than documented and hoped for.
    """
    if "birdnetlib" in sys.modules:
        raise BirdNetError(
            "birdnetlib is imported in this process, which is the GPU side. "
            "That is what makes torch unable to see the GPU — use crowgpt.birdnet "
            "to reach BirdNET in a subprocess instead. See crowgpt/gpu.py."
        )
