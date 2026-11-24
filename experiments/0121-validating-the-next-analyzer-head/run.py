"""0121 (CPU): validate the three scoped analyzer changes before touching analyzer/:
  1. True BirdNET-gated crowCount==0 false-trigger rate + unified retrain (uniform 1024-d
     window-mean pooling + explicit `none` class).
  2. Renaming `call` -> `rattle` (and testing pure crow-tools rattle vs. legacy archive `call` mix).
  3. Calibrating a high confidence threshold for `"BirdNET also heard: <Raptor> (<conf>)"`
     against pred_vocal remarks, jay-mimicry co-detections, and Ben's 29 kept captures.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0121-validating-the-next-analyzer-head/run.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0121-analyzer-validation-v2"
EXP0036 = REPO / "experiments" / "0036-what-would-more-labels-buy" / "results"
EXP102 = REPO / "experiments" / "0102-archive-remarks-semantics"
FIELD_DB = REPO / "fieldserver" / "instance" / "field.db"
FIELD_MEDIA = REPO / "fieldserver" / "instance" / "media"

for _p in ("crowgpt/src", "pipelines/ingest", "pipelines/training", "pipelines/representation", "analyzer"):
    sys.path.insert(0, str(REPO / _p))

from corpus import LabelCorpus  # noqa: E402
from crowgpt.progress import Run  # noqa: E402
from pooling import pool  # noqa: E402

CROW_TERMS = ("crow", "raven", "corvus", "jackdaw", "rook", "magpie")
JAY_TERMS = ("jay", "cyanocitta", "aphelocoma", "garrulus", "perisoreus")
CALL5_LEGACY = ["alarm call", "begging", "call", "song", "flight call"]
CALL5_RATTLE = ["alarm call", "begging", "rattle", "song", "flight call"]

_ANALYZER = None
_EXP102 = None


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _init_worker():
    global _ANALYZER, _EXP102
    from birdnetlib.analyzer import Analyzer

    _EXP102 = load_module("exp102_0121", EXP102 / "run.py")
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()


def _hp300_wav(src: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "quiet",
            "-y",
            "-i",
            src,
            "-af",
            "highpass=f=300,highpass=f=300",
            "-ac",
            "1",
            "-ar",
            "48000",
            tmp.name,
        ],
        check=True,
        timeout=120,
    )
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# 1. Scan crowCount==0 garbage files & field captures through analyzer's hp300 BirdNET
# ---------------------------------------------------------------------------

def _scan_garbage_file(task: tuple[str, str, list[int]]) -> dict:
    from birdnetlib import Recording

    file_id, path_str, seconds = task
    hp = _hp300_wav(path_str)
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            rec = Recording(_ANALYZER, str(hp), min_conf=0.05)
            rec.analyze()
    except Exception as exc:  # noqa: BLE001
        return {"file_id": file_id, "error": str(exc)[:160], "windows": {}}
    finally:
        hp.unlink(missing_ok=True)

    corvid_conf = defaultdict(float)
    top_other = defaultdict(lambda: ("", 0.0))
    for det in rec.detections or []:
        w = int(round(float(det["start_time"])))
        cn, sn = det.get("common_name", ""), det.get("scientific_name", "")
        conf = float(det["confidence"])
        blob = f"{cn} {sn}".lower()
        if any(t in blob for t in CROW_TERMS):
            corvid_conf[w] = max(corvid_conf[w], conf)
        elif conf > top_other[w][1]:
            top_other[w] = (cn, conf)

    # Match each garbage segment's `second` to `aligned = 3 * (second // 3)` (same rule as 0036/prepare.py)
    win_info = {}
    for sec in seconds:
        aligned = 3 * (int(sec) // 3)
        win_info[str(sec)] = {
            "aligned": aligned,
            "corvid_conf_hp300": round(float(corvid_conf.get(aligned, 0.0)), 4),
            "top_non_corvid": top_other[aligned][0],
            "top_non_corvid_conf": round(float(top_other[aligned][1]), 4),
        }
    return {"file_id": file_id, "error": None, "windows": win_info}


def scan_garbage_corvid_gate(stage) -> dict[str, dict]:
    """Map `file_id:second` -> BirdNET hp300 corvid detection confidence on crowCount==0 segments."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / "garbage_hp300_gate.json"
    if cache_file.exists():
        stage.update(1, 1, extra="reused garbage_hp300_gate.json")
        return json.loads(cache_file.read_text())

    corpus = LabelCorpus(dataset="all-public")
    index = corpus.audio_index()
    by_file: dict[str, tuple[str, list[int]]] = {}
    for key, flags in corpus.labels().items():
        if not flags.get("reviewed") or corpus.core_labels(flags):
            continue
        if flags.get("crowCount") != 0:
            continue
        file_id, start, _end = key.rsplit("-", 2)
        found = index.get(file_id)
        if found is None or not Path(found[1]).exists():
            continue
        if file_id not in by_file:
            by_file[file_id] = (str(found[1]), [])
        by_file[file_id][1].append(int(start))

    tasks = [(fid, p, secs) for fid, (p, secs) in sorted(by_file.items())]
    out_map = {}
    stage.update(0, len(tasks), extra="checking BirdNET corvid gate on crowCount=0 files")
    with ProcessPoolExecutor(max_workers=12, initializer=_init_worker) as ex:
        futs = [ex.submit(_scan_garbage_file, t) for t in tasks]
        for done, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            fid = res["file_id"]
            for sec_str, info in res["windows"].items():
                out_map[f"{fid}:{sec_str}"] = info
            if done % 25 == 0 or done == len(tasks):
                stage.update(done, len(tasks))

    cache_file.write_text(json.dumps(out_map, indent=2))
    return out_map


