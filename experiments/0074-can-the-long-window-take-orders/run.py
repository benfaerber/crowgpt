"""0074's gate: did the long window take orders, and at what cost?

Three instruments against model-longctx-ct, each borrowed whole:

- 0021's conditioning harness — anchor a BirdNET+logistic head on held-out
  human bouts nothing has trained on, then forced-choice the head over 60
  generated clips per requested type. Alarm is the only well-anchored class;
  call and song are reported, never gated (n=3 / n=5 anchors).
- 0067's structure metrics — units/bout, single share, gaps — both arms drawn
  fresh at the serving cell (T 1.1 / k 200 / 460 frames) so the comparison is
  within-run and within-condition, not against numbers sampled differently.
- 0069's dust probe on the same draws, relative and same-decoder only.

The adopt/reject thresholds live in the README, written before this ran.
"""
import json
import sys
import time
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
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore
from lib.dustprobe import DUST_THRESHOLD, clip_features

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SPECIES = "american-crow"
PER_TYPE = 60
N_DRAWS, N_REAL = 100, 200
SAMPLING = {"temperature": 1.1, "top_k": 200}
CT_MODEL = HERE / "results" / "model-longctx-ct" / "model.pt"
ARMS = {
    "model-longctx": HERE / "results" / "model-longctx" / "model.pt",
    "model-longctx-ct": CT_MODEL,
}


def matrix(requested, detected, rows, columns):
    table = {r: {c: 0 for c in columns} for r in rows}
    for want, got in zip(requested, detected):
        table[want][got] += 1
    return table


def stats_of(seg, audio):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, seg.floor_pctl)
    bursts = seg.bursts(db, fps, floor)
    gaps = [(b[0] - a[1]) / fps for a, b in zip(bursts, bursts[1:])]
    return len(bursts), gaps


def describe(rows):
    units = np.array([r[0] for r in rows])
    gaps = [g for r in rows for g in r[1]]
    return {
        "n": len(rows), "mean_units": round(float(units.mean()), 2),
        "single_share": round(float((units <= 1).mean()), 3),
        "gaps_per_clip": round(len(gaps) / len(rows), 2),
        "median_gap_s": round(float(np.median(gaps)), 3) if gaps else None,
    }


