#!/usr/bin/env python3
"""Capture 104's two caws — why one surfaced and the other did not.

Ben's ear put a caw over the begging at ~12s and again at ~27s (ai_descriptions
rows 13 and 14, written 2026-08-01). The one-vs-rest head and the `alternates`
column have shipped since, and the current analysis catches ONE of them:

    9-27s   begging 1.000   alternates: call 0.998   <- the ~12s caw
    27-30s  begging 1.000   alternates: (none)       <- the ~27s caw, still missed

The two regions differ in a way 0036 arm D says should matter. 9-27s is 18
seconds — six 3s BirdNET windows, so mean/std/max pooling has real temporal
spread to describe. 27-30s is one window, where std = 0 and max = mean, leaving a
third of the 3072-d vector empty and a third redundant. Arm D found exactly that
degeneracy collapsing predictions toward the dominant class on field audio: 41 of
52 spans called `alarm call` when pooled as a single window against 25 of 52
pooled over the span.

So the hypothesis is that the ~27s caw is not inaudible to the head, it is
unrepresentable at that region length. Test: score the same moment at a ladder of
window widths and watch whether `call` appears.

This is a diagnosis of one capture, not a measurement over a corpus. It can show
that a wider region surfaces the caw; it cannot prove that is why, and a single
recording cannot generalise. Treated accordingly in the write-up.

    ../../pipelines/representation/.venv-birdnet/bin/python capture_104.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MEDIA = REPO / "fieldserver" / "instance" / "media" / "38f4e5626e7b74b16f759c9879557148.flac"
HEAD = REPO / "pipelines" / "training" / "models" / "american-crow" / "calltype_clf.joblib"
DEVNULL = open(os.devnull, "w")

sys.path.insert(0, str(REPO / "pipelines" / "training"))
from pooling import pool  # noqa: E402

# The two moments Ben reported, and a control the analyzer already agrees about.
MOMENTS = {"caw_at_12s": 12.0, "caw_at_27s": 27.0, "control_at_45s": 45.0}
WIDTHS = [3, 6, 9, 12, 18]


def main():
    if not MEDIA.exists():
        sys.exit(f"missing audio: {MEDIA}")
    bundle = joblib.load(HEAD)
    head, classes = bundle["model"], bundle["classes"]

    with contextlib.redirect_stdout(DEVNULL):
        rec = Recording(Analyzer(), str(MEDIA), min_conf=0.1)
        rec.extract_embeddings()
    windows = {int(round(s["start_time"])): np.array(s["embeddings"])
               for s in rec.embeddings}
    starts = sorted(windows)
    print(f"{len(starts)} BirdNET windows, {starts[0]}-{starts[-1]}s\n", flush=True)

    out = {"capture": 104,
           "reported_by_ear": {"caw_at_12s": "surfaced as alternate `call` 0.998 "
                                             "inside the 9-27s region",
                               "caw_at_27s": "no alternate on the 27-30s region"},
           "note": ("one-vs-rest probabilities do not sum to one, so two can be "
                    "high at once — that is the point of the head"),
           "ladder": {}}

    for name, centre in MOMENTS.items():
        out["ladder"][name] = {}
        print(f"--- {name} (centre {centre}s) ---", flush=True)
        for width in WIDTHS:
            lo, hi = centre - width / 2, centre + width / 2
            covered = [windows[w] for w in starts if w < hi and (w + 3.0) > lo]
            if not covered:
                continue
            proba = head.predict_proba(pool(covered).reshape(1, -1))[0]
            ranked = sorted(zip(classes, proba), key=lambda p: -p[1])
            out["ladder"][name][f"{width}s"] = {
                "n_windows": len(covered),
                "span": [round(lo, 1), round(hi, 1)],
                "probabilities": {c: round(float(p), 4) for c, p in ranked},
            }
            top = "  ".join(f"{c}={p:.3f}" for c, p in ranked[:3])
            print(f"  {width:2d}s ({len(covered)} win): {top}", flush=True)
        print(flush=True)

    (HERE / "capture104.json").write_text(json.dumps(out, indent=2))
    print("wrote capture104.json")


if __name__ == "__main__":
    main()