def _scan_field_capture(task: tuple[int, str, float | None, float | None, str | None]) -> dict:
    from birdnetlib import Recording

    cid, path_str, lat, lon, rec_date = task
    located = lat is not None and lon is not None
    hp = _hp300_wav(path_str)
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            rec = Recording(
                _ANALYZER,
                str(hp),
                min_conf=0.10,
                **({"lat": float(lat), "lon": float(lon)} if located else {}),
            )
            rec.analyze()
            rec.extract_embeddings()
    finally:
        hp.unlink(missing_ok=True)

    emb_by_start = {}
    for s in rec.embeddings or []:
        st = round(float(s["start_time"]), 2)
        e = np.asarray(s["embeddings"], dtype=np.float32)
        if np.isfinite(e).all():
            emb_by_start[str(st)] = e.tolist()

    corvid_dets, raptor_dets, jay_dets = [], [], []
    for det in rec.detections or []:
        cn, sn = det.get("common_name", ""), det.get("scientific_name", "")
        conf = float(det["confidence"])
        st, en = round(float(det["start_time"]), 2), round(float(det["end_time"]), 2)
        blob = f"{cn} {sn}".lower()
        if any(t in blob for t in CROW_TERMS) and conf >= 0.10:
            corvid_dets.append({"start": st, "end": en, "species": cn, "scientific_name": sn, "conf": round(conf, 4)})
        if any(t in blob for t in JAY_TERMS) and conf >= 0.10:
            jay_dets.append({"start": st, "end": en, "species": cn, "conf": round(conf, 4)})
        if _EXP102._is_raptor(cn, sn) and conf >= 0.20:
            raptor_dets.append({"start": st, "end": en, "species": cn, "scientific_name": sn, "conf": round(conf, 4)})

    return {
        "capture_id": cid,
        "located": located,
        "emb_by_start": emb_by_start,
        "corvid_dets": corvid_dets,
        "raptor_dets": raptor_dets,
        "jay_dets": jay_dets,
    }


def scan_field_captures(stage) -> tuple[dict[int, dict], list[dict], list[dict]]:
    con = sqlite3.connect(f"file:{FIELD_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cap_rows = con.execute(
        """
        SELECT DISTINCT c.id, c.keep, c.latitude, c.longitude, substr(c.recorded_at, 1, 10) AS rec_date,
               c.name, c.notes,
               (SELECT m.storage_ref FROM media m WHERE m.capture_id = c.id AND m.kind = 'audio' LIMIT 1) AS storage_ref
        FROM captures c
        WHERE c.keep = 1 OR EXISTS (SELECT 1 FROM labels l WHERE l.capture_id = c.id AND l.label_source = 'human')
        ORDER BY c.id
        """
    ).fetchall()
    lab_rows = con.execute(
        """
        SELECT l.id, l.capture_id, l.call_type, l.start_sec, l.end_sec, l.species, l.notes, c.keep, c.notes AS cap_notes
        FROM labels l
        JOIN captures c ON c.id = l.capture_id
        WHERE l.label_source = 'human' AND l.start_sec IS NOT NULL AND l.end_sec IS NOT NULL
        ORDER BY l.capture_id, l.start_sec
        """
    ).fetchall()
    con.close()

    cap_meta = [dict(r) for r in cap_rows if r["storage_ref"] and (FIELD_MEDIA / r["storage_ref"]).exists()]
    labels = [dict(r) for r in lab_rows]

    cache_file = CACHE / "field_captures_hp300.json"
    if cache_file.exists():
        stage.update(1, 1, extra="reused field_captures_hp300.json")
        return {int(k): v for k, v in json.loads(cache_file.read_text()).items()}, cap_meta, labels

    tasks = [
        (int(c["id"]), str(FIELD_MEDIA / c["storage_ref"]), c["latitude"], c["longitude"], c["rec_date"])
        for c in cap_meta
    ]
    scanned = {}
    stage.update(0, len(tasks), extra="scanning field captures with hp300 BirdNET")
    with ProcessPoolExecutor(max_workers=8, initializer=_init_worker) as ex:
        futs = [ex.submit(_scan_field_capture, t) for t in tasks]
        for done, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            scanned[res["capture_id"]] = res
            stage.update(done, len(tasks))

    cache_file.write_text(json.dumps(scanned))
    return scanned, cap_meta, labels


# ---------------------------------------------------------------------------
# 2. Align garbage.npz rows with BirdNET hp300 corvid gate & build training pool
# ---------------------------------------------------------------------------

