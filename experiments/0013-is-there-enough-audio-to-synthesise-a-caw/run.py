#!/usr/bin/env python3
"""Is there enough audio here to train something that synthesises a caw?

"CrowGPT" — calls in, a model that generates new ones out. The obvious blocker
is the 35 human labels on the field server, but that blocker is imaginary: a
generative audio model does not need labels, and the ones it would be
conditioned on can be produced by the call-type heads that already ship. So the
question is not how many labels exist. It is how many seconds of *crow*, cut
into discrete call units, can be recovered from the corpus without asking a
human for anything.

    ../../pipelines/representation/.venv-birdnet/bin/python run.py

That number is what a generative model consumes, and nothing in the project has
ever measured it. `data/species` is 11 GB, which sounds like plenty, but it is
whole archive recordings — wind, other species, recordists talking — and the
fraction that is actually a corvid vocalising has only ever been guessed at.

Six things get measured, and D is the one that decides it:

  A. inventory     — hours, encoding, sample rates; the ceiling on everything
  B. crow fraction — BirdNET over the *whole* corpus at the pipeline's own
                     thresholds: what share of the grid is corvid at all
  C. contamination — what else is in those same windows, which bounds what an
                     unconditioned generator would reproduce
  D. call units    — energy bursts in the crow band inside corvid windows:
                     how many discrete calls, and how long each one is
  E. control       — the same burst detector on windows BirdNET says hold no
                     bird. If it fires as often there, D is counting noise
  F. the 3s grid   — how many calls sit inside one human-labelled window, i.e.
                     how far the existing labels are from a call boundary

BirdNET runs ~40x realtime, so this reads every file rather than a sample. It
takes roughly half an hour; progress is printed as it goes.

Set SAMPLE_PER_SPECIES to cap files per species for a fast re-run.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy.signal import stft

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

sys.path.insert(0, str(REPO / "experiments"))
from lib.media import media_dir  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
SPECIES_DIR = DATA / "species"
CROW_DB = DATA / "corvid.db"
FIELD_DB = Path(os.environ.get("FIELD_DB", REPO / "fieldserver" / "instance" / "field.db"))

# The analyzer's own numbers, imported rather than restated. A crow fraction
# measured at a threshold the pipeline does not use would answer a question
# nobody asked.
sys.path.insert(0, str(REPO / "analyzer"))
_ANALYZER_CONSTANTS = None


def constants():
    """CROW_TERMS / thresholds from analyzer/birdnet.py, loaded once.

    Importing that module builds an Analyzer and every call-type head, which is
    wasted work in a worker that only needs six strings and two floats — so it
    is read in the parent and passed down.
    """
    global _ANALYZER_CONSTANTS
    if _ANALYZER_CONSTANTS is None:
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            import birdnet
        _ANALYZER_CONSTANTS = {
            "CROW_TERMS": birdnet.CROW_TERMS,
            "CROW_MIN_CONF": birdnet.CROW_MIN_CONF,
            "CANDIDATE_MIN_CONF": birdnet.CANDIDATE_MIN_CONF,
            "WINDOW_SEC": birdnet.WINDOW_SEC,
        }
    return _ANALYZER_CONSTANTS


# Set once per worker by init(), so the constants cross the process boundary as
# plain data instead of dragging the analyzer's imports into every child.
CONF: dict = {}
ANALYZER = None

ANALYSIS_SR = 32000        # Nyquist 16 kHz — above anything a corvid puts out
BAND = (800, 4000)         # the band experiment 0004 used for call SNR
NPERSEG, NOVERLAP = 512, 256   # 16 ms hop: fine for calls of 100-500 ms
FLOOR_PCTL = 20            # "quiet in this recording", per recording
BURST_DB = 8.0             # how far above that floor counts as a call
UNIT_MIN_SEC = 0.06        # shorter than this is a click, not a caw
UNIT_GAP_SEC = 0.08        # two bursts closer than this are one call
ROLLOFF = 0.95             # spectral rolloff reported per unit

# A burst detector that fires as often on silence as on a crow is a noise
# counter, and every number in D would be worthless. One binary control is not
# enough to tell those apart, because BirdNET's own misses land in the negative
# class — birdnet.py records a real alarm call at 0.183 and a begging fledgling
# at 0.06, so "no detection" windows genuinely contain calls.
#
# So the control is a gradient instead: density and duty cycle per confidence
# band. If they rise with BirdNET's confidence the detector is tracking calls; if
# they are flat it is tracking room tone. And because the whole thing hangs on
# one arbitrary dB threshold, every band is measured at three of them.
CONF_EDGES = (0.0, 0.10, 0.25, 0.50, 0.75, 1.01)
BURST_DB_SWEEP = (6.0, 8.0, 12.0)


def conf_band(conf: float) -> str:
    for lo, hi in zip(CONF_EDGES, CONF_EDGES[1:]):
        if lo <= conf < hi:
            return f"{lo:.2f}-{hi if hi <= 1 else 1.0:.2f}"
    return f"{CONF_EDGES[-2]:.2f}-1.00"


def note(line: str, append: bool = True) -> None:
    print(line, flush=True)


def probe(path: Path):
    """Duration, sample rate and codec, straight from the container."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=sample_rate,codec_name:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        meta = json.loads(out.stdout)
        stream = (meta.get("streams") or [{}])[0]
        return {
            "duration": float(meta.get("format", {}).get("duration") or 0.0),
            "sample_rate": int(stream.get("sample_rate") or 0),
            "codec": stream.get("codec_name") or "?",
        }
    except Exception:
        return None


