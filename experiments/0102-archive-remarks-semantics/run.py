"""Experiment 0102 — Archive remarks semantic harvest & acoustic separability.

Questions:
1. How many witnessed semantic-context recordings (predator mobbing by trigger
   species, begging, foraging, close social/rattle, roosting, agonistic) are
   already sitting inside Xeno-canto and Macaulay Library free-text remarks in
   data/corvid.db?
2. On strictly recordist-grouped cross-validation — and after masking out every
   window/recording where BirdNET hears a raptor or owl itself — can BirdNET
   embeddings or interpretable prosodic features separate:
     (a) multi-class witnessed semantic contexts on American Crow;
     (b) witnessed owl mobbing vs. witnessed hawk mobbing (referential predator
         alarm);
     (c) aerial predator mobbing (owl/hawk) vs. mammal scolding across Corvus?

Runs in the BirdNET venv on CPU (zero GPU):
  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0102-archive-remarks-semantics/run.py --workers 8
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sqlite3
import sys
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import librosa
import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
DB_PATH = DATA_DIR / "corvid.db"
LABELS_PATH = HERE / "labels.json"
CACHE_DIR = DATA_DIR / "experiments" / "0102-archive-remarks"
CACHE_META = CACHE_DIR / "records.json"
CACHE_NPZ = CACHE_DIR / "features.npz"

sys.path.insert(0, str(REPO / "pipelines" / "training"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from pooling import pool  # noqa: E402
from crowgpt.progress import Run  # noqa: E402

CORVID_TERMS = (
    "crow", "raven", "rook", "jackdaw", "magpie", "corvus", "coloeus", "pica",
)
RAPTOR_TERMS = (
    "owl", "hawk", "eagle", "falcon", "kestrel", "osprey", "harrier",
    "buzzard", "goshawk", "sparrowhawk", "kite", "merlin", "vulture",
    "bubo", "strix", "asio", "tyto", "buteo", "accipiter", "falco",
    "haliaeetus", "aquila", "pandion", "circus", "milvus", "astur",
)

PROSODY_NAMES = [
    "duration_s",
    "crow_frac",
    "band_rms_mean",
    "band_rms_std",
    "band_rms_p90_p50",
    "duty_cycle",
    "onset_rate_hz",
    "centroid_hz_mean",
    "centroid_hz_std",
    "bandwidth_hz_mean",
    "flatness_mean",
    "flatness_std",
    "zcr_mean",
    "rolloff_hz_mean",
    "low_mid_ratio",
    *[f"mfcc_mean_{i}" for i in range(13)],
    *[f"mfcc_std_{i}" for i in range(13)],
]

_WORKER_ANALYZER = None
_DEVNULL = None


def _init_worker():
    global _WORKER_ANALYZER, _DEVNULL
    _DEVNULL = open(os.devnull, "w")
    from birdnetlib.analyzer import Analyzer

    with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
        _WORKER_ANALYZER = Analyzer()


def resolve_audio_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    p = Path(raw_path)
    if p.exists():
        return p
    # Handle recordings indexed before the repo directory was renamed.
    marker = "/data/"
    if marker in raw_path:
        rel = raw_path.split(marker, 1)[1]
        cand = DATA_DIR / rel
        if cand.exists():
            return cand
    return None


def _is_corvid(common: str, sci: str) -> bool:
    s = f"{common} {sci}".lower()
    return any(t in s for t in CORVID_TERMS)


def _is_raptor(common: str, sci: str) -> bool:
    s = f"{common} {sci}".lower()
    return any(t in s for t in RAPTOR_TERMS)


def extract_prosody(y: np.ndarray, sr: int, active_windows: list[tuple[float, float]]) -> np.ndarray:
    """Compute interpretable crow-band (600-4500 Hz) prosodic & spectral features."""
    if len(y) == 0:
        return np.zeros(len(PROSODY_NAMES), dtype=np.float32)

    dur = len(y) / sr
    if active_windows:
        chunks = []
        for s, e in active_windows:
            i0 = max(0, int(s * sr))
            i1 = min(len(y), int(e * sr))
            if i1 - i0 >= int(0.5 * sr):
                chunks.append(y[i0:i1])
        seg_y = np.concatenate(chunks) if chunks else y
        crow_frac = min(1.0, (len(seg_y) / sr) / max(dur, 1e-6))
    else:
        seg_y = y
        crow_frac = 0.0

    # Cap to 60 s of active crow audio for speed and consistency.
    max_len = 60 * sr
    if len(seg_y) > max_len:
        seg_y = seg_y[:max_len]

    hop = 512
    n_fft = 1024
    S = np.abs(librosa.stft(seg_y, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= 600) & (freqs <= 4500)
    low_band = (freqs >= 600) & (freqs < 1800)
    mid_band = (freqs >= 1800) & (freqs <= 4500)

    S_band = S[band, :]
    band_rms = np.sqrt(np.mean(S_band ** 2, axis=0) + 1e-12)
    p50 = float(np.percentile(band_rms, 50))
    p90 = float(np.percentile(band_rms, 90))
    p20 = float(np.percentile(band_rms, 20))
    # Adaptive activity threshold above quiet floor.
    thresh = max(p20 * 2.5, float(np.mean(band_rms)) * 0.8)
    duty_cycle = float(np.mean(band_rms > thresh))

    # Onset rate (proxy for caw repetition tempo) inside active audio.
    onset_env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S_band + 1e-8), sr=sr, hop_length=hop)
    onsets = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=hop, wait=int(0.18 * sr / hop), backtrack=False,
    )
    onset_rate = float(len(onsets) / max(len(seg_y) / sr, 1e-3))

    # Spectral stats weighted to active frames where band_rms > p50.
    act = band_rms >= p50
    if not np.any(act):
        act = np.ones_like(band_rms, dtype=bool)
    S_act = S[:, act]

    centroid = librosa.feature.spectral_centroid(S=S_act, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=S_act, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=S_band[:, act] + 1e-10)[0]
    rolloff = librosa.feature.spectral_rolloff(S=S_act, sr=sr)[0]
    zcr = librosa.feature.zero_crossing_rate(seg_y, frame_length=n_fft, hop_length=hop)[0]
    low_e = float(np.mean(S[low_band, :][:, act] ** 2))
    mid_e = float(np.mean(S[mid_band, :][:, act] ** 2))
    low_mid_ratio = float(np.log((low_e + 1e-10) / (mid_e + 1e-10)))

    mfccs = librosa.feature.mfcc(y=seg_y, sr=sr, n_mfcc=13, fmin=500, fmax=6000)
    mfcc_mean = np.mean(mfccs, axis=1)
    mfcc_std = np.std(mfccs, axis=1)

    vec = np.array([
        dur,
        crow_frac,
        float(np.mean(band_rms)),
        float(np.std(band_rms)),
        float(p90 / max(p50, 1e-8)),
        duty_cycle,
        onset_rate,
        float(np.mean(centroid)),
        float(np.std(centroid)),
        float(np.mean(bandwidth)),
        float(np.mean(flatness)),
        float(np.std(flatness)),
        float(np.mean(zcr)),
        float(np.mean(rolloff)),
        low_mid_ratio,
        *mfcc_mean.tolist(),
        *mfcc_std.tolist(),
    ], dtype=np.float32)
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def process_one(task: tuple[int, str, str]) -> dict:
    """Run BirdNET detections + embeddings + prosodic features on one file."""
    rec_id, audio_path, slug = task
    from birdnetlib import Recording

    try:
        with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
            rec = Recording(_WORKER_ANALYZER, audio_path, min_conf=0.05)
            rec.analyze()
            rec.extract_embeddings()
    except Exception as ex:  # noqa: BLE001
        return {"id": rec_id, "ok": False, "error": str(ex)}

    segs = rec.embeddings or []
    if not segs:
        return {"id": rec_id, "ok": False, "error": "no embeddings"}

    # Map detections per 3s window keyed by (start, end).
    win_crow: dict[tuple[float, float], float] = defaultdict(float)
    win_raptor: dict[tuple[float, float], float] = defaultdict(float)
    raptor_species = set()
    max_raptor_conf = 0.0
    max_crow_conf = 0.0

    for det in rec.detections or []:
        key = (round(float(det["start_time"]), 2), round(float(det["end_time"]), 2))
        c = float(det["confidence"])
        cname = det.get("common_name", "")
        sname = det.get("scientific_name", "")
        if _is_corvid(cname, sname):
            win_crow[key] = max(win_crow[key], c)
            max_crow_conf = max(max_crow_conf, c)
        if _is_raptor(cname, sname):
            win_raptor[key] = max(win_raptor[key], c)
            max_raptor_conf = max(max_raptor_conf, c)
            if c >= 0.05:
                raptor_species.add(f"{cname} ({c:.2f})")

    all_embs = []
    crow_embs = []
    clean_crow_embs = []
    crow_windows = []

    for s in segs:
        emb = np.asarray(s["embeddings"], dtype=np.float32)
        if not np.isfinite(emb).all():
            continue
        key = (round(float(s["start_time"]), 2), round(float(s["end_time"]), 2))
        all_embs.append(emb)
        cc = win_crow.get(key, 0.0)
        rc = win_raptor.get(key, 0.0)
        if cc >= 0.25:
            crow_embs.append(emb)
            crow_windows.append(key)
            if rc < 0.05:
                clean_crow_embs.append(emb)

    if not all_embs:
        return {"id": rec_id, "ok": False, "error": "non-finite embeddings"}

    # Decode mono 22050 Hz for prosodic features + accurate duration.
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=180.0)
        dur = float(librosa.get_duration(path=audio_path))
        prosody = extract_prosody(y, sr, crow_windows)
    except Exception:
        dur = float(len(all_embs) * 3.0)
        prosody = np.zeros(len(PROSODY_NAMES), dtype=np.float32)

    return {
        "id": rec_id,
        "ok": True,
        "duration_s": dur,
        "n_segs": len(all_embs),
        "n_crow_segs": len(crow_embs),
        "n_clean_crow_segs": len(clean_crow_embs),
        "max_crow_conf": max_crow_conf,
        "max_raptor_conf": max_raptor_conf,
        "raptor_species": sorted(raptor_species),
        "emb_all": pool(all_embs).astype(np.float32),
        "emb_crow": pool(crow_embs).astype(np.float32) if crow_embs else None,
        "emb_clean_crow": pool(clean_crow_embs).astype(np.float32) if clean_crow_embs else None,
        "prosody": prosody,
    }


def extract_all(labels: list[dict], workers: int, force: bool = False, run: Run | None = None):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not force and CACHE_META.exists() and CACHE_NPZ.exists():
        meta = json.loads(CACHE_META.read_text())
        npz = np.load(CACHE_NPZ, allow_pickle=False)
        if run:
            with run.stage("extract") as st:
                st.update(len(meta), len(meta), extra="cached")
        return meta, npz

    con = sqlite3.connect(str(DB_PATH))
    id_to_path = {
        rid: resolve_audio_path(fp)
        for rid, fp in con.execute(
            "SELECT id, file_path FROM recordings WHERE source IN ('xeno_canto', 'macaulay') AND downloaded = 1"
        ).fetchall()
    }
    con.close()

    # Extract all witnessed items (plus unidentified_mobbing for comparison).
    wanted = [x for x in labels if x["witnessed"] or x["context"] == "unidentified_mobbing"]
    tasks = []
    label_by_id = {}
    for x in wanted:
        p = id_to_path.get(x["id"])
        if p and p.exists():
            tasks.append((x["id"], str(p), x["slug"]))
            label_by_id[x["id"]] = x

    print(f"Extracting BirdNET + prosody for {len(tasks)} recordings with {workers} workers...", flush=True)
    results = []
    ctx = run.stage("extract") if run else contextlib.nullcontext()
    with ctx as st, ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = [ex.submit(process_one, t) for t in tasks]
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            results.append(res)
            if i % 20 == 0 or i == len(tasks):
                ok_n = sum(1 for r in results if r["ok"])
                if st is not None:
                    st.update(i, len(tasks), extra=f"ok={ok_n}")
                if i % 50 == 0 or i == len(tasks):
                    print(f"  [{i}/{len(tasks)}] ok={ok_n}", flush=True)

    ok_res = [r for r in results if r["ok"]]
    ok_res.sort(key=lambda r: r["id"])

    meta = []
    emb_all = []
    emb_crow = []
    emb_clean = []
    has_crow = []
    has_clean = []
    prosody = []

    zero_emb = np.zeros(3072, dtype=np.float32)
    for r in ok_res:
        lbl = label_by_id[r["id"]]
        meta.append({
            **lbl,
            "duration_s": round(r["duration_s"], 2),
            "n_segs": r["n_segs"],
            "n_crow_segs": r["n_crow_segs"],
            "n_clean_crow_segs": r["n_clean_crow_segs"],
            "max_crow_conf": round(r["max_crow_conf"], 4),
            "max_raptor_conf": round(r["max_raptor_conf"], 4),
            "raptor_species": r["raptor_species"],
        })
        emb_all.append(r["emb_all"])
        has_crow.append(r["emb_crow"] is not None)
        emb_crow.append(r["emb_crow"] if r["emb_crow"] is not None else zero_emb)
        has_clean.append(r["emb_clean_crow"] is not None)
        emb_clean.append(r["emb_clean_crow"] if r["emb_clean_crow"] is not None else zero_emb)
        prosody.append(r["prosody"])

    CACHE_META.write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    np.savez_compressed(
        CACHE_NPZ,
        emb_all=np.stack(emb_all),
        emb_crow=np.stack(emb_crow),
        emb_clean=np.stack(emb_clean),
        has_crow=np.array(has_crow, dtype=bool),
        has_clean=np.array(has_clean, dtype=bool),
        prosody=np.stack(prosody),
    )
    return meta, np.load(CACHE_NPZ, allow_pickle=False)


def parse_hour(t: str | None) -> float:
    if not t:
        return -1.0
    m = re.search(r"(\d{1,2}):(\d{2})", str(t))
    if not m:
        return -1.0
    h, mn = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mn <= 59:
        return h + mn / 60.0
    return -1.0


def build_meta_features(rows: list[dict]) -> np.ndarray:
    feats = []
    for r in rows:
        hr = parse_hour(r.get("time"))
        has_hr = 1.0 if hr >= 0 else 0.0
        rad = 2 * np.pi * (hr / 24.0) if hr >= 0 else 0.0
        lat = float(r["lat"]) if r.get("lat") is not None else 0.0
        lng = float(r["lng"]) if r.get("lng") is not None else 0.0
        src_xc = 1.0 if r["source"] == "xeno_canto" else 0.0
        feats.append([
            float(r["duration_s"]),
            has_hr,
            np.sin(rad) * has_hr,
            np.cos(rad) * has_hr,
            lat,
            lng,
            src_xc,
        ])
    return np.asarray(feats, dtype=np.float32)


def group_id(r: dict) -> str:
    rec = (r.get("recordist") or "").strip().lower()
    if rec:
        return f"rec:{rec}"
    return f"grp:{r.get('group_key') or r['id']}"


def eval_binary(X: np.ndarray, y: np.ndarray, groups: np.ndarray, C: float = 0.1) -> dict:
    n_pos = int(y.sum())
    n_neg = int((1 - y).sum())
    n_grp = len(set(groups))
    n_splits = min(5, n_pos, n_neg, n_grp)
    if n_splits < 2:
        return {"n": int(len(y)), "n_pos": n_pos, "n_neg": n_neg, "auc": None}
    cv = StratifiedGroupKFold(n_splits=n_splits)
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=C, max_iter=3000, class_weight="balanced"),
    )
    probs = np.zeros(len(y), dtype=np.float64)
    for tr, te in cv.split(X, y, groups):
        clf.fit(X[tr], y[tr])
        probs[te] = clf.predict_proba(X[te])[:, 1]
    auc = float(roc_auc_score(y, probs))
    bal = float(balanced_accuracy_score(y, probs >= 0.5))
    return {
        "n": int(len(y)),
        "n_pos": n_pos,
        "n_neg": n_neg,
        "n_groups": int(n_grp),
        "auc": round(auc, 4),
        "bal_acc": round(bal, 4),
    }


def eval_multiclass(X: np.ndarray, y: np.ndarray, groups: np.ndarray, C: float = 0.1) -> dict:
    classes = sorted(set(y))
    min_c = min(int((y == c).sum()) for c in classes)
    n_splits = min(5, min_c)
    cv = StratifiedGroupKFold(n_splits=n_splits)
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=C, max_iter=3000, class_weight="balanced"),
    )
    preds = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), len(classes)), dtype=np.float64)
    for tr, te in cv.split(X, y, groups):
        clf.fit(X[tr], y[tr])
        preds[te] = clf.predict(X[te])
        p = clf.predict_proba(X[te])
        for j, c in enumerate(clf.classes_):
            proba[:, classes.index(c)][te] = p[:, j]
    ovr = {}
    for j, c in enumerate(classes):
        ovr[c] = round(float(roc_auc_score((y == c).astype(int), proba[:, j])), 4)
    return {
        "n": int(len(y)),
        "n_groups": int(len(set(groups))),
        "macro_f1": round(float(f1_score(y, preds, average="macro")), 4),
        "bal_acc": round(float(balanced_accuracy_score(y, preds)), 4),
        "macro_auc": round(float(np.mean(list(ovr.values()))), 4),
        "ovr_auc": ovr,
    }


def evaluate_all(meta: list[dict], npz) -> dict:
    emb_all = npz["emb_all"]
    emb_crow = npz["emb_crow"]
    emb_clean = npz["emb_clean"]
    has_crow = npz["has_crow"]
    has_clean = npz["has_clean"]
    prosody = npz["prosody"]

    report: dict = {}

    # 1. Corpus yield summary (witnessed American Crow)
    am_wit = [i for i, r in enumerate(meta) if r["slug"] == "american-crow" and r["witnessed"]]
    dur_by_ctx = Counter()
    cnt_by_ctx = Counter()
    crow_det_by_ctx = Counter()
    raptor_leak_by_ctx = Counter()
    for i in am_wit:
        c = meta[i]["context"]
        cnt_by_ctx[c] += 1
        dur_by_ctx[c] += meta[i]["duration_s"]
        if has_crow[i]:
            crow_det_by_ctx[c] += 1
        if meta[i]["max_raptor_conf"] >= 0.05:
            raptor_leak_by_ctx[c] += 1

    print("\n=== AMERICAN CROW WITNESSED YIELD (MEASURED AUDIO DURATION) ===")
    print(f"  {'context':24s} | {'n':>4s} | {'crow_det':>8s} | {'raptor>=.05':>11s} | {'audio_min':>9s}")
    print("  " + "-" * 68)
    total_min = 0.0
    for c, n in cnt_by_ctx.most_common():
        mins = dur_by_ctx[c] / 60.0
        total_min += mins
        print(f"  {c:24s} | {n:4d} | {crow_det_by_ctx[c]:8d} | {raptor_leak_by_ctx[c]:11d} | {mins:9.1f}")
    print(f"  TOTAL witnessed American Crow audio: {len(am_wit)} clips, {total_min:.1f} min ({total_min/60:.2f} hr)")
    report["amecro_yield"] = {
        c: {
            "n": cnt_by_ctx[c],
            "crow_detected": crow_det_by_ctx[c],
            "birdnet_raptor_detected": raptor_leak_by_ctx[c],
            "audio_min": round(dur_by_ctx[c] / 60.0, 1),
        }
        for c in cnt_by_ctx
    }

    # 2. Multi-class semantic separability (American Crow, witnessed classes with >=25 crow-detected clips)
    target_classes = [
        "owl_mobbing", "hawk_mobbing", "begging",
        "roost_gathering", "territorial_agonistic", "rattle_social", "food_foraging",
    ]
    idx_mc = [
        i for i in am_wit
        if meta[i]["context"] in target_classes and has_clean[i]
    ]
    y_mc = np.array([meta[i]["context"] for i in idx_mc])
    g_mc = np.array([group_id(meta[i]) for i in idx_mc])
    X_meta_mc = build_meta_features([meta[i] for i in idx_mc])

    print("\n=== TEST 1: AMERICAN CROW 7-CLASS SEMANTIC SEPARABILITY (RECORDIST-GROUPED 5-FOLD) ===")
    mc_results = {}
    for name, X in [
        ("birdnet_clean_crow_windows", emb_clean[idx_mc]),
        ("birdnet_all_crow_windows", emb_crow[idx_mc]),
        ("birdnet_full_clip", emb_all[idx_mc]),
        ("prosody_only", prosody[idx_mc]),
        ("metadata_only_null", X_meta_mc),
    ]:
        res = eval_multiclass(X, y_mc, g_mc, C=0.05 if X.shape[1] > 100 else 0.5)
        mc_results[name] = res
        print(f"  {name:28s} | n={res['n']:3d} | bal_acc={res['bal_acc']:.3f} | macro_f1={res['macro_f1']:.3f} | macro_auc={res['macro_auc']:.3f}")
        print(f"     ovr_auc: {res['ovr_auc']}")
    report["test1_multiclass_amecro"] = mc_results

    # 3. TEST 2: Referential Predator Alarm — Owl vs Hawk (American Crow)
    print("\n=== TEST 2: AMERICAN CROW OWL vs HAWK MOBBING (RECORDIST-GROUPED 5-FOLD) ===")
    oh_all = [i for i in am_wit if meta[i]["context"] in ("owl_mobbing", "hawk_mobbing") and has_crow[i]]
    oh_strict = [
        i for i in oh_all
        if (not meta[i]["pred_vocal"])
        and meta[i]["max_raptor_conf"] < 0.05
        and has_clean[i]
    ]
    oh_daytime = [
        i for i in oh_strict
        if 8.0 <= parse_hour(meta[i].get("time")) <= 17.0
    ]
    oh_ml_only = [i for i in oh_strict if meta[i]["source"] == "macaulay"]
    oh_xc_only = [i for i in oh_strict if meta[i]["source"] == "xeno_canto"]

    oh_report = {}
    for subset_name, idxs, feat_key in [
        ("all_crow_windows (raw)", oh_all, "emb_crow"),
        ("strict_zero_raptor_audio (clean)", oh_strict, "emb_clean"),
        ("strict_prosody_only", oh_strict, "prosody"),
        ("strict_metadata_null", oh_strict, "meta"),
        ("strict_daytime_08_17_only", oh_daytime, "emb_clean"),
        ("strict_macaulay_only", oh_ml_only, "emb_clean"),
        ("strict_xeno_canto_only", oh_xc_only, "emb_clean"),
    ]:
        if len(idxs) < 12:
            continue
        y = np.array([1 if meta[i]["context"] == "owl_mobbing" else 0 for i in idxs])
        g = np.array([group_id(meta[i]) for i in idxs])
        if feat_key == "meta":
            X = build_meta_features([meta[i] for i in idxs])
            C = 0.5
        elif feat_key == "prosody":
            X = prosody[idxs]
            C = 0.5
        else:
            X = npz[feat_key][idxs]
            C = 0.05
        res = eval_binary(X, y, g, C=C)
        oh_report[subset_name] = res
        print(
            f"  {subset_name:34s} | n={res['n']:3d} (owl={res['n_pos']:3d}, hawk={res['n_neg']:3d}, "
            f"rec={res.get('n_groups', 0):3d}) | AUC={res['auc']} | bal={res.get('bal_acc')}"
        )

    # Check BirdNET's own raptor detection rate on owl vs hawk
    owl_r_rate = np.mean([meta[i]["max_raptor_conf"] >= 0.05 for i in oh_all if meta[i]["context"] == "owl_mobbing"])
    hawk_r_rate = np.mean([meta[i]["max_raptor_conf"] >= 0.05 for i in oh_all if meta[i]["context"] == "hawk_mobbing"])
    print(f"  [Confounder check] BirdNET hears a raptor/owl (>=0.05): owl_clips={owl_r_rate:.1%}, hawk_clips={hawk_r_rate:.1%}")
    oh_report["raptor_leak_rate"] = {"owl": round(float(owl_r_rate), 4), "hawk": round(float(hawk_r_rate), 4)}

    # Prosodic feature comparison on strict owl vs hawk
    print("\n  [Prosodic feature differences — strict zero-raptor American Crow Owl vs Hawk]")
    owl_p = prosody[[i for i in oh_strict if meta[i]["context"] == "owl_mobbing"]]
    hawk_p = prosody[[i for i in oh_strict if meta[i]["context"] == "hawk_mobbing"]]
    pros_stats = []
    for j, fname in enumerate(PROSODY_NAMES[:15]):
        a, b = owl_p[:, j], hawk_p[:, j]
        stat, pval = mannwhitneyu(a, b, alternative="two-sided")
        # Rank-biserial correlation (effect size in [-1, 1], >0 means higher for owl)
        rbc = 1.0 - (2.0 * stat) / (len(a) * len(b))
        # wait: mannwhitneyu returns U1; rbc = 2*U1/(n1*n2) - 1
        rbc = (2.0 * stat) / (len(a) * len(b)) - 1.0
        pros_stats.append((pval, fname, float(np.median(a)), float(np.median(b)), float(rbc)))
    pros_stats.sort()
    for pval, fname, med_o, med_h, rbc in pros_stats[:8]:
        print(f"    {fname:18s}: owl_med={med_o:8.3f}  hawk_med={med_h:8.3f}  r={rbc:+.3f}  p={pval:.4g}")
    oh_report["top_prosody_diffs"] = [
        {"feature": f, "owl_median": round(mo, 4), "hawk_median": round(mh, 4), "r": round(r, 3), "p": round(p, 5)}
        for p, f, mo, mh, r in pros_stats[:8]
    ]
    report["test2_owl_vs_hawk_amecro"] = oh_report

    # 4. TEST 3: All-Corvus Predator Class (Aerial Owl+Hawk vs Mammal Scold)
    print("\n=== TEST 3: ALL-CORVUS AERIAL RAPTOR (OWL+HAWK) vs MAMMAL SCOLD ===")
    am_mam = [
        i for i, r in enumerate(meta)
        if r["witnessed"] and r["context"] in ("owl_mobbing", "hawk_mobbing", "mammal_scold")
        and (not r["pred_vocal"]) and r["max_raptor_conf"] < 0.05 and has_clean[i]
    ]
    y_m = np.array([1 if meta[i]["context"] == "mammal_scold" else 0 for i in am_mam])
    g_m = np.array([group_id(meta[i]) for i in am_mam])
    # Also check species confounder!
    sp_m = Counter((meta[i]["slug"], meta[i]["context"] == "mammal_scold") for i in am_mam)
    print("  Species distribution (slug, is_mammal):", sp_m.most_common(10))
    res_mam_bn = eval_binary(emb_clean[am_mam], y_m, g_m, C=0.05)
    res_mam_pr = eval_binary(prosody[am_mam], y_m, g_m, C=0.5)
    res_mam_md = eval_binary(build_meta_features([meta[i] for i in am_mam]), y_m, g_m, C=0.5)
    print(f"  birdnet_clean: {res_mam_bn}")
    print(f"  prosody_only : {res_mam_pr}")
    print(f"  metadata_null: {res_mam_md}")
    report["test3_aerial_vs_mammal_all_corvus"] = {
        "birdnet_clean": res_mam_bn,
        "prosody_only": res_mam_pr,
        "metadata_null": res_mam_md,
    }

    # 5. TEST 4: Mobbing (owl+hawk) vs Non-Mobbing Contexts (begging, rattle, foraging, roost, agonistic)
    print("\n=== TEST 4: AMERICAN CROW MOBBING vs INDIVIDUAL NON-MOBBING CONTEXTS (CLEAN WINDOWS) ===")
    pair_rep = {}
    for other in ("begging", "rattle_social", "food_foraging", "roost_gathering", "territorial_agonistic"):
        idxs = [
            i for i in am_wit
            if meta[i]["context"] in ("owl_mobbing", "hawk_mobbing", other)
            and has_clean[i]
            and meta[i]["max_raptor_conf"] < 0.05
            and not meta[i]["pred_vocal"]
        ]
        y = np.array([1 if meta[i]["context"] == other else 0 for i in idxs])
        g = np.array([group_id(meta[i]) for i in idxs])
        r_bn = eval_binary(emb_clean[idxs], y, g, C=0.05)
        r_pr = eval_binary(prosody[idxs], y, g, C=0.5)
        r_md = eval_binary(build_meta_features([meta[i] for i in idxs]), y, g, C=0.5)
        pair_rep[other] = {"birdnet": r_bn, "prosody": r_pr, "metadata": r_md}
        print(
            f"  mobbing vs {other:22s} | n={r_bn['n']:3d} (other={r_bn['n_pos']:2d}) | "
            f"BirdNET={r_bn['auc']:.3f} | Prosody={r_pr['auc']:.3f} | Meta={r_md['auc']:.3f}"
        )
    report["test4_mobbing_vs_each"] = pair_rep

    # Also check how many American Crow recordings have explicit timestamps in remarks
    ts_clips = [r for r in meta if r["slug"] == "american-crow" and r["witnessed"] and r["ts"]]
    print(f"\nTimestamped witnessed American Crow clips: {len(ts_clips)}")
    report["timestamped_amecro_count"] = len(ts_clips)

    (CACHE_DIR / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    labels = json.loads(LABELS_PATH.read_text())
    run = Run("0102 archive remarks semantics", ["extract", "evaluate"])
    meta, npz = extract_all(labels, workers=args.workers, force=args.force, run=run)
    with run.stage("evaluate"):
        report = evaluate_all(meta, npz)
    oh = report["test2_owl_vs_hawk_amecro"]["strict_zero_raptor_audio (clean)"]
    mc = report["test1_multiclass_amecro"]["birdnet_clean_crow_windows"]
    run.note(f"7-class macro AUC={mc['macro_auc']:.3f}; strict owl vs hawk AUC={oh['auc']:.3f} (n={oh['n']})")


if __name__ == "__main__":
    main()