def load_pools(garbage_gate: dict[str, dict]):
    keyed = np.load(EXP0036 / "crowtools_keyed.npz", allow_pickle=True)
    X_ct = keyed["X"].astype(np.float32)
    g_ct = np.array([f"ct:{g}" for g in keyed["groups"]])
    # Map legacy "call" -> "rattle" in label sets
    Y_ct = [set("rattle" if c == "call" else c for c in v) for v in keyed["labels"]]

    arch = np.load(REPO / "pipelines" / "training" / "results" / "pooled_embeddings.npz", allow_pickle=True)
    X_ar = arch["X"].astype(np.float32)
    Y_ar_legacy = [set("rattle" if c == "call" else c for c in v) for v in arch["Y"]]
    # Pure-rattle variant: archive weak "call" tags are NOT assumed to be rattle (kept as unknown for rattle, active for other classes)
    Y_ar_pure_rattle = [set(c for c in v if c != "call") for v in arch["Y"]]
    g_ar = np.array([f"xc:{i}" for i in range(len(Y_ar_legacy))])

    garb = np.load(EXP0036 / "garbage.npz", allow_pickle=True)
    X_gb = garb["X"].astype(np.float32)
    g_gb_raw = garb["groups"]
    g_gb = np.array([f"ct:{g}" for g in g_gb_raw])
    Y_gb = [{"none"} for _ in range(len(X_gb))]

    # Reconstruct exact order of garbage.npz rows to attach corvid_conf_hp300 per row!
    # In 0036/prepare.py: items = list(garbage_rows().items()), mapped in order.
    corpus = LabelCorpus(dataset="all-public")
    index = corpus.audio_index()
    by_fid = defaultdict(list)
    for key, flags in corpus.labels().items():
        if not flags.get("reviewed") or corpus.core_labels(flags):
            continue
        if flags.get("crowCount") != 0:
            continue
        fid, start, _ = key.rsplit("-", 2)
        if fid in index:
            by_fid[fid].append(int(start))

    used_pos = defaultdict(int)
    gb_corvid_conf = np.zeros(len(X_gb), dtype=np.float32)
    gb_top_other = []
    for idx, fid in enumerate(g_gb_raw):
        fid_s = str(fid)
        pos = used_pos[fid_s]
        secs = by_fid.get(fid_s, [])
        if pos < len(secs):
            sec = secs[pos]
            info = garbage_gate.get(f"{fid_s}:{sec}", {})
            gb_corvid_conf[idx] = float(info.get("corvid_conf_hp300", 0.0))
            gb_top_other.append(info.get("top_non_corvid", ""))
        else:
            gb_top_other.append("")
        used_pos[fid_s] += 1

    X_all = np.concatenate([X_ct, X_ar, X_gb], axis=0)
    g_all = np.concatenate([g_ct, g_ar, g_gb])
    src_all = np.array(["ct"] * len(X_ct) + ["ar"] * len(X_ar) + ["garbage"] * len(X_gb))
    garb_corvid_all = np.concatenate([np.ones(len(X_ct) + len(X_ar), dtype=np.float32), gb_corvid_conf])

    return {
        "X_all": X_all,
        "g_all": g_all,
        "src_all": src_all,
        "Y_legacy_mix": Y_ct + Y_ar_legacy + Y_gb,
        "Y_pure_rattle": Y_ct + Y_ar_pure_rattle + Y_gb,
        "gb_corvid_conf": gb_corvid_conf,
        "gb_top_other": gb_top_other,
    }


# ---------------------------------------------------------------------------
# 3. Unified Head Architectures (OvR MultiLabelHead with "none" vs Softmax with "none")
# ---------------------------------------------------------------------------

class UnifiedOvRHead:
    """MultiLabelHead over CALL5_RATTLE (+ optional 'none' class), on 1024-d mean or 3072-d pooled."""

    def __init__(self, dim_mode: str = "1024", include_none: bool = True, pure_rattle: bool = False, C: float = 1.0):
        self.dim_mode = dim_mode
        self.include_none = include_none
        self.pure_rattle = pure_rattle
        self.C = C
        self.classes = CALL5_RATTLE + (["none"] if include_none else [])
        self.models = {}

    def _feat(self, X: np.ndarray) -> np.ndarray:
        return X[:, :1024] if self.dim_mode == "1024" else X

    def fit(self, X: np.ndarray, Y_sets: list[set[str]], src: np.ndarray):
        Xf = self._feat(X)
        for cls in self.classes:
            if cls != "none" and not self.include_none:
                keep = src != "garbage"
            elif cls == "rattle" and self.pure_rattle:
                # Exclude archive clips without rattle from training rattle so weak archive "call" tags don't pollute rattle
                keep = src != "ar"
            else:
                keep = np.ones(len(X), dtype=bool)
            idx = np.flatnonzero(keep)
            y = np.array([1 if cls in Y_sets[i] else 0 for i in idx], dtype=int)
            if 0 < y.sum() < len(y):
                self.models[cls] = make_pipeline(
                    StandardScaler(),
                    LogisticRegression(C=self.C, max_iter=4000, class_weight="balanced"),
                ).fit(Xf[idx], y)
        self.classes = [c for c in self.classes if c in self.models]
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xf = self._feat(X)
        return np.column_stack([self.models[c].predict_proba(Xf)[:, 1] for c in self.classes])

    def predict_top(self, X: np.ndarray, rule: str = "none_top_or_p05") -> tuple[np.ndarray, np.ndarray]:
        """Return (predicted_label_or_none, confidence)."""
        proba = self.predict_proba(X)
        if not self.include_none or "none" not in self.classes:
            idx = proba.argmax(axis=1)
            return np.array([self.classes[i] for i in idx], dtype=object), proba[np.arange(len(X)), idx]

        none_i = self.classes.index("none")
        call_indices = [i for i, c in enumerate(self.classes) if c != "none"]
        p_none = proba[:, none_i]
        p_calls = proba[:, call_indices]
        best_ci = p_calls.argmax(axis=1)
        best_cls = np.array([self.classes[call_indices[j]] for j in best_ci], dtype=object)
        best_cp = p_calls[np.arange(len(X)), best_ci]

        if rule == "argmax6":
            is_none = p_none >= best_cp
        elif rule == "none_p05":
            is_none = p_none >= 0.50
        else:  # "none_top_or_low": abstain if `none` outranks best call OR (`none >= 0.50` and best call `< 0.65`) or best call `< 0.40`
            is_none = (p_none >= best_cp) | (best_cp < 0.40)

        out_cls = np.where(is_none, "none", best_cls)
        out_p = np.where(is_none, p_none, best_cp)
        return out_cls, out_p


