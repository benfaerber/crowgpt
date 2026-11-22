"""Experiment 0104 — pure-crow masking, recording-level embeddings and caw features for the video clip set.

Reads the clip manifest under data/experiments/0104-perched-posture/ (clips are
identified here by an opaque key only), applies exactly 0103's masking — pure-crow
3 s windows, and a recording-level raptor confidence for the strict set — and
writes features and per-clip records back under data/.

Runs on CPU in the BirdNET venv:
  pipelines/representation/.venv-birdnet/bin/python \
      experiments/0104-does-owl-vs-hawk-survive-perched/extract.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import librosa
import numpy as np

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
OUT_DIR = DATA_DIR / "experiments" / "0104-perched-posture"
MAX_AUDIO_S = 150.0

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "experiments" / "0102-archive-remarks-semantics"))
sys.path.insert(0, str(REPO / "experiments" / "0103-caw-level-and-posture-controls"))
from crowgpt.progress import Run  # noqa: E402
import run as exp102  # noqa: E402
import extract_caws as exp103  # noqa: E402

_ANALYZER = None
_DEVNULL = None


def _init_worker():
    global _ANALYZER, _DEVNULL
    _DEVNULL = open(os.devnull, "w")
    from birdnetlib.analyzer import Analyzer

    with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
        _ANALYZER = Analyzer()


class ClipExtractor:
    """One clip in, masked windows, covariates, mean embeddings and caw features out."""

    def __init__(self, key: str, audio_path: str):
        self.key = key
        self.audio_path = audio_path

    def run(self) -> dict:
        from birdnetlib import Recording

        try:
            with contextlib.redirect_stdout(_DEVNULL), contextlib.redirect_stderr(_DEVNULL):
                rec = Recording(_ANALYZER, self.audio_path, min_conf=0.05)
                rec.analyze()
                rec.extract_embeddings()
        except Exception as ex:  # noqa: BLE001
            return {"key": self.key, "ok": False, "error": str(ex)[:200]}
        segs = rec.embeddings or []
        if not segs:
            return {"key": self.key, "ok": False, "error": "no embeddings"}

        win_crow = defaultdict(float)
        win_noncrow = defaultdict(int)
        bystanders = Counter()
        raptors = set()
        max_raptor = 0.0
        for det in rec.detections or []:
            win = (round(float(det["start_time"]), 2), round(float(det["end_time"]), 2))
            common, sci = det.get("common_name", ""), det.get("scientific_name", "")
            conf = float(det["confidence"])
            if exp103._is_american_crow(common, sci):
                win_crow[win] = max(win_crow[win], conf)
                continue
            win_noncrow[win] += 1
            bystanders[common] += 1
            if exp102._is_raptor(common, sci):
                max_raptor = max(max_raptor, conf)
                raptors.add(common)

        pure_w, pure_e, crow_e = [], [], []
        for s in segs:
            emb = np.asarray(s["embeddings"], dtype=np.float32)
            if not np.isfinite(emb).all():
                continue
            win = (round(float(s["start_time"]), 2), round(float(s["end_time"]), 2))
            if win_crow.get(win, 0.0) >= 0.25:
                crow_e.append(emb)
                if not win_noncrow.get(win):
                    pure_w.append(win)
                    pure_e.append(emb)

        try:
            y, sr = librosa.load(self.audio_path, sr=22050, mono=True, duration=MAX_AUDIO_S)
        except Exception as ex:  # noqa: BLE001
            return {"key": self.key, "ok": False, "error": f"load failed: {ex}"[:200]}

        prosody = (
            exp102.extract_prosody(y, sr, pure_w) if pure_w
            else np.zeros(len(exp102.PROSODY_NAMES), dtype=np.float32)
        )
        caws = exp103.segment_caws_in_windows(y, sr, pure_w, max_caws=30)
        caw_feats = [
            exp103.extract_caw_44d(y[max(0, int(round(c["onset"] * sr))): min(len(y), int(round(c["offset"] * sr)))], sr)
            for c in caws
        ]
        return {
            "key": self.key,
            "ok": True,
            "duration_s": round(len(y) / sr, 2),
            "n_segs": len(segs),
            "n_crow_w": len(crow_e),
            "n_pure_crow_w": len(pure_w),
            "pure_crow_frac": round(len(pure_w) / max(len(segs), 1), 4),
            "duty_cycle": round(float(prosody[5]), 4),
            "max_raptor_conf": round(max_raptor, 4),
            "raptor_species": sorted(raptors),
            "bystander_species": dict(bystanders.most_common(8)),
            "n_caws": len(caws),
            "emb_pure_mean": np.mean(np.stack(pure_e), axis=0).astype(np.float32) if pure_e else None,
            "emb_crow_mean": np.mean(np.stack(crow_e), axis=0).astype(np.float32) if crow_e else None,
            "caw_feats": np.stack(caw_feats).astype(np.float32) if caw_feats else np.zeros((0, 44), dtype=np.float32),
        }


def _process(task: tuple[str, str]) -> dict:
    return ClipExtractor(*task).run()


class FeatureStore:
    """Collects per-clip results into records.json and features.npz."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def write(self, results: list[dict]) -> None:
        results = sorted((r for r in results if r.get("ok")), key=lambda r: r["key"])
        zero = np.zeros(1024, dtype=np.float32)
        records, caw_x, caw_rec = [], [], []
        for i, r in enumerate(results):
            records.append({k: v for k, v in r.items() if k not in ("emb_pure_mean", "emb_crow_mean", "caw_feats", "ok")})
            for row in r["caw_feats"]:
                caw_x.append(row)
                caw_rec.append(i)
        (self.out_dir / "records.json").write_text(json.dumps(records, indent=1))
        np.savez_compressed(
            self.out_dir / "features.npz",
            keys=np.array([r["key"] for r in results]),
            emb_pure_mean=np.stack([r["emb_pure_mean"] if r["emb_pure_mean"] is not None else zero for r in results]),
            emb_crow_mean=np.stack([r["emb_crow_mean"] if r["emb_crow_mean"] is not None else zero for r in results]),
            has_pure=np.array([r["emb_pure_mean"] is not None for r in results]),
            caw_x=np.stack(caw_x) if caw_x else np.zeros((0, 44), dtype=np.float32),
            caw_rec=np.array(caw_rec, dtype=np.int32),
        )


def main():
    manifest = json.loads((OUT_DIR / "manifest.json").read_text())
    tasks = [(m["key"], m["file"]) for m in manifest if Path(m["file"]).exists()]
    run = Run("0104 perched posture masking + features", ["extract"])
    results, failed = [], 0
    with run.stage("extract") as st, ProcessPoolExecutor(max_workers=10, initializer=_init_worker) as ex:
        futs = [ex.submit(_process, t) for t in tasks]
        for k, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            failed += not r.get("ok")
            if k % 10 == 0 or k == len(tasks):
                st.update(k, len(tasks), extra=f"failed={failed}")
    FeatureStore(OUT_DIR).write(results)
    usable = sum(1 for r in results if r.get("ok") and r["n_pure_crow_w"] >= 1)
    run.note(f"{len(results) - failed}/{len(tasks)} clips extracted; {usable} with >=1 pure-crow window")
    print(f"extracted {len(results) - failed}/{len(tasks)}; usable (>=1 pure-crow window) = {usable}")


if __name__ == "__main__":
    main()
