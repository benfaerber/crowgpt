"""Ask the conditioned generator for each call type, and check what came out.

0018 established the path was open and ended with a list of things not done.
They are done now: a head trained on bouts labelled the corpus, the sequence
prefix grew a call-type token, and an 18M model trained on it. This asks the
only question that was ever the point — request an alarm call, and does an alarm
call arrive?

TWO MEASUREMENTS, AND THE FIRST IS WHAT MAKES THE SECOND MEAN ANYTHING. A head
that cannot classify REAL bouts tells us nothing about generated ones, and a
confusion matrix from a broken judge looks exactly like a generator that ignores
its conditioning. So the head is first scored on the 198 human-labelled bouts in
the generator's test split, which neither the head nor the generator has seen.
That number is the ceiling. Only then is the same head pointed at generated
audio.

FORCED CHOICE, NOT THRESHOLDED. `predict` abstains below 0.60 because a wrong
pseudo-label is expensive when labelling 57,000 bouts. Here abstention would
hide the answer, so `forced` is used for both halves and the confidence is
reported separately.

THE FAILURE THIS IS LOOKING FOR is everything collapsing to "alarm call". That
is what the shipped head did in 0018, and the corpus invites it: 26,876 alarm
bouts against 272 `call`. A generator that ignores its prefix and a judge that
answers alarm to everything produce the same matrix, which is why the held-out
anchor is not optional.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path("/home/ben/Code/cawtalker")
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np

from crowgpt.birdnet import BirdNet
from crowgpt.calltype import CORE, BoutCallTypes, human_labels, label_bouts
from crowgpt.codec import normalise
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = REPO / "data" / "crowgpt"
MODEL = HERE / "results" / "model-calltype" / "model.pt"
TOKENS = DATA / "tokens-calltype"
OUT = Path(__file__).resolve().parent
PER_TYPE = 60


def matrix(requested, detected, rows, columns):
    """Counts as a plain dict of dicts, so the JSON is readable."""
    table = {r: {c: 0 for c in columns} for r in rows}
    for want, got in zip(requested, detected):
        table[want][got] += 1
    return table


def show(table, rows, columns, title):
    width = max(len(r) for r in rows) + 2
    lines = [title, "  " + " " * width + "".join(f"{c:>12}" for c in columns)]
    for r in rows:
        total = sum(table[r].values())
        cells = "".join(f"{table[r][c]:>12}" for c in columns)
        lines.append(f"  {r:<{width}}{cells}   (n={total})")
    return "\n".join(lines)


run = Run("0021 — DOES THE CALL-TYPE TOKEN DO ANYTHING",
          ["embed labelled bouts", "anchor head on held-out", "generate", "judge generated"])
report = {}

try:
    store = BoutStore(DATA / "bouts")
    splits = store.split(seed=0)
    where = {i: name for name, indices in splits.items() for i in indices}
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
                         extra=f"{tag}, kept {len(kept)}")
        return (np.concatenate(vectors) if vectors else np.zeros((0, 1024))), kept

    with run.stage("embed labelled bouts") as stage:
        train_x, train_pos = embed(sorted(train_tagged), stage, "train")
        head = BoutCallTypes()
        fitted = head.fit(train_x, [train_tagged[p] for p in train_pos])
        held_x, held_pos = embed(sorted(held_out), stage, "held out")
        stage.say(f"head trained on {fitted['trained_on']}, "
                  f"{len(held_pos)} held-out bouts embedded")
        report["head"] = fitted

    with run.stage("anchor head on held-out") as stage:
        truth = [held_out[p] for p in held_pos]
        guess, confidence = head.forced(held_x)
        correct = sum(t == g for t, g in zip(truth, guess))
        majority = Counter(truth).most_common(1)[0]
        report["anchor"] = {
            "n": len(truth),
            "accuracy": round(correct / len(truth), 3),
            "majority_class": majority[0],
            "majority_baseline": round(majority[1] / len(truth), 3),
            "mean_confidence": round(float(np.mean(confidence)), 3),
            "truth_mix": dict(Counter(truth)),
            "matrix": matrix(truth, guess, list(CORE), list(head.classes)),
        }
        stage.say(f"{report['anchor']['accuracy']:.1%} vs "
                  f"{report['anchor']['majority_baseline']:.1%} always-{majority[0]}")
        run.note(show(report["anchor"]["matrix"], list(CORE), list(head.classes),
                      "REAL held-out bouts: human label (row) against head (column)"))

    with run.stage("generate") as stage:
        from crowgpt.sample import Sampler

        sampler = Sampler(MODEL, token_dir=TOKENS)
        wanted, clips, made = [], [], 0
        started = time.time()
        for call_type in CORE:
            for i in range(PER_TYPE):
                clips.append(sampler.audio("american-crow", call_type=call_type, seed=1000 + i))
                wanted.append(call_type)
                made += 1
                stage.update(made, len(CORE) * PER_TYPE, extra=call_type)
        durations = {c: round(float(np.mean(
            [k.size for k, w in zip(clips, wanted) if w == c])) / 24000, 2) for c in CORE}
        stage.say(f"{made} clips in {time.time() - started:.0f}s")
        report["mean_seconds"] = durations

    with run.stage("judge generated") as stage:
        generated_x, index = birdnet.embed_indexed(clips)
        kept = [wanted[i] for i in index]
        guess, confidence = head.forced(generated_x)
        agree = sum(w == g for w, g in zip(kept, guess))
        report["generated"] = {
            "requested": PER_TYPE,
            "embedded": len(kept),
            "agreement": round(agree / len(kept), 3) if kept else None,
            "mean_confidence": round(float(np.mean(confidence)), 3) if kept else None,
            "detected_mix": dict(Counter(guess)),
            "kept_per_type": dict(Counter(kept)),
            "matrix": matrix(kept, guess, list(CORE), list(head.classes)),
        }
        stage.say(f"{report['generated']['agreement']:.1%} of generated clips "
                  f"came back as the type requested")
        run.note(show(report["generated"]["matrix"], list(CORE), list(head.classes),
                      "GENERATED clips: requested (row) against head (column)"))

    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    run.note(f"anchor {report['anchor']['accuracy']:.1%} "
             f"(baseline {report['anchor']['majority_baseline']:.1%}), "
             f"generated agreement {report['generated']['agreement']:.1%}")
except Exception as exc:
    run.note(f"FAILED: {type(exc).__name__}: {exc}")
    raise

print(json.dumps(report, indent=2))