class UnifiedSoftmaxHead:
    """Single-label 6-class softmax (`alarm call, begging, rattle, song, flight call, none`) on 1024-d mean."""

    def __init__(self, C: float = 1.0):
        self.C = C
        self.clf = None
        self.classes = []

    def fit(self, X: np.ndarray, Y_sets: list[set[str]]):
        rows, y = [], []
        for i, s in enumerate(Y_sets):
            if s == {"none"}:
                rows.append(i)
                y.append("none")
            elif len(s) == 1:
                rows.append(i)
                y.append(next(iter(s)))
        idx = np.array(rows, dtype=int)
        self.clf = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=self.C, max_iter=4000, class_weight="balanced"),
        ).fit(X[idx, :1024], y)
        self.classes = list(self.clf.classes_)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(X[:, :1024])

    def predict_top(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p = self.predict_proba(X)
        idx = p.argmax(axis=1)
        return np.array([self.classes[i] for i in idx], dtype=object), p[np.arange(len(X)), idx]


def run_grouped_cv(pools: dict) -> dict:
    X_all = pools["X_all"]
    g_all = pools["g_all"]
    src_all = pools["src_all"]
    Y_leg = pools["Y_legacy_mix"]
    Y_pure = pools["Y_pure_rattle"]
    gb_conf = pools["gb_corvid_conf"]

    strat = []
    for s in Y_leg:
        if "none" in s:
            strat.append("none")
        elif "flight call" in s:
            strat.append("flight call")
        elif s:
            strat.append(sorted(s)[0])
        else:
            strat.append("other")
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X_all, np.array(strat), g_all))

    configs = {
        "M0_3072_no_none": ("ovr", "3072", False, False, 1.0),
        "M1_1024_no_none": ("ovr", "1024", False, False, 1.0),
        "M2_1024_ovr_with_none_legacy_rattle": ("ovr", "1024", True, False, 1.0),
        "M2b_1024_ovr_with_none_pure_rattle": ("ovr", "1024", True, True, 1.0),
        "M2c_1024_ovr_with_none_pure_rattle_C0.1": ("ovr", "1024", True, True, 0.1),
        "M3_1024_softmax_with_none": ("softmax", "1024", True, False, 1.0),
    }

    is_garb = src_all == "garbage"
    is_ct = src_all == "ct"
    ct_single_mask = np.array([is_ct[i] and len(Y_leg[i] & set(CALL5_RATTLE[:4])) == 1 for i in range(len(X_all))])
    y_ct_single = np.array([next(iter(Y_leg[i] & set(CALL5_RATTLE[:4]))) for i in np.flatnonzero(ct_single_mask)], dtype=object)

    out = {}
    for name, (kind, dim, inc_none, pure_r, C_val) in configs.items():
        Y_use = Y_pure if pure_r else Y_leg
        all_cls = CALL5_RATTLE + (["none"] if inc_none else [])
        oof_p = np.zeros((len(X_all), len(all_cls)), dtype=np.float64)
        oof_top_argmax = np.empty(len(X_all), dtype=object)
        oof_top_rule = np.empty(len(X_all), dtype=object)
        oof_top_conf = np.zeros(len(X_all), dtype=np.float64)

        for tr, te in folds:
            if kind == "ovr":
                m = UnifiedOvRHead(dim_mode=dim, include_none=inc_none, pure_rattle=pure_r, C=C_val).fit(
                    X_all[tr], [Y_use[i] for i in tr], src_all[tr]
                )
                pr = m.predict_proba(X_all[te])
                for ci, c in enumerate(m.classes):
                    oof_p[te, all_cls.index(c)] = pr[:, ci]
                ta, ca = m.predict_top(X_all[te], rule="argmax6")
                tr_lbl, cr = m.predict_top(X_all[te], rule="none_top_or_low")
                oof_top_argmax[te] = ta
                oof_top_rule[te] = tr_lbl
                oof_top_conf[te] = cr
            else:
                m = UnifiedSoftmaxHead(C=C_val).fit(X_all[tr], [Y_use[i] for i in tr])
                pr = m.predict_proba(X_all[te])
                for ci, c in enumerate(m.classes):
                    oof_p[te, all_cls.index(c)] = pr[:, ci]
                ta, ca = m.predict_top(X_all[te])
                oof_top_argmax[te] = ta
                oof_top_rule[te] = ta
                oof_top_conf[te] = ca

        # Per-class AUC & AP on call rows (crow-tools + archive; for pure_rattle, score rattle on crow-tools where rattle is defined!)
        per_class = {}
        for ci, c in enumerate(CALL5_RATTLE):
            if c == "rattle" and pure_r:
                eval_m = is_ct
            else:
                eval_m = ~is_garb
            yc = np.array([1 if c in Y_use[i] else 0 for i in np.flatnonzero(eval_m)], dtype=int)
            per_class[c] = {
                "auc_calls_only": round(float(roc_auc_score(yc, oof_p[eval_m, ci])), 4),
                "ap_calls_only": round(float(average_precision_score(yc, oof_p[eval_m, ci])), 4),
                "positives": int(yc.sum()),
            }
            # Also over ALL rows including garbage negatives
            eval_all = (is_ct | is_garb) if (c == "rattle" and pure_r) else np.ones(len(X_all), dtype=bool)
            ya = np.array([1 if c in Y_use[i] else 0 for i in np.flatnonzero(eval_all)], dtype=int)
            per_class[c]["auc_with_garbage"] = round(float(roc_auc_score(ya, oof_p[eval_all, ci])), 4)
            per_class[c]["ap_with_garbage"] = round(float(average_precision_score(ya, oof_p[eval_all, ci])), 4)

        # Within-archive flight call AUC (true acoustic flight-call separation without corpus-boundary cheat!)
        ar_m = src_all == "ar"
        y_fl_ar = np.array([1 if "flight call" in Y_leg[i] else 0 for i in np.flatnonzero(ar_m)], dtype=int)
        within_ar_fl_auc = round(float(roc_auc_score(y_fl_ar, oof_p[ar_m, CALL5_RATTLE.index("flight call")])), 4)

        # Garbage rejection across: (a) all 572 garbage rows, (b) BirdNET-leaked >=0.10, (c) BirdNET-leaked >=0.25
        gb_argmax = oof_top_argmax[is_garb]
        gb_rule = oof_top_rule[is_garb]
        gb_c = oof_top_conf[is_garb]

        def gb_stats(sub_mask: np.ndarray) -> dict:
            n_s = int(sub_mask.sum())
            if n_s == 0:
                return {"n": 0}
            if not inc_none:
                false_p05 = float((gb_c[sub_mask] > 0.50).mean())
                return {
                    "n": n_s,
                    "rejected_argmax_none": 0.0,
                    "false_call_p_gt_0.5": round(false_p05, 4),
                }
            return {
                "n": n_s,
                "rejected_argmax_none": round(float((gb_argmax[sub_mask] == "none").mean()), 4),
                "rejected_none_top_or_p_lt_0.40": round(float((gb_rule[sub_mask] == "none").mean()), 4),
                "false_call_remaining_argmax": round(float((gb_argmax[sub_mask] != "none").mean()), 4),
            }

        # CORE4 macro-F1 on single-label crow-tools rows
        pred_ct_arg = oof_top_argmax[ct_single_mask]
        pred_ct_rule = oof_top_rule[ct_single_mask]
        f1_uncond_arg = float(f1_score(y_ct_single, pred_ct_arg, labels=CALL5_RATTLE[:4], average="macro", zero_division=0))
        kept_arg = pred_ct_arg != "none"
        f1_cond_arg = float(f1_score(y_ct_single[kept_arg], pred_ct_arg[kept_arg], labels=CALL5_RATTLE[:4], average="macro", zero_division=0)) if kept_arg.any() else 0.0

        # Co-occurrence recall on multi-label crow-tools rows (e.g. begging + rattle)
        multi_ct = np.array([is_ct[i] and len(Y_leg[i] & set(CALL5_RATTLE[:4])) >= 2 for i in range(len(X_all))])
        both_03 = 0
        both_05 = 0
        for idx_m in np.flatnonzero(multi_ct):
            truth = Y_leg[idx_m] & set(CALL5_RATTLE[:4])
            scs = [oof_p[idx_m, CALL5_RATTLE.index(c)] for c in truth]
            if min(scs) > 0.30:
                both_03 += 1
            if min(scs) > 0.50:
                both_05 += 1

        out[name] = {
            "garbage_all_572": gb_stats(np.ones(int(is_garb.sum()), dtype=bool)),
            "garbage_leaked_past_birdnet_ge_0.10": gb_stats(gb_conf >= 0.10),
            "garbage_leaked_past_birdnet_ge_0.25": gb_stats(gb_conf >= 0.25),
            "crowtools_single_label_core4": {
                "n": int(ct_single_mask.sum()),
                "false_abstain_argmax_none": round(float((pred_ct_arg == "none").mean()), 4),
                "false_abstain_rule_none": round(float((pred_ct_rule == "none").mean()), 4),
                "macro_f1_unconditional_argmax": round(f1_uncond_arg, 4),
                "macro_f1_conditional_non_abstained": round(f1_cond_arg, 4),
            },
            "co_occurrence_multi_label_ct": {
                "n_multi": int(multi_ct.sum()),
                "both_above_0.50": both_05,
                "both_above_0.30": both_03,
            },
            "within_archive_flight_call_auc": within_ar_fl_auc,
            "per_class": per_class,
        }
    return out


