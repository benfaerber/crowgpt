"""Is the ghost the model's uncertainty made audible?

Ben on the -2 tail: "a new thing I can't describe. Not like a robot. Like a
ghost crow almost." Hypothesis: past its coherent context the model emits
low-confidence continuations — spectrally caw-shaped, energetically hollow.
The segmenter counts them (which is how the gate scored structure gains) but
the ear rejects them. Prediction: in the failed longctx clips, LATE bursts
are fainter and less transient than early ones, and than real late bursts.

Runs on the exact clips of the -2 trials, straight off the pool dir.
"""
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

import numpy as np
import soundfile as sf

from crowgpt.segment import Segmenter

DB = REPO / "fieldserver" / "instance" / "field.db"
CLIP_DIR = REPO / "crowgpt" / "results" / "listening-pools" / "longctx-0067"
SR = 24000


def bursts_with_energy(path):
    audio, _ = sf.read(path, dtype="float32")
    seg = Segmenter()
    db, fps = seg.envelope(audio, SR)
    floor = np.percentile(db, seg.floor_pctl)
    out = []
    for start, end in seg.bursts(db, fps, floor):
        chunk = audio[int(start / fps * SR): int(end / fps * SR)]
        if chunk.size == 0:
            continue
        peak = float(np.max(np.abs(chunk)) + 1e-9)
        rms = float(np.sqrt(np.mean(chunk ** 2)) + 1e-9)
        out.append({"mid_s": (start + end) / 2 / fps,
                    "peak_db": 20 * np.log10(peak),
                    "crest_db": 20 * np.log10(peak / rms)})
    return out, audio.size / SR


def halves(bursts, duration):
    early = [b for b in bursts if b["mid_s"] < duration / 2]
    late = [b for b in bursts if b["mid_s"] >= duration / 2]
    med = lambda xs, k: round(float(np.median([x[k] for x in xs])), 1) if xs else None
    return {"n_early": len(early), "n_late": len(late),
            "early_peak_db": med(early, "peak_db"), "late_peak_db": med(late, "peak_db"),
            "early_crest": med(early, "crest_db"), "late_crest": med(late, "crest_db")}


def main():
    db = sqlite3.connect(DB)
    rows = list(db.execute(
        """SELECT t.first_arm, t.first_clip, t.second_clip, t.anchor_clip, a.grade
           FROM listening_answers a JOIN listening_trials t ON t.id = a.trial_id
           JOIN listening_pools p ON p.id = t.pool_id
           WHERE p.name = 'longctx-0067' AND t.kind = 'compare'"""))

    ghost_deltas, real_deltas = [], []
    for first_arm, first, second, anchor, grade in rows:
        longctx_first = first_arm == "model-longctx"
        if not ((grade == -2 and longctx_first) or (grade == 2 and not longctx_first)):
            continue
        lc = first if longctx_first else second
        for name, bucket in ((lc, ghost_deltas), (anchor, real_deltas)):
            bursts, dur = bursts_with_energy(CLIP_DIR / name)
            h = halves(bursts, dur)
            print(f"{name}: {h}")
            if h["early_peak_db"] is not None and h["late_peak_db"] is not None:
                bucket.append(h["late_peak_db"] - h["early_peak_db"])

    print(f"\nlate-minus-early peak (median): "
          f"longctx {np.median(ghost_deltas):+.1f} dB over {len(ghost_deltas)} clips · "
          f"real anchors {np.median(real_deltas):+.1f} dB over {len(real_deltas)}")


if __name__ == "__main__":
    main()
