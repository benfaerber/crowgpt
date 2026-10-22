"""0076 stage 2 (CPU, birdnetlib, no torch): whose voice does BirdNET hear?

Runs the full taxonomy over every wav gen_draws.py wrote and tallies
detections per group. Corvid terms borrowed from the analyzer so "corvid"
means the same thing it means everywhere else in the project.
"""
import contextlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

HERE = Path(__file__).resolve().parent
WAVS = HERE / "wavs"
MIN_CONF = 0.25


def main():
    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        from birdnetlib import Recording
        from birdnetlib.analyzer import Analyzer

        from analyzer import birdnet as house

        analyzer = Analyzer()

    corvid_terms = tuple(t.lower() for t in house.CROW_TERMS)
    report = {}
    for group_dir in sorted(p for p in WAVS.rglob("*") if p.is_dir()):
        wavs = sorted(group_dir.glob("*.wav"))
        if not wavs:
            continue
        group = str(group_dir.relative_to(WAVS))
        tally, non_corvid_clips = Counter(), 0
        per_clip = []
        for wav in wavs:
            with open(os.devnull, "w") as null, \
                    contextlib.redirect_stdout(null):
                rec = Recording(analyzer, str(wav), min_conf=MIN_CONF)
                rec.analyze()
            names = set()
            for d in rec.detections:
                name = d.get("common_name") or d.get("scientific_name") or "?"
                full = f"{name} {d.get('scientific_name', '')}".lower()
                kind = "corvid" if any(t in full for t in corvid_terms) else name
                names.add(kind)
            for kind in names:
                tally[kind] += 1
            if any(k != "corvid" for k in names):
                non_corvid_clips += 1
            per_clip.append(sorted(names))
        report[group] = {
            "clips": len(wavs),
            "non_corvid_clip_share": round(non_corvid_clips / len(wavs), 3),
            "detected": dict(tally.most_common()),
        }
        print(f"{group}: {report[group]['non_corvid_clip_share']:.0%} clips "
              f"with non-corvid detections — {dict(tally.most_common(6))}",
              flush=True)

    (HERE / "detections.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
