"""0095: is the judge reading something trivial? Scores three one-number
judges on every completed pool: which clip is longer, which is louder, and
which is more periodic. None is fitted, so every pool is a test."""
import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from judging import POOLS_DIR, TRAIN_POOLS, Scorer, Trials

OUT = Path(__file__).resolve().parent


class Cues:
    def __init__(self):
        self.cache = {}

    def of(self, pool, clip):
        key = (pool, clip)
        if key not in self.cache:
            audio, sr = sf.read(POOLS_DIR / pool / clip, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            voiced = librosa.pyin(audio, fmin=200, fmax=2500, sr=sr)[2]
            self.cache[key] = {
                "longer": len(audio) / sr,
                "louder": float(20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-9)),
                "more periodic": float(np.nanmean(voiced)),
            }
        return self.cache[key]


def main():
    trials, cues = Trials(), Cues()
    report = {}
    for pool in TRAIN_POOLS:
        graded = trials.graded(pool)
        grades = [t["grade"] for t in graded]
        for cue in ("longer", "louder", "more periodic"):
            delta = np.asarray([cues.of(pool, t["first_clip"])[cue]
                                - cues.of(pool, t["second_clip"])[cue] for t in graded])
            report.setdefault(cue, {})[pool] = round(Scorer.spearman(delta, grades), 3)
    for cue, pools in report.items():
        pools["mean"] = round(float(np.mean(list(pools.values()))), 3)
    (OUT / "shortcut.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
