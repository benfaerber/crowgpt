"""Two tracks per row: the recording, and the recording through the codec.

The last open question from 0024. The crowgpt README says "it is the model, not
the codec", and that claim rests on BirdNET detection holding 0.79-0.99 through
the codec arm — but BirdNET cannot hear "robotic", which is the stated reason the
listening test exists at all. So the tokenizer has never once been judged on the
artefact it is being cleared of.

Ben's notes on the real rows of the main page ("choppy", "still bad") are the
first evidence pointing the other way, and they were unreadable because every
track on that page was already a round-trip. There was nothing untouched to
compare against.

DELIBERATELY TWO ARMS. The main page offers four and the two coarse ones are
irrelevant here — a five-codebook version is a lower bitrate by construction and
says nothing about whether the shipping bitrate is transparent. Removing them
removes the thing that made the first pass ambiguous.

If the two tracks are indistinguishable, the codec is cleared properly for the
first time and the roughness belongs to the model. If the round-trip is audibly
worse, a load-bearing claim in the README is wrong and the tokenizer is back on
the table — which would also explain why every model-side lever tried so far has
failed to move what a listener hears.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import torch

from crowgpt.codec import Codec, normalise
from crowgpt.demo import ComparePage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
PAGE = HERE / "results" / "compare-codec-only.html"
ROWS = 10
SPECIES = "american-crow"


def main():
    run = Run("0024 — IS THE CODEC ITSELF AUDIBLE", ["build"])
    try:
        with run.stage("build") as stage:
            codec = Codec(bandwidth=6.0)
            store = BoutStore(DATA / "bouts")
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            # ONE BOUT PER RECORDING. Bouts are consecutive slices of the audio
            # they came from, so held[:10] is ten pieces of one archive file
            # — which is what the first version of this page shipped, and it
            # showed one recording's character while looking like a survey of the
            # corpus. 4,475 held-out bouts sit across 883 recordings; sample the
            # recordings, not the index.
            seen, chosen = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                chosen.append(i)
                if len(chosen) >= ROWS:
                    break

            rows = []
            for position in chosen:
                samples = normalise(store.audio(store.index[position]))
                codes = codec.encode(samples).numpy()[0]
                through = codec.decode(torch.from_numpy(codes))[0]
                rows.append({"species": f"bout {len(rows) + 1}", "arms": [
                    ("RAW — the recording", "untouched", samples, None),
                    ("through the codec", "encoded and decoded, no model", through, None),
                ]})
                stage.update(len(rows), ROWS)

            ComparePage(rows, {
                "Bitrate": "6 kbps, 8 codebooks",
                "Model involved": "none",
                "Rows": len(rows),
                "Question": "is the round-trip audible",
            }).write(PAGE)
            stage.say(str(PAGE))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE)


if __name__ == "__main__":
    main()
