#!/usr/bin/env python3
"""How far is the field corpus from answering "what was that call about"?

Experiment 0006 asked whether context is in the signal and refused to answer:
the corpus held 3 labelled calls with context. It has grown, so this asks the
same question again — and, when it still cannot answer, says exactly what is
missing rather than just declining.

That second half is the point. 0006 refuses and stops, which is correct but
leaves "collect more" as the whole instruction. Two months of field sessions is
about to happen, and the difference between sessions that make this answerable
and sessions that do not is *which* situation gets recorded, on *how many
separate days*. This prints that list.

    ../../pipelines/representation/.venv-birdnet/bin/python run.py
    ../../pipelines/representation/.venv-birdnet/bin/python run.py --call-type begging

Re-run it as the corpus grows. It answers itself the moment a pair clears the
bar, with no new code — the separation test is already wired up below.

Why the bar is about *captures* and not calls: two caws from one bout are nearly
the same data point, so a split that puts them either side of a fold reports an
accuracy about the recording rather than the situation. Every fold here holds
out a whole capture, which means a cell drawn from two captures has two
independent observations however many calls are in it.

Kept captures only. The corpus is mostly seeded archive clips and test uploads, and
the ★ Keep flag is the only thing separating a real field observation from them.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(REPO / "experiments" / "lib"))

from lib.media import field_db, media_dir  # noqa: E402

#: 0006's bar, unchanged so the two experiments are comparable. Below this the
#: answer is "collect more", not a number.
MIN_CALLS = 10
MIN_CAPTURES = 4
PERMUTATIONS = 200

RESULTS = HERE / "results.json"


class ContextCorpus:
    """Human-labelled calls on kept field audio, with the situations witnessed.

    Context is joined on the *label*, not the capture. Capture-level context
    would pair every situation in a recording with every call in it, so one dog
    and one song would report that crows sing at dogs.
    """

    def __init__(self, call_type, db_path=None):
        self.call_type = call_type
        self.db_path = Path(db_path or field_db())
        db = sqlite3.connect(str(self.db_path))
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """
            SELECT l.id, l.capture_id, l.start_sec, l.end_sec, ce.key AS context,
                   m.storage_ref
            FROM labels l
            JOIN captures c ON c.id = l.capture_id
            JOIN context_events ce ON ce.label_id = l.id
            JOIN media m ON m.capture_id = c.id AND m.kind = 'audio'
                        AND m.upload_state = 'complete'
            WHERE c.keep = 1 AND l.call_type = ?
            ORDER BY l.capture_id, l.start_sec
            """,
            (call_type,),
        ).fetchall()
        db.close()

        self.chips = defaultdict(set)
        self.call = {}
        for r in rows:
            self.chips[r["id"]].add(r["context"])
            self.call[r["id"]] = dict(r)

    @property
    def contexts(self):
        return sorted({k for s in self.chips.values() for k in s})

    @property
    def captures(self):
        return {c["capture_id"] for c in self.call.values()}

    def side(self, present, absent):
        """Calls carrying `present` and not `absent` — the exclusive contrast.

        A call can hold several chips at once (`human_known` and `caller_stays`
        and `crows_still` all describe one moment), so a pairwise test has to
        drop the calls carrying both or it is scoring a label against itself.
        """
        return [i for i, s in self.chips.items() if present in s and absent not in s]

    def readiness(self):
        """Every context pair, and how far each is from being answerable."""
        out = []
        for a, b in itertools.combinations(self.contexts, 2):
            A, B = self.side(a, b), self.side(b, a)
            ca = {self.call[i]["capture_id"] for i in A}
            cb = {self.call[i]["capture_id"] for i in B}
            out.append({
                "a": a, "b": b,
                "a_calls": len(A), "a_captures": len(ca),
                "b_calls": len(B), "b_captures": len(cb),
                "ready": (len(A) >= MIN_CALLS and len(B) >= MIN_CALLS
                          and len(ca) >= MIN_CAPTURES and len(cb) >= MIN_CAPTURES),
                "needs": self._needs(len(A), len(ca), len(B), len(cb)),
            })
        return sorted(out, key=lambda r: (-r["ready"], -min(r["a_captures"],
                                                            r["b_captures"])))

    @staticmethod
    def _needs(a_calls, a_caps, b_calls, b_caps):
        gaps = []
        for side, calls, caps in (("A", a_calls, a_caps), ("B", b_calls, b_caps)):
            if caps < MIN_CAPTURES:
                gaps.append(f"{side}: {MIN_CAPTURES - caps} more capture(s)")
            if calls < MIN_CALLS:
                gaps.append(f"{side}: {MIN_CALLS - calls} more call(s)")
        return gaps


class Embedder:
    """One BirdNET vector per labelled call, from the capture's own audio."""

    def __init__(self):
        from birdnetlib.analyzer import Analyzer
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            self.analyzer = Analyzer()
        self._cache = {}

    def _windows(self, storage_ref):
        if storage_ref not in self._cache:
            from birdnetlib import Recording
            path = media_dir() / storage_ref
            if not path.exists():
                self._cache[storage_ref] = {}
            else:
                with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
                    rec = Recording(self.analyzer, str(path), min_conf=0.01)
                    rec.extract_embeddings()
                self._cache[storage_ref] = {
                    round(s["start_time"], 2): np.asarray(s["embeddings"])
                    for s in rec.embeddings
                }
        return self._cache[storage_ref]

    def embed(self, call):
        """The window the labelled call starts in, or None if the audio is gone.

        BirdNET's fixed 3 s grid, same as 0006 used — deliberately, so a change
        in the answer is a change in the corpus rather than in the method.
        Experiment 0025 found a better backbone for call *type*; whether it is
        also better for context is a question this cannot ask until a pair
        clears the bar.
        """
        windows = self._windows(call["storage_ref"])
        if not windows:
            return None
        nearest = min(windows, key=lambda s: abs(s - call["start_sec"]))
        return windows[nearest]


