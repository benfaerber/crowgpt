"""The listening test as a recorded measurement, not a vibe.

BirdNET cannot hear "robotic", so the only instrument for it is a person — and
until now that instrument's readings were thrown away. `demo.html` kept the
score in a JavaScript variable and nothing else, so every sitting anyone ever
did evaporated when the tab closed. The README's listening log is three prose
verdicts with no n, no blinding and no per-clip record, and it is the entire
human evidence base for a year of work.

That log has been right twice when the numbers were wrong: it ranked American
Crow and Raven as the strong species when the raw per-species scores said Raven
was worst (0016 found the scores were unnormalised), and it called the output
bimodal before the confidence histogram confirmed 28% near-zero and 25% strong
(0018). An instrument with that record deserves to have its readings kept.

THE TARGET IS CHANCE, WHICH INVERTS THE USUAL READING. This is not a score to
maximise. The model wins when the listener CANNOT tell its output from a real
recording, so 50% is success and anything above it is the remaining distance.
That makes "I could not tell" a claim which needs an interval like any other:
twelve trials and a shrug is not evidence of anything, so a session only counts
as a win if its interval both contains chance and is narrow enough to exclude
the alternative.

SESSIONS POOL BY CHECKPOINT FINGERPRINT, NEVER BY NAME. `results/model/` is
overwritten every time a better model appears, so a folder name identifies a
slot rather than a set of weights. Sessions are keyed on a hash of `model.pt`,
which means several short sittings on the same weights add up to one verdict and
two sittings on different weights can never be silently averaged together.
"""

import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from crowgpt.metrics import bootstrap_ci, paired_difference

CHANCE = 0.5
USEFUL_WIDTH = 0.20


class Checkpoint:
    """The weights a session was about, identified by content."""

    def __init__(self, name, fingerprint, facts=None):
        self.name = name
        self.fingerprint = fingerprint
        self.facts = facts or {}

    @classmethod
    def load(cls, folder):
        folder = Path(folder)
        weights = folder / "model.pt"
        if not weights.exists():
            raise FileNotFoundError(f"no model.pt in {folder}")

        digest = hashlib.sha256()
        with weights.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)

        facts = {}
        history = folder / "history.json"
        if history.exists():
            blob = json.loads(history.read_text())
            facts["best_val"] = blob.get("best_val")
            facts["steps"] = blob.get("history", [{}])[-1].get("step")
        return cls(folder.name, digest.hexdigest()[:12], facts)

    def as_dict(self):
        return {"name": self.name, "fingerprint": self.fingerprint, **self.facts}


class Session:
    """One sitting: the trials answered, and which weights they judged."""

    def __init__(self, payload, path=None):
        self.path = Path(path) if path else None
        self.checkpoint = payload.get("checkpoint") or {}
        self.fingerprint = self.checkpoint.get("fingerprint")
        self.subject = payload.get("subject", "ben")
        self.started_at = payload.get("started_at")
        self.note = payload.get("note", "")
        self.trials = [t for t in payload.get("trials", []) if t.get("answer")]

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()), path)

    def matches(self, checkpoint):
        return self.fingerprint == checkpoint.fingerprint

    def fingerprints(self):
        """Every checkpoint this sitting judged.

        One for an ordinary sheet, two for an interleaved one. Sessions written
        before trials carried their own checkpoint fall back to the session-level
        one, so the sittings already on disk keep reporting unchanged.
        """
        found = {t.get("checkpoint", {}).get("fingerprint")
                 for t in self.trials if t.get("checkpoint")}
        found.discard(None)
        return found or ({self.fingerprint} if self.fingerprint else set())

    def view(self, fingerprint):
        """This sitting restricted to one checkpoint's trials.

        Returned as a stand-in Session so the report does not have to know
        whether a sitting was interleaved.
        """
        tagged = [t for t in self.trials if t.get("checkpoint")]
        if not tagged:
            return self
        kept = [t for t in tagged
                if t["checkpoint"].get("fingerprint") == fingerprint]
        clone = copy.copy(self)
        clone.trials = kept
        clone.checkpoint = next((t["checkpoint"] for t in kept), self.checkpoint)
        clone.fingerprint = fingerprint
        return clone

    def __len__(self):
        return len(self.trials)


