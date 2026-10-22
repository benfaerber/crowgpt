"""Did the crows sound different at the stranger than at the recordist?

The recordist's ear says yes — "PISSED at the lady, pretty calm to me" — on a
93-second walk where a woman the birds had never met and a man who feeds them
weekly went past together (capture 113, 2026-07-31). This measures whether that
is in the audio, and mostly measures why it cannot yet be.

Three things decide the answer before any number is read.

**There is one encounter with a stranger in it.** Grouped cross-validation split
by capture — which 0006 argues for and which is the only honest scoring here —
needs two recordings per class; hold out the stranger capture and no stranger
remains to learn from. So this reports no classifier and no p-value, following
0006's refusal rather than dressing noise as a result.

**Detection is confounded with recording quality.** Any amplitude-thresholded
detector finds fewer calls in a noisier recording, so a call *rate* difference
between two captures at different ranges is partly the range. This measures that
correlation rather than assuming it away, and it turns out to be the dominant
effect.

**So the confound gets tested the way 0003 tested it:** degrade the cleaner
recording past the noisier one and re-measure. If the difference survives, it is
at least not manufactured by SNR; if it collapses, it was never there.

Segmentation is `crowgpt.segment.Segmenter` at its packaged 12 dB, not a new
detector — 0013 section E swept 6/8/12 and only 12 passed the control, and
FUTURE.txt flags re-tuning it as the trap.

Run from the repo root:
    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0016-did-the-stranger-get-a-different-call/run.py
"""

import json
import sqlite3
import sys
from pathlib import Path

import librosa
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from analyzer.quality import band_snr  # noqa: E402
from crowgpt.segment import ANALYSIS_SR, BAND, Segmenter  # noqa: E402
from experiments.lib.media import audio_for, field_db  # noqa: E402

STRANGER_KEYS = ("stranger_approaching", "stranger_passing")
KNOWN_KEYS = ("known_approaching", "known_passing", "human_known")
SEED = 20260731
# 0006's gate, restated for this question: a stranger class needs recordings, not
# calls. One encounter cannot be cross-validated against itself.
MIN_RECORDINGS_PER_GROUP = 2


class Unit:
    """One detected call unit, and the shape of it."""

    def __init__(self, samples, rate, start_sec, end_sec):
        self.start_sec = start_sec
        self.duration = end_sec - start_sec
        spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
        freqs = np.fft.rfftfreq(len(samples), 1 / rate)
        band = (freqs >= BAND[0]) & (freqs <= BAND[1])
        power = spectrum[band] ** 2
        self.peak_hz = float(freqs[band][np.argmax(power)]) if power.any() else np.nan
        total = power.sum() or np.nan
        self.centroid_hz = float((freqs[band] * power).sum() / total)
        # Flatness: geometric over arithmetic mean. 1.0 is white noise, near 0 is
        # a pure tone. 0003 read a harsher call as a flatter one.
        positive = power[power > 0]
        self.flatness = float(np.exp(np.log(positive).mean()) / positive.mean()) \
            if positive.size else np.nan
        high = (freqs[band] >= 2000)
        self.high_fraction = float(power[high].sum() / total)


class Recording:
    """The human-labelled alarm spans of one capture, segmented into units."""

    def __init__(self, capture_id, name, group, distance, samples, rate, spans):
        self.id = capture_id
        self.name = name
        self.group = group
        self.distance = distance
        self.rate = rate
        self.spans = spans
        self.samples = samples
        self.units = []
        self.labelled_sec = 0.0
        self._segment()

    def _segment(self):
        segmenter = Segmenter()
        for start_sec, end_sec in self.spans:
            lo, hi = int(start_sec * self.rate), int(end_sec * self.rate)
            clip = self.samples[lo:hi]
            if len(clip) < self.rate // 2:
                continue
            self.labelled_sec += end_sec - start_sec
            _, units = segmenter.segment(clip, self.rate)
            for a, b in units:
                piece = clip[int(a * self.rate):int(b * self.rate)]
                if len(piece) >= 128:
                    self.units.append(Unit(piece, self.rate, start_sec + a, start_sec + b))

    @property
    def snr_db(self):
        """Band SNR, or nan where it is undefined.

        band_snr is p99/p10 of per-frame band RMS, so a recording holding a
        digitally silent frame divides by zero and returns inf. That is a real
        property of capture 100, not a bug to paper over — it just cannot go
        into a correlation.
        """
        value = float(band_snr(self.samples, self.rate))
        return value if np.isfinite(value) else np.nan

    @property
    def unit_rate(self):
        return len(self.units) / self.labelled_sec if self.labelled_sec else np.nan

    def median(self, attr):
        values = [getattr(u, attr) for u in self.units]
        values = [v for v in values if np.isfinite(v)]
        return float(np.median(values)) if values else np.nan

    @property
    def median_gap(self):
        starts = sorted(u.start_sec for u in self.units)
        gaps = [b - a for a, b in zip(starts, starts[1:]) if b - a < 5.0]
        return float(np.median(gaps)) if gaps else np.nan

    def degraded_to(self, target_snr_db, rng):
        """A copy of this recording noised down to another's band SNR.

        0003's control. Added noise is broadband, so it makes calls measure
        harsher and shorter-lived — if a difference points the other way it
        cannot have been made by the noise.
        """
        noisy = self.samples.copy()
        for _ in range(40):
            if band_snr(noisy, self.rate) <= target_snr_db:
                break
            noisy += rng.normal(0, 0.004 * np.abs(self.samples).max(), len(noisy))
        return Recording(self.id, self.name + " (degraded)", self.group,
                         self.distance, noisy, self.rate, self.spans)


