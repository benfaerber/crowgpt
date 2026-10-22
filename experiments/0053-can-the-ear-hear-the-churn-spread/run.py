"""Can the ear hear the churn spread 0051 measured?

(Numbered 0053: 0052 was taken by "are continuous latents perceptually
forgiving", which was running while this was written. Colliding numbers are
already a documented nuisance in this project — there are two 0017s, two 0018s,
two 0025s and two 0027s — so this stepped aside rather than adding a fifth.)

0051 found that the pinned channel bucket moves stage-0 churn across a 0.215
range inside one checkpoint, and that 0044 had pinned the worst bucket of
thirteen. Churn is triage — 0049 put it at 1 for 2 as a ranker and demoted it —
so the finding earns a sitting and settles nothing on its own.

THIS POOL IS BUILT FOR SPREAD, NOT FOR A SHIPPING DECISION. 0044 through 0050
each asked "which of these two" about arms differing by almost nothing and four
of five came back unresolved; Ben's summary was *"most are so close it is hard to
pick."* So the three arms here span the whole measured range and every pair is
carried equally, which puts three points on the churn-versus-audibility curve
instead of one:

    channel-000   0.927   the bucket 0044 pinned; the fallback sink, overshoots
    channel-205   0.859   the on-target bucket, -0.009 from real audio
    channel-081   0.722   nobody would ship this; the calibration point

    real audio    0.868   (0046)

  pair               churn apart
  000 vs 081            0.205
  205 vs 081            0.137
  205 vs 000            0.068

If the widest pair is inaudible, churn is finished as a predictor of what a
listener hears and that is a decisive answer for two minutes of GPU per future
arm. If the ordering comes through, churn is calibrated against his ear for the
first time and every later arm can be pre-screened for free.

THE INSTRUMENT IS NEW AND THAT IS DELIBERATE. Graded response rather than a
side, an anchor in every trial, ten trials to a dose, and results withheld until
all 120 are in. The reasoning is in `crowgpt/pool.py` and
`fieldserver/alembic/versions/0024_listening_doses.py`; the short version is that
pooled over 317 saved pairwise trials P(chose left) = 0.628, resolved, while
P(chose first-heard) = 0.495 — the old rig lost about 45% of its power to a
button.

Costs about six minutes of GPU and no listener time to build.
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

OUT = Path(__file__).resolve().parent
BOUTS = REPO / "data" / "crowgpt" / "bouts"
MODEL = HERE / "results" / "model-channel256"
CLIPS = HERE / "results" / "listening-pools" / "churn-spread-0053"

SPECIES = "american-crow"
SR = 24000
NAME = "churn-spread-0053"
QUESTION = ("Which clip sounds closer to the reference recording? Judge the "
            "<strong>timbre</strong> — how much it sounds like a real crow's "
            "voice — not the length and not how many caws it has. "
            "\"They are the same\" is a real answer; use it whenever you cannot "
            "tell.")

#: Churn from 0051, carried into each trial so the analysis can regress the
#: listener's grade on the gap it was supposed to be able to hear.
CHURN = {"channel-000": 0.927, "channel-205": 0.859, "channel-081": 0.722}

BLOCKS = 12
PAIRS = [("channel-000", "channel-081", 3),
         ("channel-205", "channel-081", 3),
         ("channel-205", "channel-000", 3)]
CATCH_PER_BLOCK = 1

#: Where the two spending ledgers live. Saved sittings record a bout per trial;
#: a dose pool claims its bouts at build time in `bouts.json` beside its clips.
#: The first build of this experiment used an offset constant instead and drew 132
#: bouts of which 121 had already been played to Ben, most through ABX sittings
#: that reveal the answer every trial. Spending is read, never remembered.
SESSIONS = HERE / "results" / "listening"
POOLS = HERE / "results" / "listening-pools"

#: Registration is a separate step run in fieldserver's own venv, so nothing
#: here needs the operator secret. `tools/register_pool.py` writes through
#: ListeningStore against a database Alembic has already migrated.
REGISTER = "uv run --project fieldserver python fieldserver/tools/register_pool.py"


def needed():
    """Clips per arm, counting the catch arm's extra draw."""
    per_block = {}
    for arm_a, arm_b, n in PAIRS:
        per_block[arm_a] = per_block.get(arm_a, 0) + n
        per_block[arm_b] = per_block.get(arm_b, 0) + n
    per_block[PAIRS[0][0]] = per_block.get(PAIRS[0][0], 0) + CATCH_PER_BLOCK
    return {arm: n * BLOCKS for arm, n in per_block.items()}


