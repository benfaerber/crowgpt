"""0077's validation: ct2 against b32's paired baseline (0075's results.json).

Same instruments and seeds as 0074/0075; the pairing is the seeds.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"))

from crowgpt.gpu import claim

claim()

import numpy as np
import torch

from crowgpt.birdnet import BirdNet
from crowgpt.calltype import CORE, BoutCallTypes, human_labels, label_bouts
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore
from lib.dustprobe import DUST_THRESHOLD, clip_features

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
BASELINE = json.loads(
    (REPO / "experiments" / "0075-does-the-batch-the-recipe-claimed-matter" /
     "results.json").read_text())
MODEL = HERE / "results" / "model-longctx-ct2" / "model.pt"
SPECIES = "american-crow"
PER_TYPE = 60
SAMPLING = {"temperature": 1.1, "top_k": 200, "max_frames": 460}


def stats_of(seg, audio):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, seg.floor_pctl)
    bursts = seg.bursts(db, fps, floor)
    gaps = [(b[0] - a[1]) / fps for a, b in zip(bursts, bursts[1:])]
    return len(bursts), gaps


def describe(rows, feats):
    units = np.array([r[0] for r in rows])
    gaps = [g for r in rows for g in r[1]]
    return {
        "n": len(rows), "mean_units": round(float(units.mean()), 2),
        "single_share": round(float((units <= 1).mean()), 3),
        "gaps_per_clip": round(len(gaps) / len(rows), 2),
        "median_gap_s": round(float(np.median(gaps)), 3) if gaps else None,
        "dust_rate": round(float(np.mean(
            [p <= DUST_THRESHOLD for p in feats])), 3) if feats else None,
    }


def main():
    run = Run("0077 — CT2 VALIDATION", ["anchor", "generate", "judge", "verdict"])
    report = {"baseline": "0075 results.json (b32)"}
    seg = Segmenter()
    try:
        store = BoutStore(DATA / "bouts-6s")
        splits = store.split(seed=0)
        where = {i: n for n, idx in splits.items() for i in idx}
        tagged = label_bouts(store.index, human_labels())
        train_tagged = {i: t for i, t in tagged.items() if where[i] == "train"}
        held_out = {i: t for i, t in tagged.items() if where[i] != "train"}
        birdnet = BirdNet(sample_rate=24000)

        def embed_positions(positions, stage, tag):
            vectors, kept = [], []
            for start in range(0, len(positions), 400):
                chunk = positions[start:start + 400]
                got, index = birdnet.embed_indexed(
                    [normalise(store.audio(store.index[p])) for p in chunk])
                if len(got):
                    vectors.append(got)
                    kept.extend(chunk[j] for j in index)
                stage.update(min(start + 400, len(positions)), len(positions),
                             extra=tag)
            return (np.concatenate(vectors) if vectors
                    else np.zeros((0, 1024))), kept

        with run.stage("anchor") as stage:
            train_x, train_pos = embed_positions(sorted(train_tagged), stage,
                                                 "train")
            head = BoutCallTypes()
            head.fit(train_x, [train_tagged[p] for p in train_pos])
            held_x, held_pos = embed_positions(sorted(held_out), stage, "held")
            truth = [held_out[p] for p in held_pos]
            guess, _ = head.forced(held_x)
            report["anchor_accuracy"] = round(
                sum(t == g for t, g in zip(truth, guess)) / len(truth), 3)

        with run.stage("generate") as stage:
            sampler = Sampler(MODEL, decoder_state="finetuned")
            wanted, clips, structure = [], [], {}
            done = 0
            for call_type in CORE:
                rows, feats = [], []
                for i in range(PER_TYPE):
                    audio = sampler.audio(SPECIES, call_type=call_type,
                                          seed=41_000 + i, **SAMPLING)
                    clips.append(audio)
                    wanted.append(call_type)
                    rows.append(stats_of(seg, audio))
                    f = clip_features(seg, normalise(audio), SAMPLE_RATE)
                    if f:
                        feats.append(f["pitch_strength"])
                    done += 1
                    stage.update(done, len(CORE) * PER_TYPE, extra=call_type)
                structure[call_type] = describe(rows, feats)
            report["serving_structure"] = structure
            del sampler
            torch.cuda.empty_cache()

        with run.stage("judge") as stage:
            generated_x, index = birdnet.embed_indexed(clips)
            kept = [wanted[i] for i in index]
            guess, _ = head.forced(generated_x)
            report["recall"] = {}
            for core in CORE:
                pairs = [(w, g) for w, g in zip(kept, guess) if w == core]
                report["recall"][core] = round(
                    sum(w == g for w, g in pairs) / len(pairs), 3) if pairs else None
            stage.update(1, 1)

        with run.stage("verdict") as stage:
            b32_val = json.loads((HERE / "results" / "model-longctx-ct-b32" /
                                  "history.json").read_text())["best_val"]
            ct2_val = json.loads((HERE / "results" / "model-longctx-ct2" /
                                  "history.json").read_text())["best_val"]
            alarm_ok = (report["recall"]["alarm call"] or 0) >= \
                (BASELINE["recall"]["alarm call"] - 0.05)
            base_alarm = BASELINE["serving_structure"]["alarm call"]
            mine_alarm = report["serving_structure"]["alarm call"]
            struct_ok = all(
                mine_alarm[k] is not None and base_alarm[k]
                and abs(mine_alarm[k] - base_alarm[k]) / base_alarm[k] <= 0.15
                for k in ("mean_units", "gaps_per_clip"))
            report["verdict"] = {
                "val_b32": b32_val, "val_ct2": ct2_val,
                "val_improved": ct2_val < b32_val,
                "alarm_recall_held": alarm_ok,
                "serving_structure_held": struct_ok,
                "ct2_becomes_candidate": bool(alarm_ok and struct_ok),
            }
            stage.say(json.dumps(report["verdict"]))
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