class Corpus:
    def __init__(self):
        self.conn = sqlite3.connect(f"file:{field_db()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def _group_for(self, label_ids):
        keys = set()
        for label_id in label_ids:
            keys |= {r["key"] for r in self.conn.execute(
                "SELECT key FROM context_events WHERE label_id = ?", (label_id,))}
        if keys & set(STRANGER_KEYS):
            return "stranger"
        if keys & set(KNOWN_KEYS):
            return "known"
        return "unclassified"

    def load(self):
        rows = self.conn.execute(
            "SELECT l.id, l.capture_id, l.start_sec, l.end_sec, c.name, c.distance_band "
            "FROM labels l JOIN captures c ON c.id = l.capture_id "
            "WHERE l.call_type = 'alarm call' AND l.label_source = 'human' AND c.keep = 1 "
            "ORDER BY l.capture_id, l.start_sec").fetchall()
        by_capture = {}
        for row in rows:
            by_capture.setdefault(row["capture_id"], []).append(row)

        recordings = []
        for capture_id, labels in by_capture.items():
            try:
                path = audio_for(capture_id)
            except SystemExit:
                print(f"  capture {capture_id}: no audio, skipped")
                continue
            samples, rate = librosa.load(path, sr=ANALYSIS_SR, mono=True)
            recordings.append(Recording(
                capture_id, labels[0]["name"],
                self._group_for([r["id"] for r in labels]),
                labels[0]["distance_band"], samples, rate,
                [(r["start_sec"], r["end_sec"]) for r in labels]))
        return recordings


class Report:
    FEATURES = [("duration", "duration s"), ("peak_hz", "peak Hz"),
                ("centroid_hz", "centroid Hz"), ("flatness", "flatness"),
                ("high_fraction", ">2kHz frac")]

    def __init__(self, recordings):
        self.all = recordings
        self.classified = [r for r in recordings if r.group != "unclassified"]
        self.result = {}

    def _table(self):
        print("=" * 92)
        print("ALARM SPANS BY RECORDING (segmented with crowgpt.segment at 12 dB)")
        print("=" * 92)
        print(f"  {'cap':>4} {'group':>12} {'dist':>9} {'snr dB':>7} {'secs':>6} "
              f"{'units':>5} {'units/s':>8} {'dur s':>7} {'gap s':>6} {'peak':>6} {'flat':>6}")
        for r in sorted(self.all, key=lambda r: (r.group, r.id)):
            print(f"  {r.id:>4} {r.group:>12} {str(r.distance or '-'):>9} "
                  f"{r.snr_db:>7.1f} {r.labelled_sec:>6.1f} {len(r.units):>5} "
                  f"{r.unit_rate:>8.2f} {r.median('duration'):>7.3f} "
                  f"{r.median_gap:>6.2f} {r.median('peak_hz'):>6.0f} "
                  f"{r.median('flatness'):>6.3f}")

    def _confound(self):
        print()
        print("=" * 92)
        print("CONFOUND 1 — does the detector just find more calls in cleaner audio?")
        print("=" * 92)
        usable = [r for r in self.all if np.isfinite(r.unit_rate) and np.isfinite(r.snr_db)]
        snrs = [r.snr_db for r in usable]
        rates = [r.unit_rate for r in usable]
        r_value = float(np.corrcoef(snrs, rates)[0, 1]) if len(usable) > 2 else np.nan
        self.result["rate_vs_snr_r"] = r_value
        self.result["n_recordings_for_r"] = len(usable)
        print(f"  detected units/sec vs band SNR across {len(usable)} recordings: "
              f"r = {r_value:+.2f}")
        print("  Underpowered and not the real evidence — five points, and the")
        print("  recordings differ in range, birds, and how much was labelled. The")
        print("  controlled version is confound 2, which noises one recording down")
        print("  and holds everything else fixed.")

    def _matched_pair(self, rng):
        stranger = next((r for r in self.classified if r.group == "stranger"), None)
        control = next((r for r in self.classified if r.id == 114), None)
        if not stranger or not control:
            return
        print()
        print("=" * 92)
        print("CONFOUND 2 — degrade the cleaner recording past the noisier one (0003's control)")
        print("=" * 92)
        print("  Same evening, same fleet, same mic, 32 minutes apart. The closest thing")
        print("  to a control the corpus has, and still not a controlled one: the ranges")
        print(f"  differ ({stranger.distance} vs {control.distance}).")
        print()
        degraded = stranger.degraded_to(control.snr_db, rng)
        rows = [("stranger", stranger), ("stranger degraded", degraded),
                ("recordist alone", control)]
        print(f"  {'':>18} {'snr dB':>7} {'units':>6} {'units/s':>8} " +
              " ".join(f"{lab:>11}" for _, lab in self.FEATURES))
        for name, rec in rows:
            print(f"  {name:>18} {rec.snr_db:>7.1f} {len(rec.units):>6} "
                  f"{rec.unit_rate:>8.2f} " +
                  " ".join(f"{rec.median(attr):>11.3f}" for attr, _ in self.FEATURES))
        self.result["matched_pair"] = {
            name: {"snr_db": rec.snr_db, "units": len(rec.units),
                   "unit_rate": rec.unit_rate,
                   **{attr: rec.median(attr) for attr, _ in self.FEATURES}}
            for name, rec in rows}

        lost = 1 - len(degraded.units) / len(stranger.units) if stranger.units else np.nan
        print()
        print(f"  Noising the stranger recording down to the control's SNR lost "
              f"{lost:.0%} of its")
        print("  detected units. That is the detector's range sensitivity measured")
        print("  directly, and it is why the raw rate difference cannot be read as")
        print("  the birds calling more.")
        print()
        survival = {}
        for attr, label in [("duration", "unit duration"), ("peak_hz", "peak frequency"),
                            ("flatness", "flatness"), ("high_fraction", ">2 kHz fraction")]:
            raw = stranger.median(attr) - control.median(attr)
            after = degraded.median(attr) - control.median(attr)
            if not (np.isfinite(raw) and np.isfinite(after)) or raw == 0:
                continue
            kept = after / raw
            survival[attr] = kept
            verdict = ("holds" if kept >= 0.7 else
                       "mostly SNR" if kept >= 0.3 else
                       "gone" if kept >= 0 else "reverses")
            # Which way the added noise pushed this measure. A gap that grows
            # under degradation is not a surviving gap — it is the noise, since
            # broadband noise raises exactly the harshness measures. 0003 had the
            # luck of a confound pointing the other way; this one does not.
            drift = "away from control (noise inflates it)" if abs(kept) > 1 \
                else "toward control"
            print(f"  {label:>16}: gap {raw:+8.3f} raw -> {after:+8.3f} degraded  "
                  f"({kept:+.0%} kept, {verdict}; moved {drift})")
        self.result["gap_kept_after_degrading"] = survival
        self.result["units_lost_to_degrading"] = float(lost)
        print()
        print("  A gap that shrinks when noise is added was partly made of the")
        print("  difference in recording quality. 0003 noted added noise pushes")
        print("  calls to measure harsher and broader, so a gap that reverses under")
        print("  degradation was never pointing the way it appeared to.")

    def _gate(self):
        print()
        print("=" * 92)
        print("CAN THIS BE TESTED?")
        print("=" * 92)
        counts = {}
        for r in self.classified:
            counts[r.group] = counts.get(r.group, 0) + 1
        for group in ("stranger", "known"):
            print(f"  {group:>9}: {counts.get(group, 0)} recording(s), "
                  f"{sum(len(r.units) for r in self.classified if r.group == group)} units")
        self.result["recordings_per_group"] = counts
        short = [g for g in ("stranger", "known")
                 if counts.get(g, 0) < MIN_RECORDINGS_PER_GROUP]
        self.result["testable"] = not short
        if short:
            print()
            print(f"  Not testable. {', '.join(short)} has fewer than "
                  f"{MIN_RECORDINGS_PER_GROUP} recordings, so a fold that holds out a")
            print("  recording also holds out the class. No accuracy and no p-value are")
            print("  reported, on purpose — following 0006, a number from this much data")
            print("  would be noise wearing a result's clothes.")
            print()
            print("  'Stranger' and 'that particular walk' are currently the same variable.")
            print("  Nothing in the audio can separate them; only more encounters can.")

    def run(self):
        rng = np.random.default_rng(SEED)
        self._table()
        self._confound()
        self._matched_pair(rng)
        self._gate()
        return self.result


def main():
    print(f"reading {field_db()}\n")
    recordings = Corpus().load()
    if not recordings:
        raise SystemExit("no alarm-call spans with audio")
    result = Report(recordings).run()
    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
