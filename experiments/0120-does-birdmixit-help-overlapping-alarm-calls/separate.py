"""0120 step 1 (GPU/TF1): compute OOF crowd gate and separate multi-crow / high-P_several
3.0 s crow-tools windows with pretrained BirdMixIT (output_sources4).

    pipelines/representation/perch/.venv/bin/python \
        experiments/0120-does-birdmixit-help-overlapping-alarm-calls/separate.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import warnings
from collections import defaultdict
from importlib import util
from pathlib import Path

os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
warnings.filterwarnings("ignore")

import librosa  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import StratifiedGroupKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
CACHE = DATA_DIR / "experiments" / "0120-birdmixit-alarms"
EXP0036 = REPO / "experiments" / "0036-what-would-more-labels-buy" / "results"
EXP0118 = REPO / "experiments" / "0118-demixing-overlapping-mobs"

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
sys.path.insert(0, str(REPO / "pipelines" / "ingest"))
from crowgpt.progress import Run  # noqa: E402

T_SINGLE = 0.5826
SR = 22050
WIN_SAMPLES = int(3.0 * SR)


def load_module(name: str, path: Path):
    spec = util.spec_from_file_location(name, path)
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    run = Run("0120 BirdMixIT crow-tools separation", ["crowd_oof", "separate"])

    keyed = np.load(EXP0036 / "crowtools_keyed.npz", allow_pickle=True)
    flags_map = {r["key"]: r["flags"] for r in json.loads((EXP0036 / "crowtools_flags.json").read_text())}
    groups = keyed["groups"]
    starts = keyed["starts"]
    X1024 = keyed["X"][:, :1024].astype(np.float32)
    flags = [flags_map[f"{g}-{s}"] for g, s in zip(groups, starts)]
    counts = np.array([int(f.get("crowCount") or 0) for f in flags], dtype=int)

    with run.stage("crowd_oof") as stage:
        # Compute strictly out-of-fold P_several across the 2,338 segments (grouped by recording)
        valid = counts >= 1
        y_sev = (counts[valid] >= 2).astype(int)
        X_val = X1024[valid]
        g_val = groups[valid]
        oof_valid = np.zeros(len(y_sev), dtype=np.float32)
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
        models_fold = []
        fold_test_groups = []
        for tr, te in cv.split(X_val, y_sev, g_val):
            m = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000),
            ).fit(X_val[tr], y_sev[tr])
            oof_valid[te] = m.predict_proba(X_val[te])[:, 1]
            models_fold.append(m)
            fold_test_groups.append(set(g_val[te].tolist()))

        p_several_oof = np.zeros(len(counts), dtype=np.float32)
        p_several_oof[valid] = oof_valid
        # Score the 9 crowCount==0 rows using the fold matching their group (or full fit if group unseen)
        full_m = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.05, class_weight="balanced", max_iter=3000),
        ).fit(X_val, y_sev)
        for idx in np.flatnonzero(~valid):
            g = str(groups[idx])
            matched = [m for m, gset in zip(models_fold, fold_test_groups) if g in gset]
            clf_use = matched[0] if matched else full_m
            p_several_oof[idx] = float(clf_use.predict_proba(X1024[idx : idx + 1])[0, 1])

        np.save(CACHE / "p_several_oof.npy", p_several_oof)
        stage.update(1, 1, extra=f"gated={int((p_several_oof >= T_SINGLE).sum())}, true2+={int((counts >= 2).sum())}")

    stems_cache = CACHE / "stems_22k.npz"
    if stems_cache.exists():
        print("stems_22k.npz already cached.")
        run.note("stems_22k.npz reused")
        return

    from corpus import LabelCorpus

    audio_idx = LabelCorpus(dataset="all-public").audio_index()
    # Collect unique (file_id, aligned_start) windows needing separation (gated OR oracle crowCount>=2)
    need_by_file: dict[str, set[int]] = defaultdict(set)
    row_to_wkey: list[str] = []
    for idx, (g, s) in enumerate(zip(groups, starts)):
        aligned = 3 * (int(s) // 3)
        wkey = f"{g}:{aligned}"
        row_to_wkey.append(wkey)
        if p_several_oof[idx] >= T_SINGLE or counts[idx] >= 2:
            need_by_file[str(g)].add(aligned)

    (CACHE / "row_wkeys.json").write_text(json.dumps(row_to_wkey))

    sep_mod = load_module("sep0118", EXP0118 / "separate.py")
    sep = sep_mod.BirdMixITSeparator()

    wkeys_out: list[str] = []
    s1_out: list[np.ndarray] = []
    s2_out: list[np.ndarray] = []
    total_wins = sum(len(v) for v in need_by_file.values())
    done_wins = 0
    missing_files = 0

    with run.stage("separate") as stage:
        stage.update(0, total_wins)
        for file_id, aligned_set in sorted(need_by_file.items()):
            found = audio_idx.get(file_id)
            if found is None or not Path(found[1]).exists():
                missing_files += 1
                done_wins += len(aligned_set)
                continue
            path = str(found[1])
            try:
                with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
                    y, _ = librosa.load(path, sr=SR, mono=True)
            except Exception:  # noqa: BLE001
                missing_files += 1
                done_wins += len(aligned_set)
                continue

            waves, keys_here = [], []
            for aligned in sorted(aligned_set):
                lo = int(aligned * SR)
                if lo + SR // 2 > len(y):
                    lo = max(0, len(y) - WIN_SAMPLES)
                seg = y[lo : lo + WIN_SAMPLES].astype(np.float32)
                if len(seg) < WIN_SAMPLES:
                    seg = np.pad(seg, (0, WIN_SAMPLES - len(seg)))
                waves.append(seg)
                keys_here.append(f"{file_id}:{aligned}")

            if waves:
                stems4 = sep.separate_batch(np.stack(waves))
                for wk, st4 in zip(keys_here, stems4):
                    top = sep_mod.select_top_stems(st4, min_rel_rms=0.15, max_stems=2)
                    st1 = top[0]
                    st2 = top[1] if len(top) > 1 else top[0]
                    wkeys_out.append(wk)
                    s1_out.append(st1.astype(np.float16))
                    s2_out.append(st2.astype(np.float16))
            done_wins += len(aligned_set)
            if done_wins % 20 == 0 or done_wins == total_wins:
                stage.update(done_wins, total_wins, extra=f"kept={len(wkeys_out)} miss={missing_files}")

    np.savez_compressed(
        stems_cache,
        wkeys=np.array(wkeys_out),
        stem1=np.stack(s1_out),
        stem2=np.stack(s2_out),
    )
    run.note(f"separated {len(wkeys_out)}/{total_wins} unique 3s windows (missing_files={missing_files})")
    print(f"Saved {len(wkeys_out)} separated windows -> {stems_cache}")


if __name__ == "__main__":
    main()
