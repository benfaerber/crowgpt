"""Corpus -> call bouts on disk.

Experiment 0013 measured ~65,000 call units and then threw the boundaries away —
"Returns summary counts and the per-unit durations, never audio". This re-runs
the segmentation and keeps the audio, which is the thing nothing on disk has.

Two filters stand between a burst and the training set:

  1. The bout's midpoint must land in a 3-second window BirdNET scores as a
     corvid at CROW_MIN_CONF. 0013 section C found 1,381 distinct non-corvid
     species in these recordings, so a generator handed whole recordings would
     learn wood-pigeon as readily as crow.
  2. Optionally the tail of long recordings, where archive recordists
     announce species, location and date. This is belt-and-braces — spoken
     announcements do not score as corvid, so filter 1 already removes them —
     and it is reported separately so its cost is visible rather than assumed.

Thresholds come from analyzer/birdnet.py rather than being restated here, so
the gate is the one the pipeline actually uses.
"""

import contextlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from crowgpt.corpus import Corpus, REPO
from crowgpt.segment import ANALYSIS_SR, Segmenter

OUTPUT_SR = 24000
TAIL_TRIM_SEC = 8.0
TAIL_TRIM_MIN_DURATION = 40.0

# THE 2026-08 SCRAPE KILLED THE POOL, and these three constants are the fix.
# A worker holds a recording in memory TWICE — librosa's copy and birdnetlib's
# own whole-file load inside _crow_grid — so twelve workers meeting the
# scrape's multi-hour recordings was an OOM kill, and one killed worker is
# BrokenProcessPool for the whole run (2026-08-09, ~9k recordings in). Files
# over LONG_FILE_SEC now stream through SLICE_SEC windows instead: bounded
# memory whatever the file length. The overlap exists so a bout straddling a
# slice edge is whole in at least one slice; ownership by midpoint keeps it
# out of both.
SLICE_SEC = 900.0
SLICE_OVERLAP_SEC = 5.0
LONG_FILE_SEC = 1200.0

ANALYZER = None
CONF = {}


def analyzer_constants():
    """CROW_MIN_CONF and friends from the shipped analyzer, loaded once.

    From analyzer.thresholds, which costs nothing to import — the full
    analyzer.birdnet builds an Analyzer and every call-type head at import
    time, which is why this reads the constants-only module instead.
    """
    sys.path.insert(0, str(REPO))
    from analyzer import thresholds

    return {
        "CROW_TERMS": tuple(thresholds.CROW_TERMS),
        "CROW_MIN_CONF": thresholds.CROW_MIN_CONF,
        "CANDIDATE_MIN_CONF": thresholds.CANDIDATE_MIN_CONF,
        "WINDOW_SEC": thresholds.WINDOW_SEC,
    }


def _init(conf):
    global ANALYZER, CONF
    CONF = conf
    from birdnetlib.analyzer import Analyzer

    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        ANALYZER = Analyzer()


def _is_corvid(name, terms):
    return any(term in name.lower() for term in terms)


