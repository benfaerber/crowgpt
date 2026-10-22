"""One window policy, shared by every backbone in the bake-off.

The comparison this exists for is delicate in a way that is easy to miss.
BirdNET's native window is 3 s and Perch's is 5 s, so the naive implementation
hands Perch two extra seconds of audio and then reports the difference as a
finding about the backbone. It would be a finding about the window.

So audio is decoded once, at 48 kHz, into a fixed-width excerpt centred on the
labelled second, and every arm takes its window out of that same buffer. An arm
asking for 3 s and an arm asking for 5 s differ in exactly one variable, and the
context ladder (Perch at 1, 3 and 5 s) turns that variable into a measurement
rather than a confound.

Why 48 kHz: it is BirdNET's native rate, so the incumbent arm is never
resampled at all, and it reaches Perch's 32 kHz by an exact 2:3 `resample_poly`
and BirdAVES' 16 kHz by 1:3. No arm eats a different resampler's artefacts, and
none of them eat two.

Why no peak normalisation: the deployed path does none, and experiment 0022
showed level moves BirdNET's numbers. Adding it here would be a new variable
introduced to the one place that is supposed to hold everything constant.

The cache is ~4 GB and lives under data/, which is gitignored — the numbers are
the durable part, not the audio.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR") or REPO / "data")

#: Everything is stored at BirdNET's native rate and resampled down from it.
CACHE_SR = 48_000

#: Half the stored width. 4.5 s each side covers a 5 s window centred on the
#: labelled second with 2 s of slack, which is enough for every arm planned and
#: for a 9 s arm if one is ever wanted.
HALF_WIDTH_SEC = 4.5

#: How long one ffmpeg call may run before it is killed. Same reasoning as
#: analyzer/birdnet.py's MEDIA_TIMEOUT_SEC — a malformed container makes a
#: decoder spin rather than fail, and without a bound one bad file stalls the
#: whole build silently.
DECODE_TIMEOUT_SEC = 60


def segment_keys(corpus):
    """THE canonical row order: sorted segment keys with audio on disk.

    Sorted rather than corpus order on purpose. build_dataset.py's rows are in
    whatever order `labeled_segments` happened to yield, which is stable only as
    long as the audio directory is — and 97 recordings have already left it. A
    sorted key list is reproducible across machines and across that drift.
    """
    return sorted(seg.key for seg in corpus.labeled_segments(require_audio=True))


class ExcerptCache:
    """Fixed-width 48 kHz excerpts, one per labelled segment, on disk.

    Stored as a flat float32 memmap plus a key list, so an arm can stream rows
    without holding 4 GB of audio in memory and a rebuild can resume rather than
    start over.
    """

    def __init__(self, root, *, half_width_sec=HALF_WIDTH_SEC, sr=CACHE_SR):
        self.root = Path(root)
        self.half_width_sec = half_width_sec
        self.sr = sr
        self.samples_per_row = int(round(2 * half_width_sec * sr))
        self._data = None
        self._keys = None

    @property
    def audio_path(self):
        return self.root / "excerpts_48k.f32"

    @property
    def keys_path(self):
        return self.root / "keys.json"

    @property
    def state_path(self):
        return self.root / "built.json"

    def build(self, segments, *, jobs=None, log=print):
        """Decode one excerpt per segment. Resumable, and safe to re-run.

        `segments` maps key -> LabeledSegment. Rows already decoded in a
        previous run are skipped, so an interrupted build costs only what it had
        not finished.

        Work is grouped **by recording**, and that is a correctness requirement
        rather than an optimisation. The first version of this seeked per
        segment with `ffmpeg -ss` *before* `-i`, which on mp3 is a fast seek to
        the nearest frame boundary — so roughly half the corpus came out shifted
        by a few tens of milliseconds, at random. Measured against the committed
        BirdNET cache: 1,028 of 2,035 rows matched to 1e-4 and the rest sat at
        cosine 0.98, with no pattern in the labels. A random millisecond jitter
        over half the rows is precisely the confound an experiment about
        temporal alignment cannot carry.

        Decoding each recording once from the start and slicing every segment
        out of it is sample-exact, and with ~2.1 segments per recording it is
        also faster than seeking.
        """
        import json
        from concurrent.futures import ThreadPoolExecutor

        keys = sorted(segments)
        self.root.mkdir(parents=True, exist_ok=True)
        jobs = jobs or max(1, (os.cpu_count() or 4) - 2)

        done = set()
        if self.state_path.exists() and self.audio_path.exists():
            state = json.loads(self.state_path.read_text())
            if state.get("keys") == keys and state.get("sr") == self.sr:
                done = set(state.get("done", []))
                log(f"excerpts: resuming — {len(done)}/{len(keys)} already decoded")
            else:
                log("excerpts: cache describes a different row set, rebuilding")

        want = self.samples_per_row * len(keys) * 4
        if not self.audio_path.exists() or self.audio_path.stat().st_size != want:
            with open(self.audio_path, "wb") as fh:
                fh.truncate(want)
            done = set()

        data = np.memmap(self.audio_path, dtype=np.float32, mode="r+",
                         shape=(len(keys), self.samples_per_row))

        row_of = {k: i for i, k in enumerate(keys)}
        by_recording = {}
        for key in keys:
            if key not in done:
                by_recording.setdefault(str(segments[key].audio_path), []).append(key)
        log(f"excerpts: {sum(len(v) for v in by_recording.values())} to decode from "
            f"{len(by_recording)} recordings across {jobs} workers "
            f"({len(keys)} rows, {want / 1e9:.1f} GB)")

        failed = []

        def decode_recording(item):
            path, group = item
            track = self._decode_whole(path)
            if track is None:
                return group, []
            ok = []
            for key in group:
                data[row_of[key]] = self._excerpt(track, segments[key])
                ok.append(key)
            return group, ok

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for n, (group, ok) in enumerate(
                    pool.map(decode_recording, by_recording.items()), 1):
                done.update(ok)
                failed.extend(k for k in group if k not in ok)
                if n % 100 == 0:
                    log(f"excerpts: {n}/{len(by_recording)} recordings decoded")
                    self._save_state(keys, done)

        data.flush()
        self._save_state(keys, done)
        self.keys_path.write_text(json.dumps(keys))
        if failed:
            log(f"excerpts: {len(failed)} failed to decode, e.g. {failed[:3]}")
        log(f"excerpts: done — {len(done)}/{len(keys)} rows at {self.audio_path}")
        return [k for k in keys if k in done]

    def _save_state(self, keys, done):
        import json
        self.state_path.write_text(json.dumps(
            {"sr": self.sr, "half_width_sec": self.half_width_sec,
             "keys": keys, "done": sorted(done)}))

    def _decode_whole(self, path):
        """A whole recording as mono float32 at the cache rate, or None.

        No `-ss`. See `build` — seeking mp3 is the bug this avoids.
        """
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
               "-ac", "1", "-ar", str(self.sr), "-f", "f32le", "-"]
        try:
            done = subprocess.run(cmd, capture_output=True,
                                  timeout=DECODE_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            print(f"  timeout decoding {Path(path).name}", file=sys.stderr)
            return None
        if done.returncode != 0:
            print(f"  ffmpeg failed on {Path(path).name}: "
                  f"{done.stderr.decode('utf8', 'replace')[:120]}", file=sys.stderr)
            return None
        return np.frombuffer(done.stdout, dtype=np.float32)

    def _excerpt(self, track, seg):
        """One segment's window out of its decoded recording.

        Centred on the middle of the labelled second — every crow-tools span is
        exactly one second (3,162 of 3,162), so that is unambiguous. Clamped at
        the file edges and symmetrically zero-padded, so a call in the first
        second of a recording is still centred rather than shifted.
        """
        want = self.samples_per_row
        start = int(round(((seg.start + seg.end) / 2 - self.half_width_sec) * self.sr))
        out = np.zeros(want, dtype=np.float32)
        lead = max(0, -start)
        lo = max(0, start)
        take = min(want - lead, max(0, len(track) - lo))
        if take > 0:
            out[lead:lead + take] = track[lo:lo + take]
        return out

    def load(self):
        """(memmap of shape (rows, samples), keys) — read-only."""
        import json
        if self._data is None:
            if not self.audio_path.exists():
                raise SystemExit(
                    f"No excerpt cache at {self.audio_path}. Build it first:\n"
                    f"  python experiments/0025-is-birdnet-the-bottleneck/run.py --build-cache"
                )
            self._keys = json.loads(self.keys_path.read_text())
            self._data = np.memmap(self.audio_path, dtype=np.float32, mode="r",
                                   shape=(len(self._keys), self.samples_per_row))
        return self._data, self._keys

    def window(self, row, seconds, sr, *, pad="zero", rng=None):
        """A centred window of `seconds` at `sr`, out of one cached row.

        This is the function the whole experiment turns on. Every arm calls it,
        so "Perch got more context" is a claim about its `seconds` argument and
        nothing else.

        `pad="noise"` fills outside the requested span with band-limited noise
        at the excerpt's own 10th-percentile level instead of digital silence.
        Perch requires exactly 5 s, so a 3 s arm is 40% padding, and a model
        that reacts to a silence cliff would make the short arms look bad for a
        reason unrelated to context. Running both pads is how we tell.
        """
        row = np.asarray(row, dtype=np.float32)
        centre = len(row) // 2
        half = int(round(seconds * self.sr / 2))
        lo, hi = max(0, centre - half), min(len(row), centre + half)
        clip = row[lo:hi]

        if sr != self.sr:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(sr, self.sr)
            clip = resample_poly(clip, sr // g, self.sr // g).astype(np.float32)

        want = int(round(seconds * sr))
        if len(clip) < want:
            clip = np.pad(clip, (0, want - len(clip)))
        return clip[:want]

    def padded(self, row, seconds, model_seconds, sr, *, pad="zero", rng=None):
        """`seconds` of real audio, centred inside a `model_seconds` buffer.

        Returns (samples, mask) where mask marks which samples are real. Perch
        will not accept anything but its native 5 s, so a 3 s arm has to be
        padded — and the mask is what stops the padding being averaged into the
        embedding as though it were audio. See `time_mask` for the pooling side.
        """
        clip = self.window(row, seconds, sr, pad=pad)
        want = int(round(model_seconds * sr))
        if len(clip) >= want:
            return clip[:want], np.ones(want, dtype=bool)

        lead = (want - len(clip)) // 2
        out = np.zeros(want, dtype=np.float32)
        mask = np.zeros(want, dtype=bool)
        if pad == "noise":
            level = float(np.percentile(np.abs(clip), 10)) if len(clip) else 0.0
            rng = rng or np.random.default_rng(0)
            out[:] = rng.normal(0.0, max(level, 1e-6), want).astype(np.float32)
        out[lead:lead + len(clip)] = clip
        mask[lead:lead + len(clip)] = True
        return out, mask


def real_fraction(mask):
    """How much of a padded buffer is actually audio.

    The plan for the context ladder was to pool Perch's 5x3x1536 spatial
    embedding over a time mask, so a 3 s arm would not average two frames of
    silence into its answer. perch-hoplite does not expose that grid — `embed()`
    returns one 1536-d vector per 5 s window, already pooled — so the masking
    cannot be done at this interface.

    What is left is honesty about it: every short arm of the ladder is part
    audio and part padding, this reports which, and the noise-pad variant
    measures what the padding is worth. See the README.
    """
    return float(np.mean(mask))