def main():
    run = Run("0074 — CAN THE LONG WINDOW TAKE ORDERS",
              ["anchor", "generate", "judge", "structure", "verdict"])
    report = {}
    seg = Segmenter()
    try:
        store = BoutStore(DATA / "bouts-6s")
        splits = store.split(seed=0)
        where = {i: n for n, idx in splits.items() for i in idx}
        tagged = label_bouts(store.index, human_labels())
        train_tagged = {i: t for i, t in tagged.items() if where[i] == "train"}
        held_out = {i: t for i, t in tagged.items() if where[i] != "train"}
        birdnet = BirdNet(sample_rate=24000)

        def embed(positions, stage, tag):
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
            train_x, train_pos = embed(sorted(train_tagged), stage, "train")
            head = BoutCallTypes()
            fitted = head.fit(train_x, [train_tagged[p] for p in train_pos])
            held_x, held_pos = embed(sorted(held_out), stage, "held out")
            truth = [held_out[p] for p in held_pos]
            guess, confidence = head.forced(held_x)
            majority = Counter(truth).most_common(1)[0]
            report["anchor"] = {
                "n": len(truth),
                "accuracy": round(sum(t == g for t, g in zip(truth, guess))
                                  / len(truth), 3),
                "majority_baseline": round(majority[1] / len(truth), 3),
                "truth_mix": dict(Counter(truth)),
                "matrix": matrix(truth, guess, list(CORE), list(head.classes)),
            }
            stage.say(f"anchor {report['anchor']['accuracy']:.1%} vs "
                      f"{report['anchor']['majority_baseline']:.1%} always-{majority[0]}")

        with run.stage("generate") as stage:
            sampler = Sampler(CT_MODEL, decoder_state="finetuned")
            wanted, clips, made = [], [], 0
            for call_type in CORE:
                for i in range(PER_TYPE):
                    clips.append(sampler.audio(
                        SPECIES, call_type=call_type, seed=41_000 + i,
                        max_frames=460, **SAMPLING))
                    wanted.append(call_type)
                    made += 1
                    stage.update(made, len(CORE) * PER_TYPE, extra=call_type)
            del sampler
            torch.cuda.empty_cache()

        with run.stage("judge") as stage:
            generated_x, index = birdnet.embed_indexed(clips)
            kept = [wanted[i] for i in index]
            guess, _ = head.forced(generated_x)
            per_type = {}
            for core in CORE:
                pairs = [(w, g) for w, g in zip(kept, guess) if w == core]
                per_type[core] = round(sum(w == g for w, g in pairs)
                                       / len(pairs), 3) if pairs else None
            report["conditioning"] = {
                "embedded": len(kept),
                "recall": per_type,
                "matrix": matrix(kept, guess, list(CORE), list(head.classes)),
            }
            stage.say(" · ".join(f"{c} {per_type[c]:.0%}" for c in CORE
                                 if per_type[c] is not None))

        with run.stage("structure") as stage:
            arms, raw = {}, {}
            total = len(ARMS) * N_DRAWS + N_REAL
            done = 0
            for arm, ckpt in ARMS.items():
                sampler = Sampler(ckpt, token_dir=None, decoder_state="finetuned")
                rows, feats, seed = [], [], 0
                while len(rows) < N_DRAWS and seed < N_DRAWS * 6:
                    flat = sampler.tokens(SPECIES, seed=seed, max_frames=460,
                                          **SAMPLING)
                    grid = sampler.codec.unflatten(flat)
                    audio = np.asarray(sampler.codec.decode(
                        torch.from_numpy(grid))[0], dtype=np.float32)
                    if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
                        rows.append(stats_of(seg, audio))
                        f = clip_features(seg, normalise(audio), SAMPLE_RATE)
                        if f:
                            feats.append(f["pitch_strength"])
                        done += 1
                        stage.update(done, total, extra=arm)
                    seed += 1
                arms[arm] = describe(rows)
                arms[arm]["dust_rate"] = round(
                    float(np.mean([p <= DUST_THRESHOLD for p in feats])), 3)
                raw[arm] = rows
                del sampler
                torch.cuda.empty_cache()

            seen, rows = set(), []
            for i in splits["test"]:
                r = store.index[i]
                if r["species"] != SPECIES or r["recording_id"] in seen \
                        or r["n_samples"] < SAMPLE_RATE:
                    continue
                seen.add(r["recording_id"])
                rows.append(stats_of(seg, normalise(store.audio(r))))
                done += 1
                stage.update(done, total, extra="real")
                if len(rows) >= N_REAL:
                    break
            arms["real"] = describe(rows)
            report["structure"] = arms

        with run.stage("verdict") as stage:
            recall = report["conditioning"]["recall"]
            inc, ct = report["structure"]["model-longctx"], \
                report["structure"]["model-longctx-ct"]
            within = {}
            for key in ("mean_units", "single_share", "gaps_per_clip",
                        "median_gap_s"):
                a, b = inc[key], ct[key]
                within[key] = (round(abs(b - a) / a, 3)
                               if a not in (None, 0) and b is not None else None)
            gate = {
                "alarm_recall_ge_80": recall["alarm call"] is not None
                                      and recall["alarm call"] >= 0.80,
                "begging_above_chance": recall["begging"] is not None
                                        and recall["begging"] > 0.25,
                "structure_within_15pct": all(
                    v is not None and v <= 0.15 for v in within.values()),
                "dust_no_worse": ct["dust_rate"] <= inc["dust_rate"],
            }
            report["gate"] = {"checks": gate, "structure_deltas": within,
                              "adopt": all(gate.values())}
            stage.say("ADOPT" if report["gate"]["adopt"] else
                      "HOLD — " + ", ".join(k for k, v in gate.items() if not v))
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
