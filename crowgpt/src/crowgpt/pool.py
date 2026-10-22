"""Building a listening pool that can be graded ten trials at a time.

Every sitting until now was one page, one evening, 50-60 trials, and Ben's
verdict on that shape was *"It is hard to grade because most are so close it is
hard to pick."* This builds the other shape: a pool of trials on disk, registered
with fieldserver, served a dose at a time at `/listen/`.

FOUR DESIGN RULES, ALL OF THEM PAID FOR ALREADY.

**Blocks, not sessions.** 0038 measured 8.3 points of listener drift between
evening and morning on identical weights, so a dose is a session and twenty doses
are twenty sessions. If a dose carried one arm, drift would become the dominant
variable and this would be worse than one sitting. So every block of `dose_size`
holds the same mixture of pairs, and both arms of a comparison sit inside one
trial. Drift then cancels within a block and pooling across blocks is sound.

**Spread, not the shipping decision.** 0044 through 0050 asked "which of these
two" about arms that differ by almost nothing, and four of five came back
unresolved. A pool should include an arm nobody would ship, as the calibration
point: if the listener cannot hear the *wide* contrast, the offline instrument
that ordered the arms is finished as a predictor of audibility, which is a
decisive answer. If he can, the instrument is calibrated against his ear for the
first time.

**An anchor in every trial.** Real-versus-generated is the one comparison he is
reliable on — 67/70 on catch trials across every saved sitting — so each trial
carries a real held-out bout as a fixed reference and the question is which clip
is closer to it. That also makes cross-block comparison legitimate, which 0038
says raw good-rates are not.

**A real bout is consumed, never reused, and spending is READ rather than
remembered.** One bout per recording, so the same bird cannot supply two
references, and `spent_bouts` derives what is gone from disk.

The first version of this module took an `offset` constant instead, and it was
wrong immediately: 0053 drew 132 bouts at offset 0 and **121 of them had already
been played**, most through ABX sittings that reveal the answer every trial. A
catch trial Ben can pass by recognition instead of by ear inflates the one number
that says the sitting was readable. 0039's docstring had already named the bug
class — "three hardcoded constants deep, each one meaning 'however many the last
experiment happened to take'. That is correct exactly once." — and an offset
reintroduced it.

TWO LEDGERS, ONE UNION, because the systems were blind both ways. Saved sittings
record a `bout` per trial under `results/listening/*/session-*.json`, which is
what 0039 and 0052 read. A dose pool commits its bouts the moment it is built and
may sit ungraded for weeks, so it writes `bouts.json` beside its clips under
`results/listening-pools/*/`. `spent_bouts` unions both, so a pool built today
cannot spend what a pool built yesterday claimed and has not yet been graded.

Clips are written as wavs rather than embedded as data URIs: a 200-trial pool
would be a 40 MB HTML file, and the page fetches only the ten it needs.

Registration is deliberately not here. This writes `pool.json`; `fieldserver`'s
`tools/register_pool.py` puts it in the database from the server's own venv, so a
sitting can be built by a script that never holds the operator secret.
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from crowgpt.demo import MIN_GRADEABLE_SECONDS

SR = 24000

#: Real audio's stage-0 churn (0046). Carried into every trial's facts so the
#: analysis can ask whether the ear agrees with the offline ordering.
REAL_CHURN = 0.868


def _write(path, samples, sample_rate=SR):
    """Peak-normalise and write one clip.

    Normalising every arm including the anchor, because PLAN-TIMBRE recorded the
    second protocol lesson the expensive way: leave levels alone and loudness
    becomes the cue the listener actually uses.
    """
    samples = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(samples))) or 1.0
    sf.write(path, np.clip(samples / peak * 0.95, -1.0, 1.0), sample_rate,
             format="WAV", subtype="PCM_16")
    return len(samples) / sample_rate


class ClipWriter:
    """Names and writes the pool's audio, refusing anything ungradeable."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.seconds = {}

    def add(self, name, samples, sample_rate=SR):
        seconds = len(np.asarray(samples)) / sample_rate
        if seconds < MIN_GRADEABLE_SECONDS:
            # 0044: a sub-second clip loses on sight, and filtering it after the
            # fact is what produced a one-sided bias across six experiments.
            raise ValueError(
                f"{name} is {seconds:.2f}s, under {MIN_GRADEABLE_SECONDS}s — "
                "over-draw and filter at build time instead")
        filename = f"{name}.wav"
        self.seconds[filename] = _write(self.folder / filename, samples, sample_rate)
        return filename


