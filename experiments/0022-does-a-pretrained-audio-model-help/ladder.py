"""Does the LoRA still climb at 3,000 steps, or did it plateau — and does size help?

Ben's question: would more training push the pretrained route over the edge, on
the intuition that LoRAs jump from bad to good where from-scratch models climb
steadily. The usual fine-tuning curve is fast-then-flat rather than late-
breakthrough, but that is a claim about fine-tuning in general and this is a
corpus of crows. Both ladders are already on disk, so the shape can be measured
instead of assumed.

TWO AXES AT ONCE. Steps, across six checkpoints of the 433M small-sfx; and
capacity, across six of the 1.4B medium. If small plateaus and medium sits
higher at every step, the lever is size. If both plateau at the same place, the
lever is neither and the ceiling is the data or the captions.

Generation runs in the stable-audio-3 venv; nothing here imports BirdNET. Scoring
is score_ladder.py on the crowgpt side, same trim-and-normalise as 0022 so the
numbers land on the same axis as `real 65.0% / crowgpt 71.7% / lora 35.0%`.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SA3 = Path("/home/ben/Code/stable-audio-3")
LORA = REPO / "data" / "sa3-lora"
OUT = LORA / "ladder"
GENERATE = Path(__file__).resolve().parent / "generate.py"
PER_TYPE = 10


def rungs(folder, model):
    """(step, checkpoint) for a folder, newest file per step, ascending."""
    found = {}
    for path in Path(folder).glob("*.ckpt"):
        step = int(str(path).split("step=")[1].split(".")[0].split("-")[0])
        # `-v1` copies are the rerun's; take whichever was written last.
        if step not in found or path.stat().st_mtime > found[step].stat().st_mtime:
            found[step] = path
    return [(s, found[s], model) for s in sorted(found)]


def main():
    ladder = rungs(LORA / "checkpoints", "small-sfx-base") + \
             rungs(LORA / "checkpoints-medium", "medium-base")
    print(f"{len(ladder)} rungs", flush=True)
    index = []
    for step, ckpt, model in ladder:
        tag = f"{model}-{step}"
        target = OUT / tag
        if (target / "index.json").exists():
            print(f"  {tag}: already generated", flush=True)
        else:
            print(f"  {tag}: generating", flush=True)
            result = subprocess.run(
                ["uv", "run", "python", str(GENERATE), "--model", model,
                 "--lora", str(ckpt), "--out", str(target),
                 "--per_type", str(PER_TYPE)],
                cwd=str(SA3), capture_output=True, text=True)
            if result.returncode != 0:
                print(f"    FAILED: {result.stderr.strip().splitlines()[-1:]}", flush=True)
                continue
        index.append({"tag": tag, "model": model, "step": step, "dir": str(target)})
    (OUT / "ladder.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"wrote {OUT / 'ladder.json'} with {len(index)} rungs")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main()
