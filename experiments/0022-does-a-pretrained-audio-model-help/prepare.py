"""Write the bout corpus out as Stable Audio 3 LoRA training data.

The trainer wants a flat folder of `clip.wav` next to `clip.txt`, the caption.
Everything interesting here is in which bouts go in and what the captions say.

TRAIN SPLIT ONLY, and this is not a formality. The 60-trial listening sheet
scores generated audio against REAL held-out bouts, so a LoRA that had trained
on those would be judged against its own training set and the 75% baseline would
stop being comparable. Same reason 0021 held them back from the head.

BALANCED, BECAUSE THE CORPUS IS NOT. The train split runs 26,876 alarm bouts
against 272 `call`, and 0021 measured exactly what that imbalance does to
conditioning — recall tracked the per-class count from 92.9% down to 3.8%.
Handing the same skew to a text-conditioned model would teach it that every crow
caption means alarm. So each type is capped at the same ceiling and the rare
ones bring everything they have.

CAPTIONS ARE THE PART MOST LIKELY TO WASTE THE RUN. These models condition on
natural language, so 57,000 clips that all say "a crow" collapse to one texture
and throw away the controllability 0021 just established. The template below
carries species and call type — the two facts we actually possess — plus enough
scene words to land in the right region of a model that has never been told what
a corvid is. Nothing here is invented: call types are 0021's pseudo-labels and
the humans they were trained on, and no clip claims a type the label did not
assert.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path("/home/ben/Code/cawtalker")
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

import numpy as np
import soundfile as sf

from crowgpt.calltype import CORE, human_labels, label_bouts
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = REPO / "data" / "crowgpt"
OUT = REPO / "data" / "sa3-lora" / "american-crow"
PER_TYPE = 900
SPECIES = "american-crow"
LABEL = "American Crow"

SCENE = "wild bird vocalization, outdoor field recording, natural ambience"
PHRASING = {
    "alarm call": "American Crow alarm call, harsh repeated cawing",
    "begging": "American Crow begging call, juvenile food-solicitation calls",
    "call": "American Crow call, single spaced caws",
    "song": "American Crow song, quiet varied warbling subsong",
}


def main():
    run = Run("0022 PREPARE — BOUTS AS LORA TRAINING DATA",
              ["choose bouts", "write clips"])
    try:
        with run.stage("choose bouts") as stage:
            store = BoutStore(DATA / "bouts")
            splits = store.split(seed=0)
            train_positions = set(splits["train"])

            payload = json.loads((DATA / "bouts" / "call_types.json").read_text())
            pseudo = {int(k): v for k, v in payload["call_types"].items()}
            # The human labels the head trained on are better than its guesses
            # about the same bouts, so they win where both exist.
            humans = label_bouts(store.index, human_labels())

            chosen, counts = [], Counter()
            for position, row in enumerate(store.index):
                if row["species"] != SPECIES or position not in train_positions:
                    continue
                call_type = humans.get(position, pseudo.get(position))
                if call_type not in CORE or counts[call_type] >= PER_TYPE:
                    continue
                chosen.append((position, call_type))
                counts[call_type] += 1
            stage.say(" ".join(f"{k}:{v}" for k, v in sorted(counts.items())))
            run.note("clips per call type: " + json.dumps(dict(counts)))

        with run.stage("write clips") as stage:
            OUT.mkdir(parents=True, exist_ok=True)
            for existing in OUT.glob("*"):
                existing.unlink()
            for i, (position, call_type) in enumerate(chosen):
                audio = normalise(store.audio(store.index[position]))
                if audio.size < SAMPLE_RATE * 0.5:
                    continue
                stem = OUT / f"{i:06d}"
                sf.write(str(stem.with_suffix(".wav")), audio, SAMPLE_RATE, subtype="PCM_16")
                stem.with_suffix(".txt").write_text(f"{PHRASING[call_type]}, {SCENE}\n")
                if (i + 1) % 200 == 0:
                    stage.update(i + 1, len(chosen))
            written = len(list(OUT.glob("*.wav")))
            stage.say(f"{written} clips in {OUT}")
            durations = [sf.info(str(p)).duration for p in sorted(OUT.glob("*.wav"))[:400]]
            run.note(f"median clip {np.median(durations):.2f}s, "
                     f"95th {np.percentile(durations, 95):.2f}s, max {max(durations):.2f}s")
            (OUT.parent / "manifest.json").write_text(json.dumps({
                "clips": written, "per_type": dict(counts), "split": "train",
                "species": SPECIES, "sample_rate": SAMPLE_RATE,
                "median_seconds": round(float(np.median(durations)), 3),
            }, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(f"wrote {written} clips to {OUT}")


if __name__ == "__main__":
    main()