# ---------------------------------------------------------------------------
# 4. Raptor Co-Detection Threshold Calibration (0102 archive + 29 kept captures)
# ---------------------------------------------------------------------------

def calibrate_raptor_thresholds(scanned_field: dict[int, dict], cap_meta: list[dict]) -> dict:
    # 1. Check 0102's 561 witnessed American Crow archive recordings!
    # Wait: 0112's WINDOWS has per-window `raptor` max conf on 423 archive recordings, AND 0102/records.json has `max_raptor_conf` and `pred_vocal`!
    rec102_path = DATA_DIR / "experiments" / "0102-archive-remarks" / "records.json"
    archive_calib = {}
    if rec102_path.exists():
        recs102 = [r for r in json.loads(rec102_path.read_text()) if r.get("slug") == "american-crow" and r.get("witnessed")]
        # Check corvid.db detections for jay co-detections on these recording IDs
        db = sqlite3.connect(f"file:{DATA_DIR / 'corvid.db'}?mode=ro", uri=True)
        ids = [int(r["id"]) for r in recs102]
        jay_recs = set()
        for (rid, sp, sci) in db.execute(
            f"SELECT recording_id, species, scientific_name FROM detections WHERE recording_id IN ({','.join('?' * len(ids))})",
            ids,
        ):
            if any(t in f"{sp or ''} {sci or ''}".lower() for t in JAY_TERMS):
                jay_recs.add(int(rid))
        db.close()

        vocal = [r for r in recs102 if r.get("pred_vocal")]
        non_vocal_raptor = [r for r in recs102 if r.get("context") in ("owl_mobbing", "hawk_mobbing") and not r.get("pred_vocal")]
        non_raptor_ctx = [r for r in recs102 if r.get("context") in ("begging", "roost_gathering", "food_foraging", "flight_contact", "rattle_social")]
        non_raptor_with_jay = [r for r in non_raptor_ctx if int(r["id"]) in jay_recs]
        non_raptor_no_jay = [r for r in non_raptor_ctx if int(r["id"]) not in jay_recs]

        by_thr = {}
        for thr in (0.25, 0.50, 0.70, 0.80):
            by_thr[f"conf_ge_{thr:.2f}"] = {
                "recall_on_stated_vocal_raptor": round(float(np.mean([float(r["max_raptor_conf"]) >= thr for r in vocal])), 4) if vocal else None,
                "n_stated_vocal": len(vocal),
                "rate_on_silent_raptor_mob": round(float(np.mean([float(r["max_raptor_conf"]) >= thr for r in non_vocal_raptor])), 4) if non_vocal_raptor else None,
                "false_rate_on_non_raptor_scenes_all": round(float(np.mean([float(r["max_raptor_conf"]) >= thr for r in non_raptor_ctx])), 4) if non_raptor_ctx else None,
                "false_rate_when_jay_detected": round(float(np.mean([float(r["max_raptor_conf"]) >= thr for r in non_raptor_with_jay])), 4) if non_raptor_with_jay else None,
                "n_non_raptor_with_jay": len(non_raptor_with_jay),
                "false_rate_when_no_jay": round(float(np.mean([float(r["max_raptor_conf"]) >= thr for r in non_raptor_no_jay])), 4) if non_raptor_no_jay else None,
                "n_non_raptor_no_jay": len(non_raptor_no_jay),
            }
        archive_calib = by_thr

    # 2. Check Ben's 29 kept captures across thresholds
    kept = [c for c in cap_meta if int(c["keep"] or 0) == 1 and int(c["id"]) in scanned_field]
    kept_by_thr = {}
    for thr in (0.25, 0.50, 0.70, 0.80):
        hits = []
        for c in kept:
            cid = int(c["id"])
            sc = scanned_field[cid]
            r_above = [r for r in sc["raptor_dets"] if r["conf"] >= thr]
            if r_above:
                best = max(r_above, key=lambda r: r["conf"])
                hits.append({
                    "capture_id": cid,
                    "name": c["name"],
                    "display": f"BirdNET also heard: {best['species']} ({best['conf']:.2f})",
                    "jay_also_detected": bool(sc["jay_dets"]),
                    "notes_snippet": (c["notes"] or "")[:120],
                })
        kept_by_thr[f"conf_ge_{thr:.2f}"] = {"n_kept_captures_firing": len(hits), "hits": hits}

    return {"archive_561_calibration": archive_calib, "kept_29_captures": kept_by_thr}