class BlockedPool:
    """Trials arranged so every block holds the same mixture of pairs.

    `pairs` is a list of (arm_a, arm_b, per_block) and `catch_per_block` adds
    real-versus-generated trials that validate the sitting. Presentation order
    within a trial is randomised, and which arm went first is recorded — the
    response is a grade toward the first clip, so the analysis has to undo it.
    """

    def __init__(self, pairs, catch_per_block=1, seed=0):
        self.pairs = list(pairs)
        self.catch_per_block = catch_per_block
        self.rng = np.random.default_rng(seed)
        self.trials = []

    @property
    def dose_size(self):
        return sum(n for _, _, n in self.pairs) + self.catch_per_block

    def build(self, blocks, clips_by_arm, anchors, catch_reals, facts_by_arm=None):
        """One pass per block, drawing clips without replacement.

        Raises rather than recycling a clip: reusing generated audio across
        trials is pseudo-replication, and it would inflate n against a listener
        who may well recognise the repeat.
        """
        facts_by_arm = facts_by_arm or {}
        taken = defaultdict(int)
        used_anchors = 0
        used_catch = 0

        def draw(arm):
            index = taken[arm]
            pool = clips_by_arm[arm]
            if index >= len(pool):
                raise ValueError(
                    f"ran out of {arm} clips at trial {len(self.trials)}: "
                    f"have {len(pool)}, need more")
            taken[arm] += 1
            return pool[index]

        for block in range(blocks):
            entries = []
            for arm_a, arm_b, per_block in self.pairs:
                for _ in range(per_block):
                    entries.append(("compare", arm_a, draw(arm_a), arm_b, draw(arm_b)))
            for _ in range(self.catch_per_block):
                if used_catch >= len(catch_reals):
                    raise ValueError("ran out of catch bouts")
                arm_b = self.pairs[0][0]
                entries.append(("catch", "real", catch_reals[used_catch],
                                arm_b, draw(arm_b)))
                used_catch += 1

            # Shuffled inside the block so a dose does not present the pairs in a
            # fixed order; the block's composition is what has to stay constant,
            # not the sequence within it.
            self.rng.shuffle(entries)
            for kind, arm_a, clip_a, arm_b, clip_b in entries:
                if used_anchors >= len(anchors):
                    raise ValueError("ran out of anchor bouts")
                anchor = anchors[used_anchors]
                used_anchors += 1
                flip = bool(self.rng.integers(2))
                first_arm, first_clip = (arm_b, clip_b) if flip else (arm_a, clip_a)
                second_arm, second_clip = (arm_a, clip_a) if flip else (arm_b, clip_b)
                self.trials.append({
                    "block": block,
                    "kind": kind,
                    "anchor_clip": anchor,
                    "first_clip": first_clip,
                    "second_clip": second_clip,
                    "first_arm": first_arm,
                    "second_arm": second_arm,
                    "facts": {
                        "first_churn": facts_by_arm.get(first_arm),
                        "second_churn": facts_by_arm.get(second_arm),
                        "real_churn": REAL_CHURN,
                    },
                })
        return self.trials


