"""0117 step 2: BirdNET window scan + Perch 2.0 window embeddings for witnessed non-American Corvus
recordings (plus 0102's 9 witnessed American Crow mammal_scold recordings so Primary B uses identical windows).

    # Step 2a (CPU):
    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0117-cross-corvus-predator-and-posture/scan_and_embed.py --birdnet

    # Step 2b (GPU, ~2 GB VRAM with allow_growth):
    pipelines/representation/perch/.venv/bin/python \
        experiments/0117-cross-corvus-predator-and-posture/scan_and_embed.py --perch
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import util
from pathlib import Path

os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE_DIR = DATA_DIR / "experiments" / "0117-cross-corvus"
WIN_DIR = CACHE_DIR / "windows"
PERCH_OUT = CACHE_DIR / "perch.npz"
DB_PATH = DATA_DIR / "corvid.db"

os.environ.setdefault("KAGGLEHUB_CACHE", str(DATA_DIR / "models"))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

SLUG_TERMS = {
    "hooded-crow": ("hooded crow", "carrion crow", "corvus cornix", "corvus corone"),
    "carrion-crow": ("carrion crow", "hooded crow", "corvus corone", "corvus cornix"),
    "common-raven": ("common raven", "corvus corax"),
    "eurasian-jackdaw": ("eurasian jackdaw", "western jackdaw", "coloeus monedula", "corvus monedula"),
    "rook": ("rook", "corvus frugilegus"),
    "large-billed-crow": ("large-billed crow", "jungle crow", "corvus macrorhynchos"),
    "american-crow": ("american crow", "northwestern crow", "corvus brachyrhynchos"),
}

_ANALYZER = None
_EXP102 = None


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _init_birdnet_worker():
    global _ANALYZER, _EXP102
    from birdnetlib.analyzer import Analyzer

    _EXP102 = load_module("exp102_0117", REPO / "experiments" / "0102-archive-remarks-semantics" / "run.py")
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        _ANALYZER = Analyzer()


def resolve_audio_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        return p
    if "/data/" in raw:
        cand = DATA_DIR / raw.split("/data/", 1)[1]
        if cand.exists():
            return cand
    return None


def target_recordings() -> list[dict]:
    labs = json.loads((HERE / "labels.json").read_text())["labels"]
    witnessed = [r for r in labs if r.get("witnessed") and r.get("context") != "none"]
    # Also include 0102's witnessed American Crow mammal_scold + human_disturbance for Primary B
    labs_102 = json.loads((REPO / "experiments" / "0102-archive-remarks-semantics" / "labels.json").read_text())
    for r in labs_102:
        if r.get("slug") == "american-crow" and r.get("witnessed") and r.get("context") in ("mammal_scold", "human_disturbance"):
            witnessed.append({
                "id": r["id"],
                "slug": "american-crow",
                "context": r["context"],
                "witnessed": True,
                "posture": "unknown",
                "pred_vocal": bool(r.get("pred_vocal")),
            })
    ids = sorted({r["id"] for r in witnessed})
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    paths = {
        rid: resolve_audio_path(fp)
        for rid, fp in con.execute(f"SELECT id, file_path FROM recordings WHERE id IN ({','.join(map(str, ids))})").fetchall()
    }
    con.close()
    out = []
    seen = set()
    for r in witnessed:
        rid = r["id"]
        if rid in seen or paths.get(rid) is None:
            continue
        seen.add(rid)
        out.append({"id": rid, "key": f"c{rid}", "slug": r["slug"], "path": str(paths[rid])})
    return out


def _scan_one(task: tuple[str, str, str]) -> tuple[str, str | None]:
    key, slug, path = task
    from birdnetlib import Recording

    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            rec = Recording(_ANALYZER, path, min_conf=0.05)
            rec.analyze()
            rec.extract_embeddings()
    except Exception as exc:  # noqa: BLE001
        return key, str(exc)[:200]

    terms = SLUG_TERMS.get(slug, ())
    scores = defaultdict(lambda: np.zeros(5, dtype=np.float32))
    # cols: [0]=corvid, [1]=target_species, [2]=raptor, [3]=non_corvid, [4]=non_target
    for det in rec.detections or []:
        win = round(float(det["start_time"]), 2)
        cn, sn = det.get("common_name", ""), det.get("scientific_name", "")
        text = f"{cn} {sn}".lower()
        conf = float(det["confidence"])
        row = scores[win]
        is_corv = _EXP102._is_corvid(cn, sn)
        is_targ = any(t in text for t in terms)
        if is_corv:
            row[0] = max(row[0], conf)
        else:
            row[3] = max(row[3], conf)
        if is_targ:
            row[1] = max(row[1], conf)
        else:
            row[4] = max(row[4], conf)
        if _EXP102._is_raptor(cn, sn):
            row[2] = max(row[2], conf)
        # Additional European owl/raptor scientific-name guard (Strix, Bubo, Asio, Athene, Glaucidium, Tyto, Accipiter, Buteo, Milvus, Circus, Falco, Aquila, Haliaeetus, Pandion, Pernis)
        if any(g in text for g in ("strix", "bubo", "asio", "athene", "glaucidium", "tyto", "accipiter", "buteo", "milvus", "circus", "falco", "aquila", "haliaeetus", "pandion", "pernis")):
            row[2] = max(row[2], conf)

    starts, mat, embs = [], [], []
    for seg in rec.embeddings or []:
        emb = np.asarray(seg["embeddings"], dtype=np.float32)
        if not np.isfinite(emb).all():
            continue
        st_t = round(float(seg["start_time"]), 2)
        starts.append(st_t)
        mat.append(scores.get(st_t, np.zeros(5, dtype=np.float32)))
        embs.append(emb)
    if not starts:
        return key, "no windows"
    mat_arr = np.stack(mat)
    np.savez(
        WIN_DIR / f"{key}.npz",
        start=np.array(starts, dtype=np.float32),
        corvid=mat_arr[:, 0],
        target_species=mat_arr[:, 1],
        raptor=mat_arr[:, 2],
        non_corvid=mat_arr[:, 3],
        non_target=mat_arr[:, 4],
        embedding=np.stack(embs).astype(np.float32),
    )
    return key, None


def run_birdnet():
    WIN_DIR.mkdir(parents=True, exist_ok=True)
    recs = target_recordings()
    tasks = [(r["key"], r["slug"], r["path"]) for r in recs if not (WIN_DIR / f"{r['key']}.npz").exists()]
    run = Run("0117 cross-Corvus BirdNET scan", ["scan"])
    failures = {}
    with run.stage("scan") as st:
        st.update(0, max(len(tasks), 1), extra=f"{len(recs) - len(tasks)} cached")
        if tasks:
            with ProcessPoolExecutor(max_workers=10, initializer=_init_birdnet_worker) as pool:
                futs = [pool.submit(_scan_one, t) for t in tasks]
                for done, fut in enumerate(as_completed(futs), 1):
                    k, err = fut.result()
                    if err:
                        failures[k] = err
                    if done % 10 == 0 or done == len(tasks):
                        st.update(done, len(tasks), extra=f"{len(failures)} failed")
        else:
            st.update(1, 1)
    msg = f"total={len(recs)}, newly_scanned={len(tasks) - len(failures)}/{len(tasks)}, failures={len(failures)}"
    run.note(msg)
    print(msg)


def run_perch():
    import librosa
    from perch_hoplite.zoo import model_configs

    SR = 32000
    WINDOW = 5 * SR
    BATCH = 16  # gentle VRAM footprint alongside background render

    recs = target_recordings()
    done = {}
    if PERCH_OUT.exists():
        saved = np.load(PERCH_OUT)
        done = dict(zip(saved["ids"].tolist(), saved["embeddings"]))

    todo_by_file = defaultdict(list)
    total_spans = 0
    for r in recs:
        wpath = WIN_DIR / f"{r['key']}.npz"
        if not wpath.exists():
            continue
        d = np.load(wpath)
        corvid_mask = (d["corvid"] >= 0.25) | (d["target_species"] >= 0.25)
        for s in d["start"][corvid_mask]:
            sid = f"{r['key']}@{float(s):.2f}"
            if sid not in done:
                todo_by_file[r["path"]].append((sid, float(s), float(s) + 3.0))
                total_spans += 1

    run = Run("0117 cross-Corvus Perch embeddings", ["embed"])
    if total_spans == 0:
        with run.stage("embed") as st:
            st.update(1, 1, extra=f"all {len(done)} cached")
        run.note(f"all {len(done)} spans cached")
        print(f"All {len(done)} Perch spans already cached.")
        return

    model = model_configs.load_model_by_name("perch_v2")
    finished = 0
    with run.stage("embed") as st:
        st.update(0, total_spans)
        for path, spans in todo_by_file.items():
            try:
                samples, _ = librosa.load(path, sr=SR, mono=True, duration=300.0)
            except Exception as exc:  # noqa: BLE001
                print(f"skip {path}: {exc}")
                finished += len(spans)
                continue
            for i in range(0, len(spans), BATCH):
                chunk = spans[i : i + BATCH]
                batch = np.zeros((BATCH, WINDOW), dtype=np.float32)
                for j, (_, s0, s1) in enumerate(chunk):
                    centre = int((s0 + s1) / 2 * SR)
                    lo = centre - WINDOW // 2
                    src_lo, src_hi = max(0, lo), min(len(samples), lo + WINDOW)
                    if src_hi > src_lo:
                        batch[j, src_lo - lo : src_hi - lo] = samples[src_lo:src_hi]
                embs = np.asarray(model.batch_embed(batch).embeddings, dtype=np.float32).reshape(BATCH, -1)
                for (sid, _, _), emb in zip(chunk, embs):
                    if np.isfinite(emb).all():
                        done[sid] = emb.astype(np.float16)
                finished += len(chunk)
            st.update(finished, total_spans, extra=f"{len(done)} spans")
    if done:
        np.savez(PERCH_OUT, ids=np.array(list(done)), embeddings=np.stack(list(done.values())))
    run.note(f"{len(done)} Perch spans embedded")
    print(f"Embedded {len(done)} Perch spans.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--birdnet", action="store_true")
    parser.add_argument("--perch", action="store_true")
    args = parser.parse_args()
    if args.birdnet:
        run_birdnet()
    if args.perch:
        run_perch()


if __name__ == "__main__":
    main()
