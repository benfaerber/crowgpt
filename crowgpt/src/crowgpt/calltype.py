"""Call type per bout: a head trained on bouts, then the rest of the corpus.

WHY NOT THE HEAD THAT ALREADY SHIPS. Experiment 0018 measured it against human
labels on bouts: right 56% of the time, where always answering "alarm call"
scores 69%. It says alarm to three quarters of everything. Its 0.904-0.975 AUC
is a true fact about crow-tools' one-second single-call segments and does not
survive the move to 2.4-second multi-call bouts. A head is a fact about its unit.

Retrained on bouts, the same simple model reaches 0.918-0.951 under
recording-grouped CV, so the unit and the label count were never the problem.

THE SPLIT DISCIPLINE IS THE WHOLE POINT. The head learns only from human labels
whose recording is in the generator's TRAIN split. Human labels in the test
split are seen by nothing — not the head, not the generator — so the final
question ("can it produce an alarm call on demand?") is answered against labels
no part of the system has touched. Judging a generator with a head that learnt
the same recordings would look like success whatever happened.
"""

import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
LABELS = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"

# FOUR, WHERE THE FLEET HAS FIVE, AND IT IS THE DATA THAT DECIDES IT.
#
# These are the classes the vendored flags can actually produce (corpus.py's
# FLAG_TO_CORE). The fleet's vocabulary also has `flight call` — the class with
# the best AUC in the project — and no flag maps to it, so no bout of this
# corpus can carry it and the generator cannot be asked for one. Nobody chose
# that; it fell out of which corpus each side was built from.
#
# Written out rather than derived because the ORDER is a trained artifact: these
# become prefix tokens, so moving one silently re-points every checkpoint in
# results/ at the wrong class. `check_vocabulary()` is what makes a change loud
# instead — deriving would make it silent, which is how this drifted in the
# first place.
CORE = ("alarm call", "begging", "call", "song")

# What this corpus cannot say, named so a join with the fleet has to handle it
# rather than discover it. See FUTURE.txt, "Merging crowgpt with a future crow
# translate", which turns on exactly this gap.
MISSING_FROM_CORE = ("flight call",)

UNKNOWN = "unknown"
MIN_OVERLAP = 0.25
MIN_CONFIDENCE = 0.60
MIN_PER_CLASS = 25


def _corpus():
    """corpus.py, imported by path — it is a script, and pure stdlib on purpose.

    That is what lets this module read the one label space from a venv carrying
    torch rather than BirdNET.
    """
    spec = importlib.util.spec_from_file_location(
        "crowtools_corpus", REPO / "pipelines" / "ingest" / "corpus.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flag_map():
    return _corpus().FLAG_TO_CORE


def check_vocabulary():
    """Fail loudly if CORE has drifted from the corpus it is derived from.

    Two ways it can go wrong, and both were silent until this existed: a flag
    added upstream grows the reachable set and CORE stops covering the data, or
    the fleet's class list changes underneath and `flight call` stops being the
    only thing missing. Either way the prefix tokens no longer mean what the
    trained checkpoints think they mean, which is not a failure that shows up in
    a loss curve.
    """
    corpus = _corpus()
    reachable = set(corpus.FLAG_TO_CORE.values())
    if reachable != set(CORE):
        raise ValueError(
            f"CORE {CORE} no longer matches what the flags can produce "
            f"({sorted(reachable)}). Retrain before changing it: these are "
            f"prefix tokens and the order is baked into every checkpoint.")
    gap = set(corpus.CORE_CLASSES) - set(CORE)
    if gap != set(MISSING_FROM_CORE):
        raise ValueError(
            f"the fleet's classes moved: expected {sorted(MISSING_FROM_CORE)} "
            f"to be the only one this corpus cannot reach, got {sorted(gap)}.")


def human_labels(path=LABELS):
    """recording id -> [(start, end, {core labels})], from the vendored file."""
    flags_to_core = _flag_map()
    payload = json.loads(Path(path).read_text())
    out = defaultdict(list)
    for key, flags in payload["labels"].items():
        recording, start, end = key.rsplit("-", 2)
        cores = {core for flag, core in flags_to_core.items() if flags.get(flag)}
        if cores:
            out[recording].append((int(start), int(end), cores))
    return out


def label_bouts(index, labels, species="american-crow"):
    """Which bouts overlap a human label, and with what.

    A quarter-second of real overlap is required: a bout that merely abuts a
    labelled span shares no audio with it.
    """
    tagged = {}
    for position, row in enumerate(index):
        if row["species"] != species or row["recording_id"] not in labels:
            continue
        low, high = row["start_sec"], row["start_sec"] + row["dur_sec"]
        found = set()
        for start, end, cores in labels[row["recording_id"]]:
            if min(high, end) - max(low, start) > MIN_OVERLAP:
                found |= cores
        if len(found) == 1:
            tagged[position] = next(iter(found))
    return tagged


class BoutCallTypes:
    """Trains on the labelled bouts it is allowed to see, predicts the rest."""

    def __init__(self, min_confidence=MIN_CONFIDENCE):
        self.min_confidence = min_confidence
        self.model = None
        self.classes = None

    def fit(self, features, targets):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        counts = Counter(targets)
        keep = np.array([counts[t] >= MIN_PER_CLASS for t in targets])
        features, targets = features[keep], np.asarray(targets)[keep]
        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=3000, class_weight="balanced"),
        ).fit(features, targets)
        self.classes = list(self.model.classes_)
        return {"trained_on": int(keep.sum()), "classes": dict(Counter(targets))}

    def predict(self, features):
        """A call type, or unknown where the head is not confident enough.

        A wrong pseudo-label is worse than none: the generator would learn to
        associate a prefix token with the wrong sound, and nothing downstream
        would notice.
        """
        proba = self.model.predict_proba(features)
        best = proba.argmax(axis=1)
        confident = proba.max(axis=1) >= self.min_confidence
        return [self.classes[b] if ok else UNKNOWN for b, ok in zip(best, confident)]

    def forced(self, features):
        """The head's best guess with no confidence threshold, and how sure.

        Labelling the corpus wants the threshold — a wrong pseudo-label costs
        more than a missing one. Measuring whether the generator responds to its
        prefix token wants the opposite: abstentions there would hide the answer
        behind a number tuned for a different job, and "declined to guess" is not
        the same finding as "guessed wrong".
        """
        proba = self.model.predict_proba(features)
        best = proba.argmax(axis=1)
        return [self.classes[b] for b in best], proba.max(axis=1)
