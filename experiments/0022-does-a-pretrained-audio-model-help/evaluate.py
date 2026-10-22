"""Score every arm the same way: does BirdNET hear a corvid, and which call type?

FOUR ARMS, because two of them are the only reason the other two mean anything.

  real      held-out bouts, untouched by any model. The ceiling.
  crowgpt   the 18M from-scratch model (0021). The incumbent to beat.
  base      Stable Audio 3 with the same prompts and NO adapter. The control.
  lora      Stable Audio 3 fine-tuned on 2,961 bouts. The treatment.

`base` is the one people skip. Stable Audio has heard birds, so the prompt alone
may already produce something crow-shaped; without this arm a good `lora` number
gets credited to the fine-tune when the phrase "American Crow alarm call" did
the work. `real` is the other anchor — a metric that cannot score real audio
highly is not measuring realism, whatever it does to the generated arms.

EVERYTHING IS TRIMMED TO 3 SECONDS AND RESAMPLED TO 24 kHz FIRST. BirdNET scores
3-second windows, so a 5-second clip gets more chances to be called a corvid
than a 2.7-second bout does, and that bias runs in favour of the generated arms
exactly where we are least inclined to doubt a good result.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path("/home/ben/Code/cawtalker")
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from crowgpt.birdnet import BirdNet
from crowgpt.calltype import CORE, BoutCallTypes, human_labels, label_bouts
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = REPO / "data" / "crowgpt"
SA3 = REPO / "data" / "sa3-lora"
OUT = Path(__file__).resolve().parent
CROWGPT_MODEL = HERE / "results" / "model-calltype" / "model.pt"
TOKENS = DATA / "tokens-calltype"
PER_TYPE = 30
CLIP_SECONDS = 3.0


def standardise(audio, sr):
    """Mono, 24 kHz, first 3 seconds, peak normalised — every arm identical.

    The normalisation is not cosmetic. Stable Audio returns quiet clips (peak
    0.05-0.19 measured), the bout corpus is peak normalised to 0.89 before it is
    ever used, and BirdNET's confidence moves with level. Trimming and resampling
    both arms but normalising only one would hand the real audio an advantage and
    call the difference realism.
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        from math import gcd
        divisor = gcd(int(sr), SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, int(sr) // divisor)
    return normalise(audio[: int(CLIP_SECONDS * SAMPLE_RATE)]).astype(np.float32)


def load_arm(directory):
    index = json.loads((Path(directory) / "index.json").read_text())
    clips, wanted = [], []
    for row in index["clips"]:
        audio, sr = sf.read(str(Path(directory) / row["file"]))
        clips.append(standardise(audio, sr))
        wanted.append(row["call_type"])
    return clips, wanted


def main():
    run = Run("0022 — SCORING THE ARMS",
              ["gather", "birdnet", "call type"])
    report = {}
    try:
        with run.stage("gather") as stage:
            store = BoutStore(DATA / "bouts")
            splits = store.split(seed=0)
            where = {i: n for n, idx in splits.items() for i in idx}
            tagged = label_bouts(store.index, human_labels())
            train_tagged = {i: t for i, t in tagged.items() if where[i] == "train"}
            held_out = {i: t for i, t in tagged.items() if where[i] != "train"}

            arms = {}
            by_type = {c: [] for c in CORE}
            for position, call_type in sorted(held_out.items()):
                if len(by_type[call_type]) < PER_TYPE:
                    by_type[call_type].append(
                        standardise(normalise(store.audio(store.index[position])), SAMPLE_RATE))
            arms["real"] = ([c for t in CORE for c in by_type[t]],
                            [t for t in CORE for _ in by_type[t]])

            from crowgpt.sample import Sampler
            sampler = Sampler(CROWGPT_MODEL, token_dir=TOKENS)
            clips, wanted = [], []
            for call_type in CORE:
                for i in range(PER_TYPE):
                    clips.append(standardise(
                        sampler.audio("american-crow", call_type=call_type, seed=7000 + i),
                        SAMPLE_RATE))
                    wanted.append(call_type)
                stage.update(len(wanted), len(CORE) * PER_TYPE, extra=f"crowgpt {call_type}")
            arms["crowgpt"] = (clips, wanted)

            for name in ("base", "lora"):
                folder = SA3 / f"generated-{name}"
                if (folder / "index.json").exists():
                    arms[name] = load_arm(folder)
            stage.say(" ".join(f"{k}:{len(v[0])}" for k, v in arms.items()))

        birdnet = BirdNet(sample_rate=SAMPLE_RATE)

        with run.stage("birdnet") as stage:
            for name, (clips, _) in arms.items():
                scores, crow_min = birdnet.confidence(clips)
                got = [s for s in scores if s is not None]
                detected = sum(1 for s in got if s >= crow_min)
                report.setdefault(name, {})["birdnet"] = {
                    "clips": len(clips),
                    "scored": len(got),
                    "detected": detected,
                    "rate": round(detected / len(clips), 3) if clips else None,
                    "mean_confidence": round(float(np.mean(got)), 3) if got else None,
                    "threshold": crow_min,
                }
                stage.say(f"{name} {report[name]['birdnet']['rate']:.1%}")
            run.note("BirdNET corvid rate: " + ", ".join(
                f"{k} {v['birdnet']['rate']:.1%}" for k, v in report.items()))

        with run.stage("call type") as stage:
            features, kept = [], []
            positions = sorted(train_tagged)
            for start in range(0, len(positions), 400):
                chunk = positions[start:start + 400]
                got, index = birdnet.embed_indexed(
                    [normalise(store.audio(store.index[p])) for p in chunk])
                if len(got):
                    features.append(got)
                    kept.extend(chunk[j] for j in index)
            head = BoutCallTypes()
            head.fit(np.concatenate(features), [train_tagged[p] for p in kept])

            for name, (clips, wanted) in arms.items():
                embedded, index = birdnet.embed_indexed(clips)
                if not len(index):
                    report[name]["calltype"] = {"embedded": 0, "agreement": None}
                    continue
                truth = [wanted[i] for i in index]
                guess, _ = head.forced(embedded)
                agree = sum(a == b for a, b in zip(truth, guess))
                report[name]["calltype"] = {
                    "embedded": len(index),
                    "agreement": round(agree / len(truth), 3),
                    "detected_mix": dict(Counter(guess)),
                }
                stage.say(f"{name} {report[name]['calltype']['agreement']:.1%}")
            run.note("call-type agreement: " + ", ".join(
                f"{k} {v['calltype']['agreement']}" for k, v in report.items()))

        (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