class Discrimination:
    """Can the listener tell generated from real, and how sure are we.

    The headline is the rate with an interval, because that is the number every
    other result in this project is quoted in. d-prime and criterion come along
    as description: percent correct conflates sensitivity with a bias toward
    answering "generated", and the listener knows the deck is half and half, so
    the bias is real and worth seeing. Neither gates a decision.
    """

    def __init__(self, trials, seed=0):
        self.trials = list(trials)
        self.seed = seed
        self.correct = np.array([bool(t["correct"]) for t in self.trials], dtype=float)

    @property
    def n(self):
        return int(self.correct.size)

    @property
    def rate(self):
        return float(self.correct.mean()) if self.n else float("nan")

    @property
    def ci(self):
        if self.n < 2:
            return (float("nan"), float("nan"))
        return bootstrap_ci(self.correct, seed=self.seed)

    @property
    def width(self):
        low, high = self.ci
        return float(high - low)

    def _counts(self):
        said_generated = [t for t in self.trials if t["answer"] == "generated"]
        generated = [t for t in self.trials if t["truth"] == "generated"]
        real = [t for t in self.trials if t["truth"] == "real"]
        hits = sum(1 for t in said_generated if t["truth"] == "generated")
        false_alarms = sum(1 for t in said_generated if t["truth"] == "real")
        return hits, len(generated), false_alarms, len(real)

    def rates(self):
        """Hit and false-alarm rates, log-linear corrected.

        Adding half a count to each cell and one to each total keeps a perfect
        or an empty cell from sending d-prime to infinity, which a short sitting
        reaches easily.
        """
        hits, generated, false_alarms, real = self._counts()
        if not generated or not real:
            return float("nan"), float("nan")
        return (hits + 0.5) / (generated + 1), (false_alarms + 0.5) / (real + 1)

    def _z(self, p):
        from scipy.stats import norm

        return float(norm.ppf(p))

    @property
    def dprime(self):
        hit_rate, false_rate = self.rates()
        if not np.isfinite(hit_rate) or not np.isfinite(false_rate):
            return float("nan")
        return self._z(hit_rate) - self._z(false_rate)

    @property
    def criterion(self):
        hit_rate, false_rate = self.rates()
        if not np.isfinite(hit_rate) or not np.isfinite(false_rate):
            return float("nan")
        return -0.5 * (self._z(hit_rate) + self._z(false_rate))

    @property
    def verdict(self):
        """Three outcomes, because "could not tell" needs power to mean anything."""
        if self.n < 2:
            return "no data"
        low, high = self.ci
        if low > CHANCE or high < CHANCE:
            return "can tell"
        if self.width <= USEFUL_WIDTH:
            return "cannot tell"
        return "underpowered"

    def by_species(self):
        buckets = defaultdict(list)
        for trial in self.trials:
            buckets[trial.get("species", "?")].append(trial)
        return {name: Discrimination(rows, self.seed) for name, rows in sorted(buckets.items())}

    def decision_seconds(self):
        times = [t["decision_ms"] / 1000 for t in self.trials if t.get("decision_ms")]
        return float(np.median(times)) if times else float("nan")

    def versus(self, other):
        """Paired against another checkpoint on the conditions they share.

        Most of the variance in whether a clip is spotted is the clip, not the
        model, so comparing the same conditions cancels it. Unpaired, two
        sittings of sixty tell you almost nothing about each other.
        """
        mine = {t["condition_index"]: t for t in self.trials if t.get("condition_index") is not None}
        theirs = {t["condition_index"]: t for t in other.trials if t.get("condition_index") is not None}
        shared = sorted(set(mine) & set(theirs))
        if len(shared) < 5:
            return None
        a = np.array([float(mine[i]["correct"]) for i in shared])
        b = np.array([float(theirs[i]["correct"]) for i in shared])
        return paired_difference(a, b, seed=self.seed)


class ListeningLog:
    """Every saved session, pooled by the weights it judged."""

    def __init__(self, root):
        self.root = Path(root)

    def sessions(self):
        if not self.root.exists():
            return []
        out = []
        for path in sorted(self.root.glob("**/*.json")):
            try:
                out.append(Session.load(path))
            except (json.JSONDecodeError, KeyError):
                continue
        return out

    def by_checkpoint(self):
        """Trials grouped by the weights that produced them, not by sitting.

        An interleaved sheet judges two checkpoints in one session, so pooling
        whole sessions would put both models in the same bucket and average
        exactly what the interleaving exists to separate.
        """
        pooled = defaultdict(list)
        for session in self.sessions():
            for fingerprint in session.fingerprints():
                pooled[fingerprint].append(session.view(fingerprint))
        return dict(pooled)

    def report(self):
        out = []
        for fingerprint, sessions in self.by_checkpoint().items():
            trials = [t for s in sessions for t in s.trials]
            out.append({
                "fingerprint": fingerprint,
                "model": sessions[0].checkpoint.get("name", "?"),
                "sessions": len(sessions),
                "discrimination": Discrimination(trials),
                "per_session": [Discrimination(s.trials) for s in sessions],
                "notes": [s.note for s in sessions if s.note],
            })
        return sorted(out, key=lambda row: -row["discrimination"].n)
