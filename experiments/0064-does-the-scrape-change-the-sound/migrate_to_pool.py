"""Move blocks 2-3 of the 0064 sitting into the listening-pool system.

Block 1 (20 trials) was answered on the standalone PairPage before the pool
system's existence registered with the agent building the sitting — those
answers are banked in results/listening/pairwise-gbw81btt.json and stay
valid. This lifts the REMAINING 40 trials out of the page and registers them
as pool `scrape-v3-0064`, so the rest of the sitting is graded where every
sitting belongs: the dashboard.

BIT-IDENTICAL BY CONSTRUCTION: the trials are parsed out of the served
page's own embedded JSON — audio, arms, played-first order, catch flags —
not regenerated. The clip a trial plays in the pool is byte-for-byte the
wav the page would have played. `first_clip` is the side the page would
have PLAYED first, so the order balance survives the move.

What changes for blocks 2-3, recorded here for the analysis to weigh:
per-trial real anchors (pool convention; block 1 had none) and the graded
-2..+2 scale with defect tags in place of ternary choice. Both changes
apply to every remaining trial and both arms symmetrically; the merge maps
grades to their sign. The question keeps the page's wording, not 0053's.
"""
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

import numpy as np

from crowgpt.codec import SAMPLE_RATE
from crowgpt.tokens import BoutStore

PAGE = HERE / "results" / "pair-v3-vs-v2.html"
POOL_NAME = "scrape-v3-0064"
CLIP_DIR = HERE / "results" / "listening-pools" / POOL_NAME
OUT = Path(__file__).resolve().parent
DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"

ANSWERED = 20     # block 1, banked on the PairPage
DOSE = 20
COOLDOWN_MIN = 30

QUESTION = (
    "Which of the two sounds <strong>less</strong> synthetic — less robotic, "
    "garbled, xylophone-ish? Both may be good now; say which is closer to a "
    "real crow anyway. The reference clip is a real recording to recalibrate "
    "against, and “they are the same” is a real answer."
)


def wav_bytes(data_uri):
    return base64.b64decode(data_uri.split(",", 1)[1])


def main():
    from crowgpt.codec import normalise

    trials_json = re.search(r"const TRIALS = (\[.*?\]);\n", PAGE.read_text(),
                            re.S).group(1)
    page_trials = json.loads(trials_json)
    remaining = [t for t in page_trials if t["n"] > ANSWERED]
    assert len(remaining) == 40, f"expected 40 remaining, got {len(remaining)}"

    manifest = json.loads((OUT / "sitting-manifest.json").read_text())
    used_bouts = set(manifest.get("real_bouts", []))

    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    store = BoutStore(DATA / "bouts")
    splits = store.split(seed=0)
    seen, anchors = set(), []
    for i in splits["test"]:
        row = store.index[i]
        if row["species"] != "american-crow" or i in used_bouts \
                or row["recording_id"] in seen or row["n_samples"] < SAMPLE_RATE:
            continue
        seen.add(row["recording_id"])
        anchors.append(i)
        if len(anchors) >= len(remaining):
            break
    assert len(anchors) == len(remaining), "not enough anchor bouts"

    import soundfile as sf

    pool_trials = []
    for k, trial in enumerate(remaining):
        first_side = trial["first"]
        second_side = "right" if first_side == "left" else "left"
        hidden = trial["hidden"]
        first_name = f"trial-{trial['n']:02d}-first.wav"
        second_name = f"trial-{trial['n']:02d}-second.wav"
        (CLIP_DIR / first_name).write_bytes(wav_bytes(trial[first_side]["audio"]))
        (CLIP_DIR / second_name).write_bytes(wav_bytes(trial[second_side]["audio"]))
        anchor_name = f"anchor-{trial['n']:02d}.wav"
        sf.write(CLIP_DIR / anchor_name,
                 normalise(store.audio(store.index[anchors[k]])),
                 SAMPLE_RATE, subtype="PCM_16")
        pool_trials.append({
            "block": k // DOSE,
            "kind": "catch" if hidden["catch"] else "compare",
            "anchor_clip": anchor_name,
            "first_clip": first_name,
            "second_clip": second_name,
            "first_arm": hidden[f"{first_side}_arm"],
            "second_arm": hidden[f"{second_side}_arm"],
            "facts": {"pairpage_trial": trial["n"]},
        })

    payload = {
        "name": POOL_NAME,
        "question": QUESTION,
        "clip_dir": str(CLIP_DIR),
        "trials": pool_trials,
        "spec": {
            "experiment": "0064",
            "continues": "pairwise-gbw81btt.json (block 1, 20 trials, PairPage)",
            "decoder": "finetuned (0063 adversarial best.pt), both arms",
            "anchor_bouts": anchors,
            "format_note": "blocks 2-3 graded with anchors; block 1 ternary "
                           "without — merge by grade sign",
        },
    }
    pool_json = OUT / "pool.json"
    pool_json.write_text(json.dumps(payload, indent=2))
    result = subprocess.run(
        [str(REPO / "fieldserver" / ".venv" / "bin" / "python"),
         str(REPO / "fieldserver" / "tools" / "register_pool.py"),
         str(pool_json), "--dose-size", str(DOSE), "--cooldown", str(COOLDOWN_MIN)],
        capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(1)

    catches = sum(1 for t in pool_trials if t["kind"] == "catch")
    print(f"{len(pool_trials)} trials ({catches} catch) in 2 blocks of {DOSE}, "
          f"cooldown {COOLDOWN_MIN} min — on the dashboard")


if __name__ == "__main__":
    main()