# ---------------------------------------------------------------------------
# 5. Field Transfer & Kept-Capture Region Replay (Shipped vs Unified Retrain)
# ---------------------------------------------------------------------------

def evaluate_field_and_replay(pools: dict, scanned_field: dict[int, dict], cap_meta: list[dict], labels: list[dict]) -> dict:
    shipped = joblib.load(REPO / "pipelines" / "training" / "models" / "american-crow" / "calltype_clf.joblib")
    sh_clf = shipped["model"]
    sh_classes = ["rattle" if c == "call" else c for c in shipped["classes"]]

    X_all, src_all = pools["X_all"], pools["src_all"]
    m2_leg = UnifiedOvRHead("1024", include_none=True, pure_rattle=False, C=1.0).fit(X_all, pools["Y_legacy_mix"], src_all)
    m2_pure = UnifiedOvRHead("1024", include_none=True, pure_rattle=True, C=1.0).fit(X_all, pools["Y_pure_rattle"], src_all)
    m2_pure_c01 = UnifiedOvRHead("1024", include_none=True, pure_rattle=True, C=0.1).fit(X_all, pools["Y_pure_rattle"], src_all)
    m3_soft = UnifiedSoftmaxHead(C=1.0).fit(X_all, pools["Y_legacy_mix"])

    # Score human field labels (X_span = all covered 3s windows; X_win = single 3s window)
    rows = []
    call_label_notes = []
    for lab in labels:
        cap = scanned_field.get(int(lab["capture_id"]))
        if not cap or not cap["emb_by_start"]:
            continue
        emb_map = {float(k): np.array(v, dtype=np.float32) for k, v in cap["emb_by_start"].items()}
        starts = sorted(emb_map)
        s, e = float(lab["start_sec"]), float(lab["end_sec"])
        covered = [emb_map[w] for w in starts if w < e and (w + 3.0) > s]
        if not covered:
            continue
        mid = 0.5 * (s + e)
        nearest = min(starts, key=lambda w: abs((w + 1.5) - mid))
        rows.append({
            "lab": lab,
            "X_span": pool(covered).astype(np.float32),
            "X_win": pool(emb_map[nearest]).astype(np.float32),
            "n_win": len(covered),
        })
        if lab["call_type"] == "call" and int(lab["keep"] or 0) == 1:
            call_label_notes.append({
                "capture_id": lab["capture_id"],
                "span": f"{s:.1f}-{e:.1f}s",
                "label_note": lab["notes"],
                "capture_note_head": (lab["cap_notes"] or "")[:120],
            })

    X_span = np.stack([r["X_span"] for r in rows])
    X_win = np.stack([r["X_win"] for r in rows])
    # Map human "call" -> "rattle" for taxonomy-aligned comparison, while noting contact-call gap!
    y_mapped = np.array(["rattle" if r["lab"]["call_type"] == "call" else r["lab"]["call_type"] for r in rows], dtype=object)
    kept = np.array([int(r["lab"]["keep"] or 0) == 1 for r in rows], dtype=bool)
    trainable = np.isin(y_mapped, CALL5_RATTLE)
    not_crow = y_mapped == "not_a_crow"
    multi_win = np.array([r["n_win"] >= 2 for r in rows], dtype=bool)

    def eval_fn(fn, Xm):
        pred, conf = fn(Xm)
        res = {}
        for sname, mask in (
            ("kept_all_58", trainable & kept),
            ("kept_multi_window_regions", trainable & kept & multi_win),
            ("kept_single_window_regions", trainable & kept & (~multi_win)),
        ):
            if mask.sum() == 0:
                continue
            yt = y_mapped[mask]
            pr = pred[mask]
            non_ab = pr != "none"
            res[sname] = {
                "n": int(mask.sum()),
                "abstained_none": int((~non_ab).sum()),
                "top1_unconditional": round(float((pr == yt).mean()), 4),
                "top1_non_abstained": round(float((pr[non_ab] == yt[non_ab]).mean()) if non_ab.any() else 0.0, 4),
                "predicted_breakdown": dict(Counter(pr).most_common()),
            }
        if not_crow.any():
            res["kept_not_a_crow_2"] = {
                "n": int(not_crow.sum()),
                "rejected_as_none": int((pred[not_crow] == "none").sum()),
                "predictions": pred[not_crow].tolist(),
            }
        return res

    def sh_predict(Xm):
        p = sh_clf.predict_proba(Xm)
        idx = p.argmax(axis=1)
        return np.array([sh_classes[i] for i in idx], dtype=object), p[np.arange(len(Xm)), idx]

    models_eval = {}
    for mname, fn in (
        ("shipped_3072_no_none", sh_predict),
        ("M2_1024_ovr_none_legacy_rattle", lambda Xm: m2_leg.predict_top(Xm, "argmax6")),
        ("M2b_1024_ovr_none_pure_rattle", lambda Xm: m2_pure.predict_top(Xm, "argmax6")),
        ("M2c_1024_ovr_none_pure_rattle_C0.1", lambda Xm: m2_pure_c01.predict_top(Xm, "argmax6")),
        ("M3_1024_softmax_none", m3_soft.predict_top),
    ):
        models_eval[mname] = {
            "X_span": eval_fn(fn, X_span),
            "X_win": eval_fn(fn, X_win),
        }

    # Replay all 29 kept captures region-by-region (analyzer/birdnet.py logic)
    kept_caps = [c for c in cap_meta if int(c["keep"] or 0) == 1 and int(c["id"]) in scanned_field]
    conf_total, conf_none_m2, cand_total, cand_none_m2 = 0, 0, 0, 0
    sh_dist, m2_dist = Counter(), Counter()
    long_reg_flips = []

    for c in kept_caps:
        cid = int(c["id"])
        sc = scanned_field[cid]
        emb_map = {float(k): np.array(v, dtype=np.float32) for k, v in sc["emb_by_start"].items()}
        wins = []
        for det in sorted(sc["corvid_dets"], key=lambda d: d["start"]):
            emb = emb_map.get(float(det["start"]))
            if emb is not None:
                wins.append({**det, "candidate": det["conf"] < 0.25, "emb": emb})
        regions = []
        for w in wins:
            last = regions[-1][-1] if regions else None
            if last and w["species"] == last["species"] and w["candidate"] == last["candidate"] and (w["start"] - last["end"] <= 1.5):
                regions[-1].append(w)
            else:
                regions.append([w])
        for reg in regions:
            if "crow" not in reg[0]["species"].lower():
                continue
            embs = np.stack([w["emb"] for w in reg])
            v3072 = pool(embs).reshape(1, -1).astype(np.float32)
            sh_c, sh_p = sh_predict(v3072)
            m2_c, m2_p = m2_pure_c01.predict_top(v3072, "argmax6")
            if reg[0]["candidate"]:
                cand_total += 1
                if m2_c[0] == "none":
                    cand_none_m2 += 1
            else:
                conf_total += 1
                sh_dist[str(sh_c[0])] += 1
                m2_dist[str(m2_c[0])] += 1
                if m2_c[0] == "none":
                    conf_none_m2 += 1
                if len(reg) >= 2 and sh_c[0] != m2_c[0]:
                    long_reg_flips.append({
                        "capture_id": cid,
                        "span": f"{reg[0]['start']:.0f}-{reg[-1]['end']:.0f}s ({len(reg)} wins)",
                        "shipped_3072": f"{sh_c[0]} ({sh_p[0]:.2f})",
                        "uniform_1024_none": f"{m2_c[0]} ({m2_p[0]:.2f})",
                    })

    return {
        "field_labels_comparison": models_eval,
        "kept_human_call_labels_context": call_label_notes,
        "kept_29_region_replay": {
            "confident_regions_ge_0.25": conf_total,
            "confident_abstained_none_M2c": conf_none_m2,
            "candidate_regions_0.10_0.25": cand_total,
            "candidate_abstained_none_M2c": cand_none_m2,
            "shipped_3072_region_distribution": dict(sh_dist.most_common()),
            "uniform_1024_M2c_region_distribution": dict(m2_dist.most_common()),
            "multi_window_region_changes_sample": long_reg_flips[:15],
        },
    }