def main():
    from crowgpt.gpu import claim

    claim()

    from crowgpt.pool import (BlockedPool, ClipWriter, claim_bouts,
                              held_out_reals, spent_bouts)
    from crowgpt.progress import Run
    from crowgpt.sample import Sampler

    wanted = needed()
    total_clips = sum(wanted.values())
    trials = BLOCKS * (sum(n for _, _, n in PAIRS) + CATCH_PER_BLOCK)
    reals = trials + BLOCKS * CATCH_PER_BLOCK

    run = Run("0053 — CHURN SPREAD POOL", ["generate", "real", "build"])
    writer = ClipWriter(CLIPS)
    clips_by_arm = {}
    # clip name -> bout index, so a pool can be audited against the ledger later.
    # The first build recorded no mapping at all, which is why the contamination
    # had to be found by recomputing the draw rather than by reading the pool.
    bout_of = {}
    try:
        with run.stage("generate") as stage:
            sampler = Sampler(MODEL / "model.pt", token_dir=None)
            done = 0
            for arm, count in wanted.items():
                kept, seed, short = [], 0, 0
                # Over-draw: 0051 saw 4 to 39 sub-second fragments per 40 clips
                # depending on the bucket, and a short clip cannot go in — it
                # loses on sight (0044) and ClipWriter refuses it.
                while len(kept) < count and seed < count * 8:
                    audio = sampler.audio(SPECIES, seed=seed, channel=arm)
                    seed += 1
                    if len(audio) / SR < 1.0:
                        short += 1
                        continue
                    kept.append(writer.add(f"{arm}-{len(kept):03d}", audio))
                    done += 1
                    if done % 10 == 0:
                        stage.update(done, total_clips, extra=arm)
                if len(kept) < count:
                    raise SystemExit(
                        f"{arm}: only {len(kept)}/{count} clips over 1.0s in "
                        f"{seed} draws ({short} short)")
                clips_by_arm[arm] = kept
                run.note(f"{arm}: {len(kept)} clips, {short} short discarded")
            del sampler
            stage.update(total_clips, total_clips)

        with run.stage("real") as stage:
            stage.update(0, reals)
            already = spent_bouts(SESSIONS, POOLS)
            drawn, available = held_out_reals(
                BOUTS, SPECIES, reals, exclude=already)
            anchors, catch, claimed = [], [], []
            for n, (index, audio) in enumerate(drawn):
                name = writer.add(f"real-{n:03d}", audio)
                (anchors if n < trials else catch).append(name)
                claimed.append(index)
                bout_of[name] = index
                stage.update(n + 1, reals)
            # Claimed before the pool is registered, and before a single trial is
            # graded: a pool can sit unheard for weeks and its bouts are gone the
            # moment it is built.
            claim_bouts(CLIPS, NAME, claimed)
            run.note(f"{len(anchors)} anchors + {len(catch)} catch bouts; "
                     f"{len(already)} already spent, "
                     f"{available - reals} unheard recordings left")

        with run.stage("build") as stage:
            stage.update(0, 1)
            builder = BlockedPool(PAIRS, catch_per_block=CATCH_PER_BLOCK, seed=52)
            built = builder.build(BLOCKS, clips_by_arm, anchors, catch,
                                  facts_by_arm=CHURN)
            payload = {
                "name": NAME,
                "question": QUESTION,
                "clip_dir": str(CLIPS),
                "dose_size": builder.dose_size,
                "reveal_at": len(built),
                "trials": built,
                "spec": {
                    "experiment": "0053",
                    "model": MODEL.name,
                    "arms": CHURN,
                    "real_churn": 0.868,
                    "pairs": [[a, b, n] for a, b, n in PAIRS],
                    "blocks": BLOCKS,
                    "bout_of": bout_of,
                    "seconds": writer.seconds,
                },
            }
            (OUT / "pool.json").write_text(json.dumps(payload, indent=2))
            stage.say(f"{len(built)} trials in {BLOCKS} blocks of "
                      f"{builder.dose_size}")

    except Exception as error:
        run.note(f"FAILED: {type(error).__name__}: {error}")
        raise

    print(f"\n{len(built)} trials, {BLOCKS} blocks of {builder.dose_size}")
    print(f"clips: {CLIPS}")
    print(f"register with:\n  {REGISTER} {OUT / 'pool.json'}")


if __name__ == "__main__":
    main()
