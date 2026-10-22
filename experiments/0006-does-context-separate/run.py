"""Can a model tell what the crow was reacting to, from the call alone?

The prior question before any "I see a dog" classifier is worth building: is the
context *in* the signal at all? If crows use the same alarm for a dog and for a
person, no amount of data helps — you would be predicting the world from
something that does not encode it.

This answers it the only honest way, and refuses to answer when it cannot.

Two things make or break it:

  Grouped cross-validation, split by capture. Two caws from the same bout are
  nearly the same data point, so a random split puts near-duplicates on both
  sides and reports an accuracy that means nothing. Every fold here holds out
  whole recordings.

  A permutation baseline. With small n, "80% accurate" is unreadable — the
  question is what that number looks like when the labels are shuffled and there
  is provably nothing to learn. If the real score sits inside that distribution,
  there is no signal, however good it looked.

Usage:
    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0006-does-context-separate/run.py [context_a] [context_b]
"""

import contextlib
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.media import DEFAULT_DB, media_dir  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Below these the answer is "collect more", not a number. Reporting an accuracy
# from four recordings would be the most misleading thing this script could do.
MIN_PER_CLASS = 10
MIN_GROUPS_PER_CLASS = 4
PERMUTATIONS = 200


def labelled_spans(db_path: Path, a: str, b: str):
    """Human-labelled calls carrying one of two witnessed contexts.

    Human labels only, and context attached to a *label* rather than a capture:
    a model trained on the analyzer's own guesses would be learning its bias,
    and capture-level context would credit every situation to every call.
    """
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """
        SELECT l.capture_id, l.start_sec, l.end_sec, ce.key AS context,
               m.storage_ref
        FROM context_events ce
        JOIN labels l ON l.id = ce.label_id
        JOIN captures c ON c.id = l.capture_id
        JOIN media m ON m.capture_id = c.id AND m.kind = 'audio'
                    AND m.upload_state = 'complete'
        WHERE ce.key IN (?, ?) AND c.keep = 1
        ORDER BY l.capture_id, l.start_sec
        """,
        (a, b),
    ).fetchall()
    return [dict(r) for r in rows]


def embed(spans):
    """One BirdNET embedding per labelled call."""
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer

    with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
        analyzer = Analyzer()

    vectors, groups, labels = [], [], []
    by_file: dict[str, list[dict]] = {}
    for span in spans:
        by_file.setdefault(span["storage_ref"], []).append(span)

    for ref, items in by_file.items():
        path = media_dir() / ref
        if not path.exists():
            print(f"  missing audio: {ref}", file=sys.stderr)
            continue
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            rec = Recording(analyzer, str(path), min_conf=0.01)
            rec.extract_embeddings()
        # BirdNET embeds on a fixed 3s grid; take the window each label starts in.
        by_start = {round(s["start_time"], 2): np.array(s["embeddings"])
                    for s in rec.embeddings}
        starts = sorted(by_start)
        for item in items:
            nearest = min(starts, key=lambda s: abs(s - item["start_sec"]), default=None)
            if nearest is None:
                continue
            vectors.append(by_start[nearest])
            groups.append(item["capture_id"])
            labels.append(item["context"])
    return np.array(vectors), np.array(groups), np.array(labels)


def grouped_score(X, y, groups) -> float:
    """Mean accuracy with whole recordings held out."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import LeaveOneGroupOut

    splitter = LeaveOneGroupOut()
    scores = []
    for train, test in splitter.split(X, y, groups):
        if len(set(y[train])) < 2:
            # A fold whose training set lost a class entirely teaches nothing.
            continue
        model = LogisticRegression(max_iter=2000, class_weight="balanced")
        model.fit(X[train], y[train])
        scores.append(model.score(X[test], y[test]))
    return float(np.mean(scores)) if scores else float("nan")


def main() -> None:
    a = sys.argv[1] if len(sys.argv) > 2 else "human_gives_food"
    b = sys.argv[2] if len(sys.argv) > 2 else "raptor_overhead"
    print(f"Does the call distinguish '{a}' from '{b}'?\n")

    spans = labelled_spans(Path(os.environ.get("FIELD_DB", DEFAULT_DB)), a, b)
    counts = Counter(s["context"] for s in spans)
    groups_per_class = {
        key: len({s["capture_id"] for s in spans if s["context"] == key})
        for key in counts
    }
    for key in (a, b):
        print(f"  {key:<20} {counts.get(key, 0):3} calls "
              f"across {groups_per_class.get(key, 0)} recording(s)")

    short = [k for k in (a, b)
             if counts.get(k, 0) < MIN_PER_CLASS
             or groups_per_class.get(k, 0) < MIN_GROUPS_PER_CLASS]
    if short:
        print(f"\nNot enough yet — need {MIN_PER_CLASS}+ calls across "
              f"{MIN_GROUPS_PER_CLASS}+ separate recordings per class.")
        print("Short on:", ", ".join(short))
        print("\nNo accuracy is reported, on purpose. A number from this much "
              "data would be noise wearing a result's clothes.")
        return

    print("\nExtracting embeddings…")
    X, groups, y = embed(spans)
    print(f"  {len(X)} vectors, {len(set(groups))} recordings\n")

    real = grouped_score(X, y, groups)
    print(f"grouped accuracy: {real:.3f}")

    rng = np.random.default_rng(20260726)
    null = []
    for _ in range(PERMUTATIONS):
        # Shuffled *within* the group structure, so the baseline keeps the same
        # class imbalance and the same folds — only the link to the audio is cut.
        null.append(grouped_score(X, rng.permutation(y), groups))
    null = np.array([s for s in null if not np.isnan(s)])
    p = float((null >= real).mean())

    print(f"shuffled labels:  {null.mean():.3f} ± {null.std():.3f}")
    print(f"p ≈ {p:.3f}  ({PERMUTATIONS} permutations)")
    print()
    if p < 0.05:
        print("There is signal. The call carries something about the context.")
    else:
        print("No signal at this sample size. Either the call does not encode "
              "the difference, or there is not enough data to see it — this "
              "cannot tell those apart, and neither can any other test.")


if __name__ == "__main__":
    main()