def corpus_files():
    """Every corpus recording, per species, plus the field captures.

    American Crow is the one species whose audio does not live under
    data/species — the Phase 1 corpus put it in data/audio and recorded the join
    in corvid.db — so it is resolved through the database like everything else
    rather than by guessing at filenames.
    """
    groups: dict[str, list[Path]] = {}
    cap = int(os.environ.get("SAMPLE_PER_SPECIES", "0")) or None

    for manifest in sorted(SPECIES_DIR.glob("*/manifest.json")):
        recs = json.loads(manifest.read_text()).get("recordings", [])
        paths = [Path(r["path"]) for r in recs if r.get("path")]
        # manifest paths were written absolute on another checkout; re-root them
        paths = [p if p.exists() else manifest.parent / "audio" / p.name for p in paths]
        paths = [p for p in paths if p.exists()]
        if paths:
            groups[manifest.parent.name] = paths[:cap]

    if CROW_DB.exists():
        # EACH ROW UNDER ITS OWN SPECIES. This appended every downloaded
        # file_path to american-crow, whatever bird it was. That was right
        # while the corpus held only American Crow; the 2026-08-05 sweep put 48
        # species in the database, so it filed thousands of hooded crows,
        # ravens and jackdaws under the one species this experiment is about —
        # and counted the 2,382 recordings held in BOTH stores twice. Both
        # errors inflate the very number the experiment reports.
        with sqlite3.connect(str(CROW_DB)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT file_path, slug, species FROM recordings "
                "WHERE downloaded = 1 AND file_path IS NOT NULL"
            ).fetchall()
        seen = {p.resolve() for paths in groups.values() for p in paths}
        for row in rows:
            p = Path(row["file_path"])
            if not p.exists():
                p = DATA / "audio" / p.name
            if not p.exists():
                continue
            # A duplicate is the SAME RECORDING in the other store, and the
            # manifest copy is already counted above.
            resolved = p.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            slug = row["slug"] or "unknown"
            groups.setdefault(slug, []).append(p)
        if cap:
            groups = {s: v[:cap] for s, v in groups.items()}

    return groups


def field_captures():
    """Field captures with their keep flag, so real recordings can be counted
    apart from the seeded archive clips and test uploads."""
    if not FIELD_DB.exists():
        return []
    with sqlite3.connect(str(FIELD_DB)) as conn:
        rows = conn.execute(
            "SELECT c.id, c.keep, c.duration_sec, m.storage_ref FROM captures c "
            "JOIN media m ON m.capture_id = c.id AND m.kind = 'audio' "
            "AND m.upload_state = 'complete'"
        ).fetchall()
    out = []
    for cid, keep, dur, ref in rows:
        path = media_dir() / ref
        if path.exists():
            out.append({"id": cid, "keep": bool(keep), "duration": dur or 0.0, "path": path})
    return out


def init(conf: dict) -> None:
    global ANALYZER, CONF
    CONF = conf
    from birdnetlib.analyzer import Analyzer
    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        ANALYZER = Analyzer()