def separates(X, y, groups, seed=0):
    """Leave-one-capture-out accuracy, against a shuffled-label baseline.

    With n this small an accuracy alone is unreadable — the question is what the
    same number looks like when the labels carry provably nothing. If the real
    score sits inside that distribution there is no signal, however good it
    looked.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import LeaveOneGroupOut

    def score(labels):
        scores = []
        for train, test in LeaveOneGroupOut().split(X, labels, groups):
            if len(set(labels[train])) < 2:
                continue
            model = LogisticRegression(max_iter=2000, class_weight="balanced")
            model.fit(X[train], labels[train])
            scores.append(model.score(X[test], labels[test]))
        return float(np.mean(scores)) if scores else float("nan")

    real = score(y)
    rng = np.random.default_rng(seed)
    null = np.array([score(rng.permutation(y)) for _ in range(PERMUTATIONS)])
    return {
        "accuracy": round(real, 3),
        "null_mean": round(float(np.nanmean(null)), 3),
        "null_p95": round(float(np.nanpercentile(null, 95)), 3),
        "p_value": round(float(np.nanmean(null >= real)), 4),
        "n": int(len(y)),
        "captures": int(len(set(groups.tolist()))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--call-type", default="alarm call")
    args = parser.parse_args()

    corpus = ContextCorpus(args.call_type)
    print(f"=== '{args.call_type}' on kept field audio ===")
    print(f"{len(corpus.chips)} calls with context over "
          f"{len(corpus.captures)} captures, {len(corpus.contexts)} distinct chips\n")
    if not corpus.chips:
        raise SystemExit("No labelled calls of that type carry a context chip yet.")

    table = corpus.readiness()
    shown = [r for r in table if min(r["a_calls"], r["b_calls"]) >= 3]
    print(f"Pairwise readiness — the bar is {MIN_CALLS}+ calls over "
          f"{MIN_CAPTURES}+ separate captures, per side.\n")
    print(f"{'context A':<20}{'context B':<20}{'A':>9}{'B':>9}  status")
    for r in shown:
        a_cell = "{}/{}".format(r["a_calls"], r["a_captures"])
        b_cell = "{}/{}".format(r["b_calls"], r["b_captures"])
        status = "READY" if r["ready"] else "; ".join(r["needs"])
        print(f"{r['a']:<20}{r['b']:<20}{a_cell:>9}{b_cell:>9}  {status}")

    ready = [r for r in table if r["ready"]]
    results = {"call_type": args.call_type,
               "calls_with_context": len(corpus.chips),
               "captures": len(corpus.captures),
               "readiness": table, "tests": {}}

    if not ready:
        print("\nNo pair is answerable yet, so no accuracy is reported — a number "
              "from\nthis much data would be noise wearing a result's clothes.")
        _what_to_record(corpus, table)
    else:
        embedder = Embedder()
        for r in ready:
            A, B = corpus.side(r["a"], r["b"]), corpus.side(r["b"], r["a"])
            X, y, g = [], [], []
            for label, ids in ((r["a"], A), (r["b"], B)):
                for i in ids:
                    vec = embedder.embed(corpus.call[i])
                    if vec is None:
                        continue
                    X.append(vec)
                    y.append(label)
                    g.append(corpus.call[i]["capture_id"])
            if len({*y}) < 2:
                continue
            out = separates(np.array(X), np.array(y), np.array(g))
            results["tests"][f"{r['a']} vs {r['b']}"] = out
            verdict = ("SEPARATES" if out["p_value"] < 0.05
                       else "no signal above the shuffled baseline")
            print(f"\n=== {r['a']} vs {r['b']} ===")
            print(f"  accuracy {out['accuracy']}  vs shuffled {out['null_mean']} "
                  f"(95th {out['null_p95']}),  p={out['p_value']}  -> {verdict}")

    RESULTS.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {RESULTS}")


def _what_to_record(corpus, table):
    """The actionable half: which situation, on how many more separate days."""
    print("\n" + "=" * 72)
    print("WHAT WOULD MAKE THIS ANSWERABLE")
    print("=" * 72)
    per_context = {}
    for chip in corpus.contexts:
        ids = [i for i, s in corpus.chips.items() if chip in s]
        caps = {corpus.call[i]["capture_id"] for i in ids}
        per_context[chip] = (len(ids), len(caps))
    print(f"\n{'context':<24}{'calls':>7}{'captures':>10}  needs")
    for chip, (n, caps) in sorted(per_context.items(),
                                  key=lambda kv: -kv[1][1]):
        need = []
        if caps < MIN_CAPTURES:
            need.append(f"{MIN_CAPTURES - caps} more capture(s) on separate days")
        if n < MIN_CALLS:
            need.append(f"{MIN_CALLS - n} more call(s)")
        print(f"{chip:<24}{n:>7}{caps:>10}  {', '.join(need) or 'ready'}")

    closest = min(
        (r for r in table if min(r["a_calls"], r["b_calls"]) >= 3),
        key=lambda r: ((MIN_CAPTURES - min(r["a_captures"], r["b_captures"]))
                       + (MIN_CALLS - min(r["a_calls"], r["b_calls"])) / 10),
        default=None)
    if closest:
        print(f"\nClosest pair: {closest['a']} vs {closest['b']} — "
              f"{'; '.join(closest['needs'])}.")
    print("\nCaptures, not calls, are what is short. Twenty more alarm calls from")
    print("one more morning move nothing; four mornings with the same situation")
    print("on each is what turns a cell into an answer.")


if __name__ == "__main__":
    main()
