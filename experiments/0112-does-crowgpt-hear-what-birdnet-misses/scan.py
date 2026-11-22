"""0112 step 1: one BirdNET pass per recording, every window's detections and embedding cached.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0112-does-crowgpt-hear-what-birdnet-misses/scan.py
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sets  # noqa: E402

sys.path.insert(0, str(sets.REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

_ANALYZER = None
_EXP102 = None


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _init_worker():
    global _ANALYZER, _EXP102
    from birdnetlib.analyzer import Analyzer

    sys.path.insert(0, str(sets.REPO / "pipelines" / "training"))
    _EXP102 = load_module("exp102_scan", sets.EXP102 / "run.py")
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()


def is_american_crow(common: str, scientific: str) -> bool:
    text = f"{common} {scientific}".lower()
    return "american crow" in text or "northwestern crow" in text or "corvus brachyrhynchos" in text


class WindowScanner:
    """One recording in, one npz of per-window detections and embeddings out."""

    def __init__(self, key: str, path: str):
        self.key, self.path = key, path

    def run(self) -> tuple[str, str | None]:
        from birdnetlib import Recording

        try:
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                recording = Recording(_ANALYZER, self.path, min_conf=0.05)
                recording.analyze()
                recording.extract_embeddings()
        except Exception as error:  # noqa: BLE001
            return self.key, str(error)[:200]
        scores = defaultdict(lambda: np.zeros(4, dtype=np.float32))
        for det in recording.detections or []:
            window = round(float(det["start_time"]), 2)
            common, scientific = det.get("common_name", ""), det.get("scientific_name", "")
            confidence = float(det["confidence"])
            row = scores[window]
            if _EXP102._is_corvid(common, scientific):
                row[0] = max(row[0], confidence)
            if is_american_crow(common, scientific):
                row[1] = max(row[1], confidence)
            else:
                row[3] = max(row[3], confidence)
            if _EXP102._is_raptor(common, scientific):
                row[2] = max(row[2], confidence)
        starts, rows, embeddings = [], [], []
        for segment in recording.embeddings or []:
            embedding = np.asarray(segment["embeddings"], dtype=np.float32)
            if not np.isfinite(embedding).all():
                continue
            start = round(float(segment["start_time"]), 2)
            starts.append(start)
            rows.append(scores.get(start, np.zeros(4, dtype=np.float32)))
            embeddings.append(embedding)
        if not starts:
            return self.key, "no windows"
        rows = np.array(rows)
        np.savez(sets.WINDOWS / f"{self.key}.npz", start=np.array(starts, dtype=np.float32),
                 corvid=rows[:, 0], american_crow=rows[:, 1], raptor=rows[:, 2], other=rows[:, 3],
                 embedding=np.array(embeddings, dtype=np.float32))
        return self.key, None


def _scan(task):
    return WindowScanner(*task).run()


def main():
    sets.WINDOWS.mkdir(parents=True, exist_ok=True)
    recordings = (sets.ArchiveSet().recordings + sets.OutsideSet().recordings + sets.ClipSet().recordings)
    seen, tasks = set(), []
    for r in recordings:
        if r.key not in seen and not sets.WindowTable.exists(r.key):
            seen.add(r.key)
            tasks.append((r.key, str(r.path)))
    run = Run("0112 BirdNET window scan", ["scan"])
    failures = {}
    with run.stage("scan") as stage, ProcessPoolExecutor(max_workers=12, initializer=_init_worker) as pool:
        futures = [pool.submit(_scan, t) for t in tasks]
        stage.update(0, len(tasks))
        for done, future in enumerate(as_completed(futures), 1):
            key, error = future.result()
            if error:
                failures[key] = error
            if done % 10 == 0 or done == len(tasks):
                stage.update(done, len(tasks), extra=f"{len(failures)} failed")
    run.note(f"{len(tasks) - len(failures)}/{len(tasks)} scanned")
    print(f"scanned {len(tasks) - len(failures)}/{len(tasks)}; failures: {failures}")


if __name__ == "__main__":
    main()