def detect(path: Path):
    """BirdNET at the candidate floor, so both tiers come back in one pass."""
    from birdnetlib import Recording
    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        rec = Recording(ANALYZER, str(path), min_conf=CONF["CANDIDATE_MIN_CONF"])
        rec.analyze()
    return rec.detections


def envelope(y, sr):
    """Band energy per frame, in dB, plus the frame rate and the FFT bins.

    The envelope is the whole measurement in D and E: a call is a burst of
    energy in the band a corvid uses, and everything else is the floor it has to
    stand above.
    """
    freqs, _, Z = stft(y, fs=sr, nperseg=NPERSEG, noverlap=NOVERLAP)
    mag = np.abs(Z)
    band = (freqs >= BAND[0]) & (freqs <= BAND[1])
    energy = np.sqrt(np.mean(mag[band] ** 2, axis=0))
    db = 20 * np.log10(np.maximum(energy, 1e-12))
    fps = sr / (NPERSEG - NOVERLAP)
    return db, fps, freqs, mag


def bursts(db, fps, floor_db, thresh_db=BURST_DB):
    """Contiguous runs above the floor, merged across short gaps.

    Returns (start_frame, end_frame) pairs. The gap merge is what makes a unit a
    call rather than a syllable: a caw is not one smooth envelope, and splitting
    on every dip would count the same call three times.
    """
    hot = db > floor_db + thresh_db
    if not hot.any():
        return []
    starts = list(np.flatnonzero(np.diff(np.concatenate(([0], hot.astype(np.int8)))) == 1))
    ends = list(np.flatnonzero(np.diff(np.concatenate((hot.astype(np.int8), [0]))) == -1) + 1)

    gap_frames = UNIT_GAP_SEC * fps
    merged: list[list[int]] = []
    for s, e in zip(starts, ends):
        if merged and s - merged[-1][1] <= gap_frames:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    min_frames = UNIT_MIN_SEC * fps
    return [(s, e) for s, e in merged if e - s >= min_frames]


def rolloff_hz(mag, freqs, s, e):
    """Frequency below which ROLLOFF of a unit's energy sits.

    This decides whether the lossy half of the corpus matters. If units roll off
    well under 16 kHz then an mp3 lowpass is irrelevant and a generative model
    can be trained at 16 or 22 kHz without throwing anything away.
    """
    spec = np.mean(mag[:, s:e] ** 2, axis=1)
    total = spec.sum()
    if total <= 0:
        return None
    return float(freqs[np.searchsorted(np.cumsum(spec) / total, ROLLOFF)])