def main():
    run = Run("0121 unified retrain & raptor threshold validation", ["garbage_gate", "field_scan", "cv_and_eval"])
    with run.stage("garbage_gate") as stage:
        garbage_gate = scan_garbage_corvid_gate(stage)
    with run.stage("field_scan") as stage:
        scanned_field, cap_meta, labels = scan_field_captures(stage)

    with run.stage("cv_and_eval") as stage:
        stage.update(0, 3, extra="loading pools & BirdNET gate stats")
        pools = load_pools(garbage_gate)
        gb_conf = pools["gb_corvid_conf"]
        leaked_10 = gb_conf >= 0.10
        leaked_25 = gb_conf >= 0.25
        top_non_corvid_on_rest = Counter(
            t for t, m in zip(pools["gb_top_other"], ~leaked_10) if m and t
        ).most_common(8)

        upstream_gate_summary = {
            "n_garbage_segments_embedded": int(len(gb_conf)),
            "pass_birdnet_candidate_ge_0.10": int(leaked_10.sum()),
            "pass_birdnet_candidate_rate": round(float(leaked_10.mean()), 4),
            "pass_birdnet_confident_ge_0.25": int(leaked_25.sum()),
            "pass_birdnet_confident_rate": round(float(leaked_25.mean()), 4),
            "blocked_upstream_by_birdnet_lt_0.10_rate": round(float((~leaked_10).mean()), 4),
            "top_non_corvid_species_in_blocked_garbage": dict(top_non_corvid_on_rest),
        }

        stage.update(1, 3, extra="5-fold recording-grouped CV")
        cv_res = run_grouped_cv(pools)

        stage.update(2, 3, extra="raptor threshold calibration & field replay")
        raptor_cal = calibrate_raptor_thresholds(scanned_field, cap_meta)
        field_res = evaluate_field_and_replay(pools, scanned_field, cap_meta, labels)
        stage.update(3, 3)

    results = {
        "1_upstream_birdnet_gate_on_crowCount0": upstream_gate_summary,
        "2_grouped_cv_retrain_comparison": cv_res,
        "3_raptor_co_detection_threshold_calibration": raptor_cal,
        "4_field_labels_and_kept_replay": field_res,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({
        "1_upstream_birdnet_gate_on_crowCount0": upstream_gate_summary,
        "2_grouped_cv_summary": {
            k: {
                "garbage_all_572": v["garbage_all_572"],
                "garbage_leaked_ge_0.25": v["garbage_leaked_past_birdnet_ge_0.25"],
                "core4": v["crowtools_single_label_core4"],
                "co_occurrence": v["co_occurrence_multi_label_ct"],
                "within_archive_flight_auc": v["within_archive_flight_call_auc"],
                "per_class_auc_calls": {c: d["auc_calls_only"] for c, d in v["per_class"].items()},
                "per_class_ap_with_garbage": {c: d["ap_with_garbage"] for c, d in v["per_class"].items()},
            }
            for k, v in cv_res.items()
        },
        "3_raptor_archive_calibration": raptor_cal["archive_561_calibration"],
        "3_raptor_kept_counts": {k: v["n_kept_captures_firing"] for k, v in raptor_cal["kept_29_captures"].items()},
        "4_kept_replay": field_res["kept_29_region_replay"],
    }, indent=2))
    run.note(
        f"upstream_leak>=0.25={upstream_gate_summary['pass_birdnet_confident_rate']} ({upstream_gate_summary['pass_birdnet_confident_ge_0.25']}/572)"
    )


if __name__ == "__main__":
    main()
