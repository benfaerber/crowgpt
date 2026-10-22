"""Cutting a recording into call bouts.

The burst detector is experiment 0013's, unchanged in its numerics: band energy
in 800-4000 Hz against the recording's own 20th percentile, runs merged across
gaps under 80 ms, runs under 60 ms dropped. What changes here is the threshold
and the unit.

THE THRESHOLD IS 12 dB, not the 8 dB that file defaults to. 0013 section E swept
6/8/12 and only 12 passes the control: density and duty cycle both rise
monotonically with BirdNET's confidence (1.02 -> 2.29 units per window, 11% ->
39% duty). At 6 dB density goes flat and the units are mostly background.
FUTURE.txt flags this as the trap for anyone reusing the segmentation.

THE UNIT IS A BOUT, not a single call. A caw sequence has timing, and a model
trained on isolated 0.4 s units cannot learn it — the timing would have to be
invented at assembly time, which is exactly where realism is being measured. So
bursts within 1.5 s of each other become one bout, capped at 3.0 s, and inter-
call timing is learned instead of assumed. 3.0 s is not arbitrary: it is
BirdNET's window, so a generated bout is directly judgeable.

Even at 12 dB this is a bootstrap, not a call detector — 0013 measured 1.02
units per window in the emptiest confidence band, so a minority of bursts are
not crow. Anything trained on this inherits that contamination.
"""

import numpy as np
from scipy.signal import stft

ANALYSIS_SR = 32000
BAND = (800, 4000)
NPERSEG, NOVERLAP = 512, 256
FLOOR_PCTL = 20
BURST_DB = 12.0
UNIT_MIN_SEC = 0.06
UNIT_GAP_SEC = 0.08
BOUT_GAP_SEC = 1.5
BOUT_MAX_SEC = 3.0


class Segmenter:
    """Energy bursts in the corvid band, merged into bouts."""

    def __init__(
        self,
        burst_db=BURST_DB,
        unit_min_sec=UNIT_MIN_SEC,
        unit_gap_sec=UNIT_GAP_SEC,
        bout_gap_sec=BOUT_GAP_SEC,
        bout_max_sec=BOUT_MAX_SEC,
        floor_pctl=FLOOR_PCTL,
        band=BAND,
    ):
        self.burst_db = burst_db
        self.unit_min_sec = unit_min_sec
        self.unit_gap_sec = unit_gap_sec
        self.bout_gap_sec = bout_gap_sec
        self.bout_max_sec = bout_max_sec
        self.floor_pctl = floor_pctl
        self.band = band

    def envelope(self, y, sr):
        """Band energy per frame in dB, plus the frame rate."""
        freqs, _, spectrum = stft(y, fs=sr, nperseg=NPERSEG, noverlap=NOVERLAP)
        mag = np.abs(spectrum)
        in_band = (freqs >= self.band[0]) & (freqs <= self.band[1])
        energy = np.sqrt(np.mean(mag[in_band] ** 2, axis=0))
        db = 20 * np.log10(np.maximum(energy, 1e-12))
        return db, sr / (NPERSEG - NOVERLAP)

    def bursts(self, db, fps, floor_db):
        """Contiguous runs above the floor, merged across short gaps.

        Merge happens before the minimum-duration filter, and the order is
        load-bearing: two 40 ms bursts 50 ms apart are one 130 ms call, not two
        sub-threshold ones to be thrown away.
        """
        hot = db > floor_db + self.burst_db
        if not hot.any():
            return []
        as_int = hot.astype(np.int8)
        starts = np.flatnonzero(np.diff(np.concatenate(([0], as_int))) == 1)
        ends = np.flatnonzero(np.diff(np.concatenate((as_int, [0]))) == -1) + 1

        gap_frames = self.unit_gap_sec * fps
        merged = []
        for start, end in zip(starts, ends):
            if merged and start - merged[-1][1] <= gap_frames:
                merged[-1][1] = end
            else:
                merged.append([start, end])

        min_frames = self.unit_min_sec * fps
        return [(int(s), int(e)) for s, e in merged if e - s >= min_frames]

    def bouts(self, units, fps):
        """Group units into bouts, splitting rather than truncating at the cap.

        A run of calls longer than the cap becomes several bouts. Truncating
        instead would teach the model that caw sequences stop abruptly at
        exactly 3.0 s.

        The cap has to be enforced twice. Refusing to merge past it is not
        enough, because a single burst can exceed it on its own: continuous
        energy above the floor for 23 seconds is rare but real, and left whole
        those bouts are long enough to be dropped silently by any fixed context
        window. Splitting them mid-run is arbitrary, but a 23-second unbroken
        burst has no natural boundary to respect anyway.
        """
        if not units:
            return []
        gap_frames = self.bout_gap_sec * fps
        max_frames = int(self.bout_max_sec * fps)
        min_frames = self.unit_min_sec * fps

        grouped = []
        for start, end in units:
            if not grouped:
                grouped.append([start, end])
                continue
            joined_span = end - grouped[-1][0]
            if start - grouped[-1][1] <= gap_frames and joined_span <= max_frames:
                grouped[-1][1] = end
            else:
                grouped.append([start, end])

        capped = []
        for start, end in grouped:
            while end - start > max_frames:
                capped.append((int(start), int(start + max_frames)))
                start += max_frames
            if end - start >= min_frames:
                capped.append((int(start), int(end)))
        return capped

    def segment(self, y, sr):
        """Bouts and their constituent units, as (start_sec, end_sec) pairs."""
        if y.size < NPERSEG * 4:
            return [], []
        db, fps = self.envelope(y, sr)
        floor_db = float(np.percentile(db, self.floor_pctl))
        units = self.bursts(db, fps, floor_db)
        return (
            [(s / fps, e / fps) for s, e in self.bouts(units, fps)],
            [(s / fps, e / fps) for s, e in units],
        )
