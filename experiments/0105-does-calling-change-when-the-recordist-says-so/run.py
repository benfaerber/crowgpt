"""0105 — does calling intensity move at the moment a recordist says it does?

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0105-does-calling-change-when-the-recordist-says-so/run.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402


class CallingIntensity:
    """Caw rate and duty cycle of one recording, measurable over any span of it."""

    SAMPLE_RATE = 16000
    FRAME_RATE = 100.0
    BAND_HZ = (700.0, 4500.0)
    MIN_SPACING_S = 0.12
    PROMINENCE = 0.18
    HEIGHT = 0.25

    def __init__(self, audio_path: Path):
        y, sr = librosa.load(str(audio_path), sr=self.SAMPLE_RATE, mono=True)
        self.duration_s = len(y) / sr
        nyquist = sr / 2
        b, a = butter(4, [self.BAND_HZ[0] / nyquist, self.BAND_HZ[1] / nyquist], btype="band")
        hop = int(sr / self.FRAME_RATE)
        envelope = librosa.feature.rms(y=filtfilt(b, a, y).astype(np.float32),
                                       frame_length=hop * 2, hop_length=hop)[0]
        envelope = np.convolve(envelope, np.ones(3) / 3.0, mode="same")
        low, high = np.percentile(envelope, 10), np.percentile(envelope, 98)
        self.scaled = np.clip((envelope - low) / max(high - low, 1e-9), 0.0, 1.5)
        self.peaks, _ = find_peaks(
            self.scaled,
            distance=int(self.MIN_SPACING_S * self.FRAME_RATE),
            prominence=self.PROMINENCE,
            height=self.HEIGHT,
        )

    def caw_rate(self, start_s: float, end_s: float) -> float:
        lo, hi = start_s * self.FRAME_RATE, end_s * self.FRAME_RATE
        return float(np.sum((self.peaks >= lo) & (self.peaks < hi)) / max(end_s - start_s, 1e-9))

    def duty_cycle(self, start_s: float, end_s: float) -> float:
        span = self.scaled[int(start_s * self.FRAME_RATE):int(end_s * self.FRAME_RATE)]
        return float(np.mean(span > self.HEIGHT)) if len(span) else 0.0


@dataclass
class Contrast:
    """Before-and-after windows around one moment of a recording."""

    REACH_S = 30.0
    GUARD_S = 3.0
    MIN_SIDE_S = 8.0

    intensity: CallingIntensity
    t_sec: float

    @property
    def before(self) -> tuple[float, float]:
        return max(0.0, self.t_sec - self.REACH_S), self.t_sec - self.GUARD_S

    @property
    def after(self) -> tuple[float, float]:
        return self.t_sec + self.GUARD_S, min(self.intensity.duration_s, self.t_sec + self.REACH_S)

    @property
    def valid(self) -> bool:
        return min(self.before[1] - self.before[0], self.after[1] - self.after[0]) >= self.MIN_SIDE_S

    def change(self, measure: str) -> float:
        fn = getattr(self.intensity, measure)
        return fn(*self.after) - fn(*self.before)


class Corpus:
    def __init__(self):
        self.db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)

    def audio_path(self, recording_id: int) -> Path:
        (raw,) = self.db.execute("SELECT file_path FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        path = Path(raw)
        if not path.exists() and "/data/" in raw:
            path = DATA_DIR / raw.split("/data/", 1)[1]
        return path


def evaluate(event: dict, corpus: Corpus) -> dict:
    intensity = CallingIntensity(corpus.audio_path(event["recording_id"]))
    contrast = Contrast(intensity, float(event["t_sec"]))
    sign = 1.0 if event["expect"] == "up" else -1.0
    row = {
        "recording_id": event["recording_id"],
        "t_sec": event["t_sec"],
        "expect": event["expect"],
        "duration_s": round(intensity.duration_s, 1),
        "valid": contrast.valid,
        "distance_confound": bool(event.get("distance_confound")),
    }
    if not contrast.valid:
        return row
    row["rate_before"] = round(intensity.caw_rate(*contrast.before), 3)
    row["rate_after"] = round(intensity.caw_rate(*contrast.after), 3)
    row["rate_change_signed"] = round(sign * contrast.change("caw_rate"), 3)
    row["duty_change_signed"] = round(sign * contrast.change("duty_cycle"), 3)
    others = [
        sign * c.change("caw_rate")
        for c in (Contrast(intensity, float(t)) for t in range(int(intensity.duration_s)))
        if c.valid and abs(c.t_sec - contrast.t_sec) > Contrast.GUARD_S
    ]
    row["other_moments"] = len(others)
    row["fraction_of_other_moments_as_large"] = (
        round(float(np.mean(np.array(others) >= sign * contrast.change("caw_rate"))), 3) if others else None
    )
    return row


def sign_test(rows: list[dict], key: str) -> dict:
    hits = sum(1 for r in rows if r[key] > 0)
    return {"hits": hits, "n": len(rows),
            "p_one_sided": round(float(binomtest(hits, len(rows), 0.5, alternative="greater").pvalue), 4)}


def main():
    run = Run("0105 calling change at stated moments", ["measure"])
    events = json.loads((HERE / "events.json").read_text())["tier_a"]
    corpus = Corpus()
    rows = []
    with run.stage("measure") as stage:
        for i, event in enumerate(events, 1):
            rows.append(evaluate(event, corpus))
            stage.update(i, len(events))
    usable = [r for r in rows if r["valid"]]
    report = {
        "events": rows,
        "primary_caw_rate": sign_test(usable, "rate_change_signed"),
        "without_distance_confound": sign_test(
            [r for r in usable if not r["distance_confound"]], "rate_change_signed"),
        "duty_cycle": sign_test(usable, "duty_change_signed"),
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    for r in rows:
        print(r)
    print({k: v for k, v in report.items() if k != "events"})
    run.note(f"caw rate moved as described in {report['primary_caw_rate']['hits']}/{report['primary_caw_rate']['n']}")


if __name__ == "__main__":
    main()