def analyse(item):
    """One recording: detections, window classes, and the units inside them.

    Returns summary counts and the per-unit durations, never audio — the point
    is to reduce 40 hours to a few thousand numbers.
    """
    path, species = Path(item[0]), item[1]
    meta = probe(path)
    if not meta or meta["duration"] <= 0:
        return {"path": str(path), "species": species, "error": "unreadable"}

    try:
        detections = detect(path)
    except Exception as exc:
        return {"path": str(path), "species": species, "error": f"birdnet: {exc}"}

    win = CONF["WINDOW_SEC"]
    n_windows = max(1, int(meta["duration"] // win))
    crow_conf = np.zeros(n_windows)
    others: Counter = Counter()
    other_windows = np.zeros(n_windows, dtype=bool)

    for d in detections:
        w = int(d["start_time"] // win)
        if not 0 <= w < n_windows:
            continue
        name = d["common_name"].lower()
        if any(term in name for term in CONF["CROW_TERMS"]):
            crow_conf[w] = max(crow_conf[w], d["confidence"])
        else:
            others[d["common_name"]] += 1
            other_windows[w] = True

    is_crow = crow_conf >= CONF["CROW_MIN_CONF"]
    is_candidate = (crow_conf >= CONF["CANDIDATE_MIN_CONF"]) & ~is_crow
    is_empty = (crow_conf < CONF["CANDIDATE_MIN_CONF"]) & ~other_windows

    try:
        import librosa
        y, sr = librosa.load(str(path), sr=ANALYSIS_SR, mono=True)
    except Exception as exc:
        return {"path": str(path), "species": species, "error": f"load: {exc}"}
    if y.size < NPERSEG * 4:
        return {"path": str(path), "species": species, "error": "too short"}

    db, fps, freqs, mag = envelope(y, sr)
    floor_db = float(np.percentile(db, FLOOR_PCTL))

    # windows per confidence band, so the gradient has a denominator
    band_windows: Counter = Counter()
    for w in range(n_windows):
        band_windows[conf_band(crow_conf[w])] += 1

    # (threshold, band) -> [units, seconds], the control in E
    gradient: dict[str, dict[str, list]] = {}
    for thresh in BURST_DB_SWEEP:
        acc: dict[str, list] = defaultdict(lambda: [0, 0.0])
        for s, e in bursts(db, fps, floor_db, thresh):
            w = int(((s + e) / 2 / fps) // win)
            if not 0 <= w < n_windows:
                continue
            cell = acc[conf_band(crow_conf[w])]
            cell[0] += 1
            cell[1] += (e - s) / fps
        gradient[f"{thresh:g}"] = {k: [v[0], round(v[1], 2)] for k, v in acc.items()}

    crow_units, empty_units, rolloffs = [], [], []
    for s, e in bursts(db, fps, floor_db, BURST_DB):
        centre_sec = (s + e) / 2 / fps
        w = int(centre_sec // win)
        if not 0 <= w < n_windows:
            continue
        dur = (e - s) / fps
        if is_crow[w]:
            crow_units.append(dur)
            r = rolloff_hz(mag, freqs, s, e)
            if r is not None:
                rolloffs.append(r)
        elif is_empty[w]:
            empty_units.append(dur)

    return {
        "band_windows": dict(band_windows),
        "gradient": gradient,
        "path": str(path),
        "species": species,
        "duration": meta["duration"],
        "sample_rate": meta["sample_rate"],
        "codec": meta["codec"],
        "n_windows": n_windows,
        "crow_windows": int(is_crow.sum()),
        "candidate_windows": int(is_candidate.sum()),
        "empty_windows": int(is_empty.sum()),
        "max_crow_conf": float(crow_conf.max()),
        "others": dict(others),
        "crow_unit_durations": [round(d, 3) for d in crow_units],
        "empty_unit_durations": [round(d, 3) for d in empty_units],
        "rolloffs": [round(r, 1) for r in rolloffs],
    }


def pct(values, q):
    return round(float(np.percentile(values, q)), 3) if len(values) else None


def gradient_table(ok, win):
    """E. Burst density and duty cycle per confidence band, at each threshold.

    Read down a column: if density climbs from the 0.00-0.10 band to the
    0.75-1.00 one, the burst detector is finding calls rather than background,
    and it climbs for the same reason BirdNET's confidence does. Read across the
    rows to see how much of that is the dB threshold's doing.
    """
    windows: Counter = Counter()
    for r in ok:
        windows.update(r.get("band_windows", {}))

    bands = [f"{lo:.2f}-{min(hi, 1.0):.2f}" for lo, hi in zip(CONF_EDGES, CONF_EDGES[1:])]
    table = {}
    for thresh in BURST_DB_SWEEP:
        key = f"{thresh:g}"
        acc: dict[str, list] = {b: [0, 0.0] for b in bands}
        for r in ok:
            for band, (n, secs) in r.get("gradient", {}).get(key, {}).items():
                if band in acc:
                    acc[band][0] += n
                    acc[band][1] += secs
        table[key] = {
            band: {
                "windows": windows.get(band, 0),
                "units": acc[band][0],
                "per_window": (
                    round(acc[band][0] / windows[band], 2) if windows.get(band) else None
                ),
                "duty_cycle": (
                    round(acc[band][1] / (windows[band] * win), 3)
                    if windows.get(band) else None
                ),
            }
            for band in bands
        }
    return {"bands": bands, "by_threshold": table}


def summarise(results, groups):
    """Fold the per-file rows into the numbers the README quotes."""
    ok = [r for r in results if not r.get("error")]
    errors = [r for r in results if r.get("error")]

    win = constants()["WINDOW_SEC"]
    per_species = {}
    for species in sorted(groups):
        rows = [r for r in ok if r["species"] == species]
        if not rows:
            continue
        hours = sum(r["duration"] for r in rows) / 3600
        crow_w = sum(r["crow_windows"] for r in rows)
        cand_w = sum(r["candidate_windows"] for r in rows)
        total_w = sum(r["n_windows"] for r in rows)
        units = [d for r in rows for d in r["crow_unit_durations"]]
        per_species[species] = {
            "files": len(rows),
            "hours": round(hours, 2),
            "windows": total_w,
            "crow_windows": crow_w,
            "candidate_windows": cand_w,
            "crow_share": round(crow_w / total_w, 3) if total_w else None,
            "crow_hours": round(crow_w * win / 3600, 2),
            "units": len(units),
            "unit_seconds": round(sum(units), 1),
            "median_unit_sec": pct(units, 50),
            "files_with_no_crow": sum(1 for r in rows if r["crow_windows"] == 0),
        }

    crow_units = [d for r in ok for d in r["crow_unit_durations"]]
    empty_units = [d for r in ok for d in r["empty_unit_durations"]]
    crow_w = sum(r["crow_windows"] for r in ok)
    empty_w = sum(r["empty_windows"] for r in ok)
    rolloffs = [x for r in ok for x in r["rolloffs"]]

    others: Counter = Counter()
    for r in ok:
        others.update(r["others"])

    codecs: Counter = Counter()
    lossless_hours = lossy_hours = 0.0
    rates: Counter = Counter()
    for r in ok:
        codecs[r["codec"]] += 1
        rates[r["sample_rate"]] += 1
        if r["codec"].startswith("pcm") or r["codec"] in ("flac", "alac"):
            lossless_hours += r["duration"] / 3600
        else:
            lossy_hours += r["duration"] / 3600

    return {
        "files_read": len(ok),
        "files_failed": len(errors),
        "errors": errors[:20],
        "total_hours": round(sum(r["duration"] for r in ok) / 3600, 2),
        "lossless_hours": round(lossless_hours, 2),
        "lossy_hours": round(lossy_hours, 2),
        "codecs": dict(codecs.most_common()),
        "sample_rates": dict(sorted(rates.items())),
        "per_species": per_species,
        "crow": {
            "windows": crow_w,
            "hours": round(crow_w * constants()["WINDOW_SEC"] / 3600, 2),
            "share_of_grid": round(crow_w / sum(r["n_windows"] for r in ok), 3) if ok else None,
            "candidate_windows": sum(r["candidate_windows"] for r in ok),
        },
        "units": {
            "n": len(crow_units),
            "seconds": round(sum(crow_units), 1),
            "hours": round(sum(crow_units) / 3600, 2),
            "per_crow_window": round(len(crow_units) / crow_w, 2) if crow_w else None,
            "p10": pct(crow_units, 10),
            "median": pct(crow_units, 50),
            "p90": pct(crow_units, 90),
            "duty_cycle_in_crow_windows": (
                round(sum(crow_units) / (crow_w * constants()["WINDOW_SEC"]), 3)
                if crow_w else None
            ),
        },
        "control_empty_windows": {
            "windows": empty_w,
            "units": len(empty_units),
            "per_window": round(len(empty_units) / empty_w, 2) if empty_w else None,
            "median": pct(empty_units, 50),
        },
        "control_gradient": gradient_table(ok, win),
        "bandwidth": {
            "n_units": len(rolloffs),
            "rolloff_p50_hz": pct(rolloffs, 50),
            "rolloff_p90_hz": pct(rolloffs, 90),
            "rolloff_p99_hz": pct(rolloffs, 99),
            "share_under_8k": (
                round(float(np.mean(np.array(rolloffs) < 8000)), 3) if rolloffs else None
            ),
        },
        "contamination": {
            "distinct_non_corvid_species": len(others),
            "top": others.most_common(15),
        },
    }


def label_grid():
    """F. How many call units sit inside one human-labelled window?

    Every label on the field server is on the 3-second BirdNET grid — checked,
    not assumed: the run stops if one is not. A synthesiser needs a call, not a
    window containing some, so this counts how far apart those two things are.
    """
    if not FIELD_DB.exists():
        return {"error": f"no field db at {FIELD_DB}"}
    with sqlite3.connect(str(FIELD_DB)) as conn:
        rows = conn.execute(
            "SELECT l.capture_id, l.start_sec, l.end_sec, l.call_type, m.storage_ref "
            "FROM labels l JOIN media m ON m.capture_id = l.capture_id "
            "AND m.kind = 'audio' AND m.upload_state = 'complete' "
            "ORDER BY l.capture_id, l.start_sec"
        ).fetchall()
    if not rows:
        return {"error": "no labels"}

    off_grid = [
        (c, s, e) for c, s, e, _, _ in rows
        if s is None or e is None or s % 3 or (e - s) % 3
    ]

    by_capture: dict[str, list] = defaultdict(list)
    for cid, s, e, call_type, ref in rows:
        by_capture[ref].append((cid, s, e, call_type))

    import librosa
    per_label, spans = [], []
    for ref, labels in by_capture.items():
        path = media_dir() / ref
        if not path.exists():
            continue
        try:
            y, sr = librosa.load(str(path), sr=ANALYSIS_SR, mono=True)
        except Exception:
            continue
        db, fps, freqs, mag = envelope(y, sr)
        floor_db = float(np.percentile(db, FLOOR_PCTL))
        found = bursts(db, fps, floor_db)
        for cid, s, e, call_type in labels:
            if s is None or e is None:
                continue
            inside = [
                (b - a) / fps for a, b in found
                if s <= ((a + b) / 2 / fps) < e
            ]
            per_label.append({
                "capture": cid, "start": s, "end": e, "call_type": call_type,
                "span_sec": round(e - s, 1), "units": len(inside),
                "unit_seconds": round(sum(inside), 2),
            })
            spans.append(e - s)

    counts = [p["units"] for p in per_label]
    return {
        "labels": len(rows),
        "labels_measured": len(per_label),
        "off_grid": off_grid,
        "all_on_3s_grid": not off_grid,
        "label_span_seconds": round(float(np.sum(spans)), 1) if spans else 0.0,
        "units_found": int(np.sum(counts)) if counts else 0,
        "units_per_label_median": pct(counts, 50),
        "units_per_label_max": int(max(counts)) if counts else 0,
        "single_unit_labels": sum(1 for c in counts if c == 1),
        "multi_unit_labels": sum(1 for c in counts if c > 1),
        "empty_labels": sum(1 for c in counts if c == 0),
        "call_seconds_inside_labels": round(sum(p["unit_seconds"] for p in per_label), 1),
        "per_label": per_label,
    }


def also_field():
    """The archive's own 'also' list for American Crow: species the recordist
    said are audible. Independent of BirdNET, so it is a cross-check on C."""
    if not CROW_DB.exists():
        return {"error": "no corvid.db"}
    with sqlite3.connect(str(CROW_DB)) as conn:
        rows = conn.execute("SELECT raw FROM recordings WHERE downloaded = 1").fetchall()
    with_also = 0
    names: Counter = Counter()
    for (raw,) in rows:
        try:
            also = [a for a in (json.loads(raw or "{}").get("also") or []) if a.strip()]
        except Exception:
            continue
        if also:
            with_also += 1
            names.update(also)
    return {
        "recordings": len(rows),
        "with_other_species": with_also,
        "share": round(with_also / len(rows), 3) if rows else None,
        "distinct": len(names),
        "top": names.most_common(10),
    }


def field_inventory(captures):
    kept = [c for c in captures if c["keep"]]
    return {
        "captures_with_audio": len(captures),
        "kept": len(kept),
        "kept_minutes": round(sum(c["duration"] for c in kept) / 60, 1),
        "unkept_minutes": round(sum(c["duration"] for c in captures if not c["keep"]) / 60, 1),
    }


def main() -> int:
    note(f"0013 — is there enough audio to synthesise a caw ({time.strftime('%H:%M:%S')})",
         append=False)

    groups = corpus_files()
    if not groups:
        raise SystemExit(f"no audio found under {SPECIES_DIR} — set DATA_DIR?")
    items = [(str(p), sp) for sp, paths in groups.items() for p in paths]
    note(f"A. {len(items)} recordings across {len(groups)} species")

    captures = field_captures()
    field = field_inventory(captures)
    note(f"   field: {field['kept']} kept captures, {field['kept_minutes']} min real audio")

    workers = min(12, max(1, (os.cpu_count() or 4) - 2))
    note(f"B-E. BirdNET + burst detection over all of it, {workers} workers")

    results = []
    started = time.time()
    with ProcessPoolExecutor(workers, initializer=init, initargs=(constants(),)) as pool:
        for i, row in enumerate(pool.map(analyse, items, chunksize=4), 1):
            results.append(row)
            if i % 100 == 0 or i == len(items):
                done_h = sum(r.get("duration", 0) for r in results) / 3600
                rate = i / max(1e-9, time.time() - started)
                note(f"   {i}/{len(items)} files · {done_h:.1f} h read · "
                     f"{rate * 60:.0f} files/min · eta {(len(items) - i) / rate / 60:.0f} min")

    summary = summarise(results, groups)
    note(f"F. the 3-second grid, against the field server's labels")
    summary["field"] = field
    summary["label_grid"] = label_grid()
    summary["archive_also"] = also_field()

    (HERE / "results.json").write_text(json.dumps(summary, indent=2))

    u, c, b = summary["units"], summary["crow"], summary["bandwidth"]
    ctl, lg = summary["control_empty_windows"], summary["label_grid"]

    print(f"\nA. inventory — {summary['total_hours']} h over {summary['files_read']} files "
          f"({summary['files_failed']} unreadable)")
    print(f"   lossless {summary['lossless_hours']} h · lossy {summary['lossy_hours']} h")
    print(f"   field: {field['kept']} kept captures = {field['kept_minutes']} min\n")

    print(f"   {'species':<20}{'files':>6}{'hours':>8}{'crow%':>7}{'crow h':>8}{'units':>8}{'no crow':>9}")
    for sp, row in summary["per_species"].items():
        print(f"   {sp:<20}{row['files']:>6}{row['hours']:>8.2f}"
              f"{row['crow_share'] * 100 if row['crow_share'] is not None else 0:>6.0f}%"
              f"{row['crow_hours']:>8.2f}{row['units']:>8}{row['files_with_no_crow']:>9}")

    print(f"\nB. corvid windows   {c['windows']} of grid ({c['share_of_grid']:.1%}) = {c['hours']} h")
    print(f"   candidates       {c['candidate_windows']} more windows in the 0.10-0.25 band")

    print(f"\nC. contamination    {summary['contamination']['distinct_non_corvid_species']} "
          f"distinct non-corvid species detected")
    for name, n in summary["contamination"]["top"][:6]:
        print(f"     {name:<34}{n:>7}")
    also = summary["archive_also"]
    if not also.get("error"):
        print(f"   archive 'also' agrees: {also['share']:.0%} of American Crow "
              f"recordings list another species")

    print(f"\nD. call units       {u['n']} units, {u['seconds']} s total ({u['hours']} h)")
    print(f"   duration         p10 {u['p10']}s · median {u['median']}s · p90 {u['p90']}s")
    print(f"   density          {u['per_crow_window']} per corvid window · "
          f"duty cycle {u['duty_cycle_in_crow_windows']:.1%}")

    print(f"\nE. control — does the burst detector track BirdNET's confidence?")
    grad = summary["control_gradient"]
    print(f"   {'crow conf':<14}{'windows':>9}" +
          "".join(f"{'  ' + t + ' dB':>16}" for t in grad["by_threshold"]))
    print(f"   {'':<14}{'':>9}" +
          "".join(f"{'per win':>8}{'duty':>8}" for _ in grad["by_threshold"]))
    for band in grad["bands"]:
        first = next(iter(grad["by_threshold"].values()))[band]
        line = f"   {band:<14}{first['windows']:>9}"
        for t in grad["by_threshold"]:
            cell = grad["by_threshold"][t][band]
            pw = "—" if cell["per_window"] is None else f"{cell['per_window']:.2f}"
            dc = "—" if cell["duty_cycle"] is None else f"{cell['duty_cycle']:.0%}"
            line += f"{pw:>8}{dc:>8}"
        print(line)
    print(f"   strict 'empty' windows: {ctl['per_window']} units/window "
          f"vs {u['per_crow_window']} in corvid windows")

    print(f"\n   bandwidth       rolloff median {b['rolloff_p50_hz']} Hz · "
          f"p99 {b['rolloff_p99_hz']} Hz · {b['share_under_8k']:.1%} under 8 kHz")

    if not lg.get("error"):
        print(f"\nF. the 3s grid     all {lg['labels']} labels on the grid: {lg['all_on_3s_grid']}")
        print(f"   {lg['label_span_seconds']}s of label spans hold {lg['units_found']} call units "
              f"(median {lg['units_per_label_median']} per label, max {lg['units_per_label_max']})")
        print(f"   single-call labels {lg['single_unit_labels']} · "
              f"multi-call {lg['multi_unit_labels']} · empty {lg['empty_labels']}")
        print(f"   actual call audio inside every human label: "
              f"{lg['call_seconds_inside_labels']}s")

    note(f"\nwrote {HERE / 'results.json'} ({time.strftime('%H:%M:%S')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