def _crow_grid(path, duration):
    """Max corvid confidence per 3-second window."""
    from birdnetlib import Recording as BirdRecording

    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        rec = BirdRecording(ANALYZER, str(path), min_conf=CONF["CANDIDATE_MIN_CONF"])
        rec.analyze()

    window = CONF["WINDOW_SEC"]
    n_windows = max(1, int(duration // window))
    grid = np.zeros(n_windows)
    for det in rec.detections:
        name = f"{det.get('common_name', '')} {det.get('scientific_name', '')}"
        if not _is_corvid(name, CONF["CROW_TERMS"]):
            continue
        idx = int(det["start_time"] // window)
        if 0 <= idx < n_windows:
            grid[idx] = max(grid[idx], det["confidence"])
    return grid, window


def _keepable(y, sr, grid, window, meta, offset=0.0, own_until=float("inf"),
              tail_cut=float("inf")):
    """Bouts from one loaded span, filtered and cut.

    `y` and `grid` cover the same span; bout times from the segmenter are
    local to it. `offset` places the span in recording time — bout records
    carry GLOBAL start times, and ownership (`own_until`) and the tail trim
    are judged globally so a sliced file behaves like a whole one. A bout
    whose global midpoint falls at or past `own_until` is left for the next
    slice, which holds it in full thanks to the overlap.
    """
    # The cap is overridable for the long-context arm (0067): 3 s bouts
    # discard between-call structure by construction, and raising the cap at
    # extraction is the only place it can be raised. Env rather than a
    # threaded parameter because analyse() runs in pool workers that get
    # their config through _init, and the knob must reach both paths.
    cap = float(os.environ.get("CROWGPT_BOUT_MAX_SEC", 0) or 0)
    segmenter = Segmenter(bout_max_sec=cap) if cap else Segmenter()
    bouts, units = segmenter.segment(y, sr)
    kept, audio = [], []
    dropped_conf = dropped_tail = 0
    for start, end in bouts:
        g_mid = (start + end) / 2 + offset
        if g_mid >= own_until:
            continue
        idx = min(int(((start + end) / 2) // window), len(grid) - 1)
        if grid[idx] < CONF["CROW_MIN_CONF"]:
            dropped_conf += 1
            continue
        if g_mid > tail_cut:
            dropped_tail += 1
            continue
        chunk = y[int(start * sr) : int(end * sr)]
        if chunk.size < sr * 0.06:
            continue
        resampled = resample_poly(chunk, OUTPUT_SR, sr)
        peak = float(np.max(np.abs(resampled))) or 1.0
        audio.append(np.clip(resampled / peak * 0.89, -1.0, 1.0))
        kept.append(
            {
                "species": meta["species"],
                "recording_id": meta["recording_id"],
                "group_key": meta["group_key"],
                "quality": meta["quality"],
                "start_sec": round(start + offset, 3),
                "dur_sec": round(end - start, 3),
                "crow_conf": round(float(grid[idx]), 3),
            }
        )
    return {"kept": kept, "audio": audio, "n_units": len(units),
            "n_bouts": len(bouts), "dropped_conf": dropped_conf,
            "dropped_tail": dropped_tail}


def _probe_seconds(path):
    """Duration without decoding the audio. None means 'could not say'."""
    try:
        import librosa

        return float(librosa.get_duration(path=str(path)))
    except Exception:
        return None


def _analyse_sliced(path, duration, meta):
    """A long recording, one bounded slice at a time.

    birdnetlib only takes a file, so each slice is written to a temp wav for
    its _crow_grid — an extra write, and the price of never holding more
    than SLICE_SEC of audio however long the recording runs.
    """
    import tempfile

    import librosa
    import soundfile as sf

    tail_cut = duration - TAIL_TRIM_SEC if duration > TAIL_TRIM_MIN_DURATION \
        else duration
    totals = {"kept": [], "audio": [], "n_units": 0, "n_bouts": 0,
              "dropped_conf": 0, "dropped_tail": 0}
    offset = 0.0
    while offset < duration:
        span = min(SLICE_SEC + SLICE_OVERLAP_SEC, duration - offset)
        try:
            y, sr = librosa.load(path, sr=ANALYSIS_SR, mono=True,
                                 offset=offset, duration=span)
        except Exception as exc:
            return {"recording_id": meta["recording_id"],
                    "species": meta["species"], "error": str(exc)}
        if y.size == 0:
            break
        last = offset + span >= duration
        own_until = float("inf") if last else offset + SLICE_SEC
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav") as slice_file:
                sf.write(slice_file.name, y, int(sr), subtype="PCM_16")
                grid, window = _crow_grid(slice_file.name, y.size / sr)
        except Exception as exc:
            return {"recording_id": meta["recording_id"],
                    "species": meta["species"], "error": str(exc)}
        part = _keepable(y, sr, grid, window, meta, offset=offset,
                         own_until=own_until, tail_cut=tail_cut)
        for key in totals:
            totals[key] += part[key]
        offset += SLICE_SEC
    return {
        "recording_id": meta["recording_id"],
        "species": meta["species"],
        "duration": duration,
        "n_units": totals["n_units"],
        "n_bouts": totals["n_bouts"],
        "dropped_conf": totals["dropped_conf"],
        "dropped_tail": totals["dropped_tail"],
        "kept": totals["kept"],
        "audio": [(a * 32767).astype(np.int16) for a in totals["audio"]],
    }


def analyse(item):
    """One recording -> its keepable bouts as int16 at 24 kHz."""
    # `quality` is unpacked with a default so an index written by the older
    # four-tuple form still loads. It rides through to every bout because
    # `Corpus.Recording` has always carried it and this was the one place it
    # was dropped — which meant a corpus could arrive at mixed quality and
    # then never filtered by it without re-extracting all 81,389 bouts.
    path, species, recording_id, group_key, *rest = item
    quality = rest[0] if rest else None
    meta = {"species": species, "recording_id": recording_id,
            "group_key": group_key, "quality": quality}

    probe = _probe_seconds(path)
    if probe is not None and probe > LONG_FILE_SEC:
        return _analyse_sliced(path, probe, meta)

    try:
        import librosa

        y, sr = librosa.load(path, sr=ANALYSIS_SR, mono=True)
    except Exception as exc:
        return {"recording_id": recording_id, "species": species, "error": str(exc)}

    duration = y.size / sr
    if duration <= 0:
        return {"recording_id": recording_id, "species": species, "error": "empty"}

    try:
        grid, window = _crow_grid(path, duration)
    except Exception as exc:
        return {"recording_id": recording_id, "species": species, "error": str(exc)}

    tail_cut = duration
    if duration > TAIL_TRIM_MIN_DURATION:
        tail_cut = duration - TAIL_TRIM_SEC

    part = _keepable(y, sr, grid, window, meta, tail_cut=tail_cut)
    return {
        "recording_id": recording_id,
        "species": species,
        "duration": duration,
        "n_units": part["n_units"],
        "n_bouts": part["n_bouts"],
        "dropped_conf": part["dropped_conf"],
        "dropped_tail": part["dropped_tail"],
        "kept": part["kept"],
        "audio": [(a * 32767).astype(np.int16) for a in part["audio"]],
    }


class Extractor:
    """Runs the corpus through segmentation and writes the bout shards."""

    def __init__(self, out_dir, limit_per_species=None, workers=None, on_progress=None):
        self.out_dir = Path(out_dir)
        self.limit = limit_per_species
        self.workers = workers or min(12, max(1, (os.cpu_count() or 4) - 2))
        # Progress belongs to the caller's Run, threaded in through this hook.
        # This class must never write the progress record itself: that record
        # is the whole-run status, and a second writer turns it into whichever
        # of them wrote last.
        self.on_progress = on_progress

    def note(self, line, done=None, total=None):
        print(line, flush=True)
        if self.on_progress:
            self.on_progress(line, done, total)

    def run(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        found = Corpus(limit_per_species=self.limit).recordings()
        items = [
            (str(r.path), r.species, r.recording_id, r.group_key, r.quality)
            for recs in found.values()
            for r in recs
        ]
        self.note(f"   {len(items)} recordings across {len(found)} species")

        shards = {slug: open(self.out_dir / f"{slug}.i16", "wb") for slug in found}
        offsets = {slug: 0 for slug in found}
        index_path = self.out_dir / "index.jsonl"
        totals = {
            "recordings": 0,
            "errors": 0,
            "units": 0,
            "bouts": 0,
            "kept": 0,
            "dropped_conf": 0,
            "dropped_tail": 0,
            "seconds": 0.0,
        }

        try:
            with open(index_path, "w") as index:
                # Spawn, not fork. The default fork shares the parent's memory
                # with 24 children, and after this stage the parent could no
                # longer see the GPU — tokenising and training both silently
                # fell back to the CPU and ran ~240x slower for ten hours.
                # Spawn starts each worker clean, so nothing the pool does can
                # reach back into the parent's CUDA state. Costs a few seconds
                # of extra startup on a stage that takes twenty minutes.
                with ProcessPoolExecutor(
                    self.workers, initializer=_init, initargs=(analyzer_constants(),),
                    mp_context=get_context("spawn"),
                ) as pool:
                    for i, row in enumerate(pool.map(analyse, items, chunksize=4), 1):
                        totals["recordings"] += 1
                        if row.get("error"):
                            totals["errors"] += 1
                        else:
                            self._write(row, shards, offsets, index, totals)
                        if i % 100 == 0 or i == len(items):
                            self.note(
                                f"   {i}/{len(items)} recordings · "
                                f"{totals['kept']} bouts · "
                                f"{totals['seconds'] / 60:.1f} min kept",
                                done=i, total=len(items),
                            )
        finally:
            for handle in shards.values():
                handle.close()

        summary = {
            **totals,
            "seconds": round(totals["seconds"], 1),
            "hours": round(totals["seconds"] / 3600, 3),
            "per_species": self._per_species(index_path),
        }
        (self.out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary

    def _write(self, row, shards, offsets, index, totals):
        slug = row["species"]
        totals["units"] += row["n_units"]
        totals["bouts"] += row["n_bouts"]
        totals["dropped_conf"] += row["dropped_conf"]
        totals["dropped_tail"] += row["dropped_tail"]
        for meta, samples in zip(row["kept"], row["audio"]):
            shards[slug].write(samples.tobytes())
            meta["sample_offset"] = offsets[slug]
            meta["n_samples"] = int(samples.size)
            offsets[slug] += int(samples.size)
            totals["kept"] += 1
            totals["seconds"] += samples.size / OUTPUT_SR
            index.write(json.dumps(meta) + "\n")

    def _per_species(self, index_path):
        per = {}
        with open(index_path) as fh:
            for line in fh:
                meta = json.loads(line)
                slot = per.setdefault(
                    meta["species"], {"bouts": 0, "seconds": 0.0, "groups": set()}
                )
                slot["bouts"] += 1
                slot["seconds"] += meta["n_samples"] / OUTPUT_SR
                slot["groups"].add(meta["group_key"])
        return {
            slug: {
                "bouts": v["bouts"],
                "seconds": round(v["seconds"], 1),
                "groups": len(v["groups"]),
            }
            for slug, v in sorted(per.items())
        }
