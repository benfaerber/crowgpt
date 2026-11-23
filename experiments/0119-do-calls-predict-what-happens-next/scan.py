"""0119 step 1: build deduplicated candidate catalogue and scan 3.0 s BirdNET + envelope windows.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0119-do-calls-predict-what-happens-next/scan.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
DB = DATA_DIR / "corvid.db"
FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"
CACHE = DATA_DIR / "experiments" / "0119-call-consequences"
WINDOWS = CACHE / "windows"
WINDOWS_0112 = DATA_DIR / "experiments" / "0112-representations" / "windows"
EXP102 = REPO / "experiments" / "0102-archive-remarks-semantics"

SR = 22050
WINDOW_S = 3.0
MIN_DUR_S = 24.0
MAX_DUR_S = 300.0
MIN_GENERAL_S = 31.0

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

_ANALYZER = None
_EXP102 = None
_SOS = butter(4, [700.0 / (SR / 2.0), 4500.0 / (SR / 2.0)], btype="band", output="sos")


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resolve_audio_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return path
    if "/data/" in raw:
        candidate = DATA_DIR / raw.split("/data/", 1)[1]
        if candidate.exists():
            return candidate
    return None


def is_american_crow(common: str, scientific: str) -> bool:
    text = f"{common} {scientific}".lower()
    return "american crow" in text or "northwestern crow" in text or "corvus brachyrhynchos" in text


def _header_duration(item: tuple[int, Path]) -> tuple[int, float | None]:
    rid, path = item
    try:
        return rid, float(sf.info(str(path)).duration)
    except Exception:  # noqa: BLE001
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return rid, float(librosa.get_duration(path=str(path)))
        except Exception:  # noqa: BLE001
            return rid, None


def build_catalogue(run_stage) -> list[dict]:
    cat_path = CACHE / "catalogue.json"
    if cat_path.exists():
        return json.loads(cat_path.read_text())

    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = db.execute(
        """
        SELECT id, file_path, content_sha256, group_key, recordist, date
        FROM recordings
        WHERE slug = 'american-crow' AND downloaded = 1 AND analyzed_at IS NOT NULL
        ORDER BY id ASC
        """
    ).fetchall()

    crow_dets: dict[int, int] = defaultdict(int)
    beg_dets: set[int] = set()
    for rid, sp, sci, ct in db.execute(
        """
        SELECT d.recording_id, d.species, d.scientific_name, d.call_type
        FROM detections d
        JOIN recordings r ON r.id = d.recording_id
        WHERE r.slug = 'american-crow' AND r.downloaded = 1 AND r.analyzed_at IS NOT NULL
        """
    ):
        text = f"{sp or ''} {sci or ''}".lower()
        if "crow" in text or "corvus" in text or "raven" in text or "jay" in text or "magpie" in text:
            crow_dets[int(rid)] += 1
            if ct == "begging":
                beg_dets.add(int(rid))

    seen_sha: set[str] = set()
    candidates = []
    for rid, fp, sha, gk, rec, date in rows:
        rid = int(rid)
        if crow_dets[rid] == 0:
            continue
        p = resolve_audio_path(fp)
        if p is None:
            continue
        sha_clean = (sha or "").strip().lower()
        if sha_clean:
            if sha_clean in seen_sha:
                continue
            seen_sha.add(sha_clean)
        observer = (gk or "").strip().lower() or (rec or "").strip().lower() or f"rec:{rid}"
        candidates.append((rid, p, observer, (date or "")[:10], rid in beg_dets))

    run_stage.update(0, len(candidates), extra="checking header durations")
    durs: dict[int, float] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        for idx, (rid, dur) in enumerate(pool.map(_header_duration, [(c[0], c[1]) for c in candidates], chunksize=64), 1):
            if dur is not None:
                durs[rid] = dur
            if idx % 1000 == 0 or idx == len(candidates):
                run_stage.update(idx, len(candidates), extra="header durations")

    catalogue = []
    for rid, p, observer, date_str, has_beg_det in candidates:
        dur = durs.get(rid)
        if dur is None or dur < MIN_DUR_S or dur > MAX_DUR_S:
            continue
        # Files >= 31.0s enter all pools; 24..31s enter if flagged begging in detections
        if dur >= MIN_GENERAL_S or has_beg_det:
            catalogue.append({
                "id": rid,
                "path": str(p),
                "observer": observer,
                "date": date_str,
                "header_duration": round(dur, 3),
                "has_beg_det": bool(has_beg_det),
            })

    CACHE.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps(catalogue, indent=2))
    return catalogue


def _init_worker():
    global _ANALYZER, _EXP102
    from birdnetlib.analyzer import Analyzer

    sys.path.insert(0, str(REPO / "pipelines" / "training"))
    _EXP102 = load_module("exp102_0119", EXP102 / "run.py")
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()


def _compute_envelopes(y: np.ndarray, starts: np.ndarray) -> dict[str, np.ndarray]:
    y = y.astype(np.float32, copy=False)
    y_band = sosfiltfilt(_SOS, y).astype(np.float32)

    hop10 = SR // 100  # 220 samples = 10 ms
    n10 = len(y_band) // hop10
    if n10 >= 10:
        env10 = np.sqrt(np.mean(y_band[: n10 * hop10].reshape(n10, hop10) ** 2, axis=1))
        p10, p98 = float(np.percentile(env10, 10)), float(np.percentile(env10, 98))
        thr = p10 + 0.25 * max(p98 - p10, 1e-8)
        valid_range = (p98 - p10) > 1e-7
    else:
        env10 = np.zeros(0, dtype=np.float32)
        thr = 1.0
        valid_range = False

    hop50 = SR // 20  # 1102 samples = 50 ms
    m = len(starts)
    rms_db = np.zeros(m, dtype=np.float32)
    crow_rms_db = np.zeros(m, dtype=np.float32)
    noise_p10_db = np.zeros(m, dtype=np.float32)
    snr_db = np.zeros(m, dtype=np.float32)
    duty_u = np.zeros(m, dtype=np.float32)
    zero_frac = np.zeros(m, dtype=np.float32)

    for idx, s in enumerate(starts):
        lo = max(0, int(round(float(s) * SR)))
        hi = min(len(y), int(round((float(s) + WINDOW_S) * SR)))
        seg = y[lo:hi]
        seg_b = y_band[lo:hi]
        if len(seg) < SR // 2:
            rms_db[idx] = -120.0
            crow_rms_db[idx] = -120.0
            noise_p10_db[idx] = -120.0
            snr_db[idx] = 0.0
            zero_frac[idx] = 1.0
            continue
        rms_db[idx] = float(20.0 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-7))
        crow_rms_db[idx] = float(20.0 * np.log10(np.sqrt(np.mean(seg_b ** 2)) + 1e-7))
        zero_frac[idx] = float(np.mean(np.abs(seg) < 1e-5))

        n50 = len(seg) // hop50
        if n50 >= 4:
            f50 = np.sqrt(np.mean(seg[: n50 * hop50].reshape(n50, hop50) ** 2, axis=1))
            noise_p10_db[idx] = float(20.0 * np.log10(float(np.percentile(f50, 10)) + 1e-7))
        else:
            noise_p10_db[idx] = rms_db[idx]
        snr_db[idx] = crow_rms_db[idx] - noise_p10_db[idx]

        f0 = int(round(float(s) * 100))
        f1 = min(len(env10), f0 + 300)
        if valid_range and f1 > f0:
            duty_u[idx] = float(np.mean(env10[f0:f1] > thr))

    return {
        "rms_db": rms_db,
        "crow_rms_db": crow_rms_db,
        "noise_p10_db": noise_p10_db,
        "snr_db": snr_db,
        "duty_u": duty_u,
        "zero_frac": zero_frac,
    }


def _reuse_0112(rid: int | str) -> Path | None:
    if isinstance(rid, int):
        for prefix in ("a", "o"):
            cand = WINDOWS_0112 / f"{prefix}{rid}.npz"
            if cand.exists():
                return cand
    return None


def _scan_one(task: tuple[str, int | str, str]) -> tuple[str, str | None]:
    out_name, rid, path_str = task
    out_path = WINDOWS / f"{out_name}.npz"
    if out_path.exists():
        return out_name, None

    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
            y, _ = librosa.load(path_str, sr=SR, mono=True)
    except Exception as exc:  # noqa: BLE001
        return out_name, f"load: {str(exc)[:160]}"

    file_dur = float(len(y) / SR)
    if file_dur < 6.0:
        return out_name, "too short"

    cached = _reuse_0112(rid)
    if cached is not None:
        d = np.load(cached)
        starts = d["start"].astype(np.float32)
        keep = starts + 2.5 <= file_dur + 0.05
        starts = starts[keep]
        corvid = d["corvid"][keep].astype(np.float32)
        am_crow = d["american_crow"][keep].astype(np.float32)
        raptor = d["raptor"][keep].astype(np.float32)
        other = d["other"][keep].astype(np.float32)
        embedding = d["embedding"][keep].astype(np.float32)
    else:
        from birdnetlib import Recording

        try:
            with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                recording = Recording(_ANALYZER, path_str, min_conf=0.05)
                recording.analyze()
                recording.extract_embeddings()
        except Exception as exc:  # noqa: BLE001
            return out_name, f"birdnet: {str(exc)[:160]}"

        scores = defaultdict(lambda: np.zeros(4, dtype=np.float32))
        for det in recording.detections or []:
            w = round(float(det["start_time"]), 2)
            common, scientific = det.get("common_name", ""), det.get("scientific_name", "")
            conf = float(det["confidence"])
            row = scores[w]
            if _EXP102._is_corvid(common, scientific):
                row[0] = max(row[0], conf)
            if is_american_crow(common, scientific):
                row[1] = max(row[1], conf)
            else:
                row[3] = max(row[3], conf)
            if _EXP102._is_raptor(common, scientific):
                row[2] = max(row[2], conf)

        s_list, r_list, e_list = [], [], []
        for segment in recording.embeddings or []:
            emb = np.asarray(segment["embeddings"], dtype=np.float32)
            if not np.isfinite(emb).all():
                continue
            st = round(float(segment["start_time"]), 2)
            if st + 2.5 > file_dur + 0.05:
                continue
            s_list.append(st)
            r_list.append(scores.get(st, np.zeros(4, dtype=np.float32)))
            e_list.append(emb)
        if not s_list:
            return out_name, "no windows"
        starts = np.array(s_list, dtype=np.float32)
        arr = np.array(r_list, dtype=np.float32)
        corvid, am_crow, raptor, other = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
        embedding = np.array(e_list, dtype=np.float32)

    if len(starts) == 0:
        return out_name, "empty starts"

    env = _compute_envelopes(y, starts)
    np.savez(
        out_path,
        file_duration=np.float32(file_dur),
        start=starts,
        corvid=corvid,
        american_crow=am_crow,
        raptor=raptor,
        other=other,
        embedding=embedding,
        **env,
    )
    return out_name, None


def capture_104_task() -> tuple[str, str, str] | None:
    if not FIELD_DB.exists():
        return None
    db = sqlite3.connect(f"file:{FIELD_DB}?mode=ro", uri=True)
    row = db.execute(
        "SELECT m.storage_ref FROM media m WHERE m.capture_id = 104 AND m.kind = 'audio' LIMIT 1"
    ).fetchone()
    if not row or not row[0]:
        return None
    path = FIELD_DB.parent / "media" / row[0]
    if not path.exists():
        return None
    return ("capture_104", "capture_104", str(path))


def main():
    WINDOWS.mkdir(parents=True, exist_ok=True)
    run = Run("0119 window & envelope scan", ["catalogue", "scan"])
    with run.stage("catalogue") as stage:
        catalogue = build_catalogue(stage)

    tasks: list[tuple[str, int | str, str]] = []
    for item in catalogue:
        name = f"r{item['id']}"
        if not (WINDOWS / f"{name}.npz").exists():
            tasks.append((name, int(item["id"]), item["path"]))

    c104 = capture_104_task()
    if c104 is not None and not (WINDOWS / f"{c104[0]}.npz").exists():
        tasks.append(c104)

    print(f"Catalogue size: {len(catalogue)} recordings; to scan: {len(tasks)}")
    failures = {}
    if tasks:
        with run.stage("scan") as stage, ProcessPoolExecutor(max_workers=12, initializer=_init_worker) as pool:
            futures = [pool.submit(_scan_one, t) for t in tasks]
            stage.update(0, len(tasks))
            for done, fut in enumerate(as_completed(futures), 1):
                name, err = fut.result()
                if err:
                    failures[name] = err
                if done % 25 == 0 or done == len(tasks):
                    stage.update(done, len(tasks), extra=f"{len(failures)} failed")
    else:
        with run.stage("scan") as stage:
            stage.update(1, 1, extra="all cached")

    (CACHE / "scan_failures.json").write_text(json.dumps(failures, indent=2))
    run.note(f"catalogue={len(catalogue)}, newly_scanned={len(tasks) - len(failures)}, failed={len(failures)}")
    print(f"Done: {len(tasks) - len(failures)}/{len(tasks)} succeeded, {len(failures)} failed")


if __name__ == "__main__":
    main()
