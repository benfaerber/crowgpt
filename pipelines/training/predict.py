"""Phase 4/5: the working detector. Audio in -> call type + confidence.

End-to-end in the BirdNET venv: BirdNET embeds the clip, the trained classifier
scores it. Usage:

  ../representation/.venv-birdnet/bin/python predict.py <audio-file>
"""

import contextlib
import os
import sys
from pathlib import Path

import joblib
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

from pooling import pool

HERE = Path(__file__).resolve().parent
# The per-species head the analyzer itself serves — the flat archive-only
# head this loaded before was retired 2026-08-09.
MODEL = HERE / "models" / "american-crow" / "calltype_clf.joblib"
DEVNULL = open(os.devnull, "w")


def embed(path):
    with contextlib.redirect_stdout(DEVNULL):
        analyzer = Analyzer()
        rec = Recording(analyzer, str(path), min_conf=0.1)
        rec.extract_embeddings()
    segs = rec.embeddings
    if not segs:
        raise SystemExit("No embeddings — is this an audio file with sound?")
    return pool([s["embeddings"] for s in segs]).reshape(1, -1)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: predict.py <audio-file>")
    if not MODEL.exists():
        raise SystemExit(f"No model at {MODEL} — run train_head.py first.")
    bundle = joblib.load(MODEL)
    model, classes = bundle["model"], bundle["classes"]
    proba = model.predict_proba(embed(sys.argv[1]))[0]
    ranked = sorted(zip(classes, proba), key=lambda kv: -kv[1])
    print(f"\n{Path(sys.argv[1]).name}")
    for c, p in ranked:
        bar = "█" * int(round(p * 30))
        print(f"  {c:<12} {p:5.1%} {bar}")
    print(f"\n→ {ranked[0][0]} ({ranked[0][1]:.0%} confidence)")


if __name__ == "__main__":
    main()
