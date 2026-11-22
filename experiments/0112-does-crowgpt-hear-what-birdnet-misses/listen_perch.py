"""0112 step 3: Perch 2.0 embeddings, one 5 s window centred on each span.

    pipelines/representation/perch/.venv/bin/python \
        experiments/0112-does-crowgpt-hear-what-birdnet-misses/listen_perch.py
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import librosa  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sets  # noqa: E402

os.environ.setdefault("KAGGLEHUB_CACHE", str(sets.DATA_DIR / "models"))
sys.path.insert(0, str(sets.REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

OUT = sets.CACHE / "perch.npz"
SR = 32000
WINDOW = 5 * SR
FADE = int(0.010 * SR)
BATCH = 32


class PerchSpanAudio:
    """One file at 32 kHz; spans become 5 s windows centred on them, zero-padded past the file."""

    def __init__(self, path: str):
        self.samples, _ = librosa.load(path, sr=SR, mono=True)

    def window(self, start: float, end: float) -> np.ndarray:
        centre = int((start + end) / 2 * SR)
        lo = centre - WINDOW // 2
        out = np.zeros(WINDOW, dtype=np.float32)
        src_lo, src_hi = max(0, lo), min(len(self.samples), lo + WINDOW)
        if src_hi > src_lo:
            out[src_lo - lo:src_hi - lo] = self.samples[src_lo:src_hi]
        return out

    def isolated(self, onset: float, offset: float) -> np.ndarray:
        body = self.samples[int(onset * SR):int(offset * SR)].astype(np.float32).copy()[:WINDOW]
        fade = min(FADE, len(body) // 2)
        if fade:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            body[:fade] *= ramp
            body[-fade:] *= ramp[::-1]
        out = np.zeros(WINDOW, dtype=np.float32)
        lo = (WINDOW - len(body)) // 2
        out[lo:lo + len(body)] = body
        return out


def main():
    from perch_hoplite.zoo import model_configs

    spans = sets.SpanCatalogue().all()
    done = {}
    if OUT.exists():
        saved = np.load(OUT)
        done = dict(zip(saved["ids"].tolist(), saved["embeddings"]))
    todo = [s for s in spans if s.span_id not in done]
    by_file = defaultdict(list)
    for s in todo:
        by_file[s.path].append(s)
    run = Run("0112 Perch embeddings", ["embed"])
    model = model_configs.load_model_by_name("perch_v2")
    finished = 0
    with run.stage("embed") as stage:
        stage.update(0, len(todo))
        for path, group in by_file.items():
            try:
                audio = PerchSpanAudio(path)
            except Exception as error:  # noqa: BLE001
                print(f"skip {path}: {error}")
                finished += len(group)
                continue
            for i in range(0, len(group), BATCH):
                chunk = group[i:i + BATCH]
                batch = np.zeros((BATCH, WINDOW), dtype=np.float32)
                for j, s in enumerate(chunk):
                    batch[j] = audio.isolated(s.start, s.end) if s.isolated else audio.window(s.start, s.end)
                embeddings = np.asarray(model.batch_embed(batch).embeddings, dtype=np.float32).reshape(BATCH, -1)
                for s, embedding in zip(chunk, embeddings):
                    if np.isfinite(embedding).all():
                        done[s.span_id] = embedding.astype(np.float16)
                finished += len(chunk)
            stage.update(finished, len(todo), extra=f"{len(done)} spans")
            if len(done) % 2000 < len(group):
                np.savez(OUT, ids=np.array(list(done)), embeddings=np.stack(list(done.values())))
    np.savez(OUT, ids=np.array(list(done)), embeddings=np.stack(list(done.values())))
    run.note(f"{len(done)} spans embedded")


if __name__ == "__main__":
    main()