def spent_bouts(sessions_dir, pools_dir=None):
    """Every bout index already committed, from both ledgers on disk.

    A malformed file is skipped rather than fatal — a half-written session from a
    sitting that was closed mid-dose should not stop the next pool from being
    built — but an unreadable file cannot be *seen*, so anything it spent would
    silently come back into circulation. Hence the two ledgers are small, plain
    JSON, and written last.

    INDICES ARE THE FRAGILE KEY. They point into one store's index.jsonl and
    stop meaning anything at a re-extract (0050). `spent_recordings` is the
    durable view and the one new pools should retire against; this stays for
    the index-keyed history and same-store checks.
    """
    used = set()
    for path in Path(sessions_dir).glob("*/session-*.json"):
        try:
            session = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for trial in session.get("trials", []):
            if trial.get("bout") is not None:
                used.add(int(trial["bout"]))
    for path in Path(pools_dir or sessions_dir).glob("*/bouts.json"):
        try:
            claimed = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        used.update(int(i) for i in claimed.get("bouts", ()))
    return used


def spent_recordings(sessions_dir, pools_dir=None):
    """Every recording whose audio has already faced Ben, keyed durably.

    Recording ids survive a re-extract and span stores — a 6 s pool and a 3 s
    sitting that drew from the same recording spent the same bird — which is
    exactly what bout indices could not say. Sources: the `recordings` list a
    pool's `bouts.json` carries since the 2026-08-11 migration, and the
    `spent-recordings.json` sidecar that migration derived from the 822
    index-keyed session records while the index → recording join still
    existed. Same tolerance as `spent_bouts`: malformed files are skipped.
    """
    used = set()
    roots = [Path(sessions_dir)]
    if pools_dir is not None:
        roots.append(Path(pools_dir))
    for root in roots:
        for path in [root / "spent-recordings.json",
                     *root.glob("*/bouts.json")]:
            try:
                entry = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            used.update(str(r) for r in entry.get("recordings", ()))
    return used


def claim_bouts(clip_dir, name, indices, recordings=()):
    """Write this pool's ledger entry, so the next pool can see the spend.

    `recordings` is the durable half of the claim; pass it always — the
    indices half dies at the next re-extract and exists for same-store
    tooling that predates the recording key.
    """
    path = Path(clip_dir) / "bouts.json"
    path.write_text(json.dumps(
        {"pool": name, "bouts": sorted(int(i) for i in indices),
         "recordings": sorted(str(r) for r in recordings)}, indent=2))
    return path


def held_out_reals(bouts_dir, species, count, exclude=(), exclude_recordings=(),
                   min_seconds=MIN_GRADEABLE_SECONDS):
    """Held-out bouts, one per recording, that nobody has heard.

    Drawn from the CURRENT store: 0050 recorded that every earlier sitting drew
    from v1 and those indices stopped meaning the same thing after the rebuild,
    so a count carried over from before it is not a count of anything.

    `exclude_recordings` is the durable retirement — feed it
    `spent_recordings(...)` and a bout is skipped because its *recording*
    already faced Ben, in any store, at any cap. `exclude` remains the
    same-store index form.

    Returns `(pairs, available)` where `available` is how many unheard bouts the
    pool held before this draw — the number worth printing, because it is the
    budget the next sitting has left.
    """
    from crowgpt.tokens import BoutStore

    exclude = set(int(i) for i in exclude)
    exclude_recordings = set(str(r) for r in exclude_recordings)
    store = BoutStore(bouts_dir)
    splits = store.split(seed=0)
    seen, ordered = set(), []
    for i in splits["test"]:
        row = store.index[i]
        if row["species"] != species or row["recording_id"] in seen:
            continue
        if row["n_samples"] / SR < min_seconds:
            continue
        # Retired by recording, not by index: a bout whose recording already
        # supplied a reference is a second look at the same microphone, and 0042
        # measured the microphone moving timbre 6.2x further than the bird.
        seen.add(row["recording_id"])
        if i in exclude or str(row["recording_id"]) in exclude_recordings:
            continue
        ordered.append(i)
    if len(ordered) < count:
        raise ValueError(
            f"only {len(ordered)} unheard held-out {species} bouts remain, "
            f"need {count} — every sitting spends them and they do not come back")
    return [(i, store.audio(store.index[i])) for i in ordered[:count]], len(ordered)
