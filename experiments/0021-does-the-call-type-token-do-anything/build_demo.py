"""The listening page for 0021: each call type asked for, beside the real thing.

The confusion matrix is the evidence and this is not a second measurement — it
is the thing the matrix cannot give you, which is what the conditioning actually
sounds like. Real held-out bouts sit above the generated ones so the ear has
something to compare against, and every generated row carries what the head
heard so a section can be read without trusting the summary.

Generated clips are picked to show the truth rather than the best of it: the
head's agreement is displayed per row, and where a type mostly fails the page
shows mostly failures.
"""
import json
import sys
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
from crowgpt.demo import CallTypePage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = REPO / "data" / "crowgpt"
MODEL = HERE / "results" / "model-calltype" / "model.pt"
TOKENS = DATA / "tokens-calltype"
PAGE = HERE / "results" / "demo-calltype.html"
RESULTS = json.loads((Path(__file__).resolve().parent / "results.json").read_text())

TRAIN_BOUTS = {"alarm call": 26876, "begging": 2349, "song": 1113, "call": 272}
REAL_PER_TYPE = 3
GENERATED_PER_TYPE = 6

run = Run("0021 DEMO — ASK IT FOR A CALL TYPE",
          ["gather real bouts", "generate", "judge", "write page"])

try:
    store = BoutStore(DATA / "bouts")
    splits = store.split(seed=0)
    where = {i: name for name, indices in splits.items() for i in indices}
    tagged = label_bouts(store.index, human_labels())
    train_tagged = {i: t for i, t in tagged.items() if where[i] == "train"}
    held_out = {i: t for i, t in tagged.items() if where[i] != "train"}
    birdnet = BirdNet(sample_rate=24000)

    with run.stage("gather real bouts") as stage:
        by_type = {c: [] for c in CORE}
        for position, call_type in sorted(held_out.items()):
            if len(by_type[call_type]) < REAL_PER_TYPE:
                by_type[call_type].append(normalise(store.audio(store.index[position])))
        # The head has to exist for the generated half, and it trains on the
        # same train-split humans the corpus labelling used.
        features, kept = [], []
        positions = sorted(train_tagged)
        for start in range(0, len(positions), 400):
            chunk = positions[start:start + 400]
            got, index = birdnet.embed_indexed(
                [normalise(store.audio(store.index[p])) for p in chunk])
            if len(got):
                features.append(got)
                kept.extend(chunk[j] for j in index)
            stage.update(min(start + 400, len(positions)), len(positions), extra="embedding")
        head = BoutCallTypes()
        head.fit(np.concatenate(features), [train_tagged[p] for p in kept])
        stage.say(f"{sum(len(v) for v in by_type.values())} real bouts, head ready")

    with run.stage("generate") as stage:
        from crowgpt.sample import Sampler

        sampler = Sampler(MODEL, token_dir=TOKENS)
        generated, made = {}, 0
        for call_type in CORE:
            clips = []
            for i in range(GENERATED_PER_TYPE):
                clips.append(sampler.audio("american-crow", call_type=call_type, seed=2000 + i))
                made += 1
                stage.update(made, len(CORE) * GENERATED_PER_TYPE, extra=call_type)
            generated[call_type] = clips
        stage.say(f"{made} clips")

    with run.stage("judge") as stage:
        flat = [(c, clip) for c in CORE for clip in generated[c]]
        embedded, index = birdnet.embed_indexed([clip for _, clip in flat])
        heard = {}
        if len(index):
            guess, _ = head.forced(embedded)
            heard = dict(zip(index, guess))
        stage.say(f"{len(index)}/{len(flat)} embedded")

    with run.stage("write page") as stage:
        sections, cursor = [], 0
        for call_type in CORE:
            recall = RESULTS["generated"]["matrix"][call_type][call_type]
            total = sum(RESULTS["generated"]["matrix"][call_type].values())
            rows = []
            for i, clip in enumerate(generated[call_type]):
                verdict = heard.get(cursor + i)
                rows.append({"audio": clip, "label": f"generated {i + 1}",
                             "heard": verdict or "too short to judge",
                             "hit": None if verdict is None else verdict == call_type})
            cursor += len(generated[call_type])
            sections.append({
                "type": call_type,
                "note": f"{TRAIN_BOUTS[call_type]:,} training bouts · "
                        f"{recall}/{total} of 0021's clips came back as {call_type} "
                        f"({recall / total:.0%})",
                "real": [{"audio": audio, "label": f"real {i + 1}", "hit": None}
                         for i, audio in enumerate(by_type[call_type])],
                "generated": rows,
            })

        facts = {
            "Agreement": f"{RESULTS['generated']['agreement']:.1%}",
            "Chance": "25.5%",
            "Judge on real": f"{RESULTS['anchor']['accuracy']:.1%}",
            "Baseline": f"{RESULTS['anchor']['majority_baseline']:.1%}",
            "Clips judged": RESULTS["generated"]["embedded"],
            "Model": "18M params, d384, 6 kbps",
        }
        CallTypePage(sections, facts).write(PAGE)
        stage.say(str(PAGE))
except Exception as exc:
    run.note(f"FAILED: {type(exc).__name__}: {exc}")
    raise

print("wrote", PAGE)
