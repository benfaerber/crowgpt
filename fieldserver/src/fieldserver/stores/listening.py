"""Listening pools graded ten trials at a time, and the guards that keep them honest.

Two rules are enforced here rather than left to the page, because both are
invisible when they fail. `dose` never crosses a block boundary, so a sitting
cannot end up comparing arms across two different evenings — 0038 measured 8.3
points of listener drift overnight. And `results` refuses to compute anything
until `reveal_at` trials are answered, so a page you return to cannot be stopped
the moment it looks resolved.
"""

import json
from datetime import datetime, timezone

from .db_base import Database, utc_now

#: The response scale, signed toward the FIRST clip of the pair. 0 is a real
#: answer and the most important one on the scale: pooled over every saved
#: pairwise sitting Ben marked 13% of trials "too close to call" while a resolved
#: 0.628 left-button bias filled the rest, which is what forcing a pick buys.
GRADES = (-2, -1, 0, 1, 2)

#: Named so the page and the export agree, and so a defect tag is a fixed
#: vocabulary rather than free text. Every one of these is a word Ben has already
#: used about this model. Refreshed 2026-08-11: "choppy" and "modem" retired —
#: codec artifacts the 0063 decoder finetune removed, unused across the 88 trials
#: since. The 0067 tail listen's "ghost crow" entered briefly and was renamed by
#: Ben mid-second-sitting to "blowing-dust" ("like when you blow out an old thing
#: and dust comes out" — his words, more accurate; no answer ever stored "ghost").
#: Retired tags stay valid in stored answers; only new ones are checked.
#: "hoarse2" arrived mid-dust-sitting (2026-08-12), Ben's word for a
#: screamy, many-crows texture that is "better than hoarse1 but still
#: audibly hoarse" — a brighter cousin of blowing-dust, named in his notes
#: before the tag existed.
DEFECTS = ("blowing-dust", "hoarse2", "scratchy", "hoarse", "too-short",
           "wrong-contour", "background")


class ListeningStore(Database):
    """Pools, their trials, and one answer per trial."""

    # --- building a pool ---

    def create_pool(self, name, question, clip_dir, trials,
                    dose_size=10, reveal_at=None, spec=None,
                    cooldown_minutes=None) -> dict:
        """Insert a pool and its trials in one transaction.

        `trials` arrive already ordered and blocked by the builder — this does
        not shuffle, because the balance that makes doses poolable is a property
        of the ordering and belongs with the code that can guarantee it.
        """
        if not name:
            raise ValueError("a pool needs a name")
        if not question:
            raise ValueError("a pool needs a question, written before the first clip")
        if dose_size < 1:
            raise ValueError("dose_size must be at least 1")
        if not trials:
            raise ValueError("a pool needs trials")
        reveal_at = len(trials) if reveal_at is None else int(reveal_at)
        if reveal_at < 1:
            raise ValueError("reveal_at must be at least 1")

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM listening_pools WHERE name = ?", (name,)).fetchone()
            if existing:
                raise ValueError(f"a pool named {name!r} already exists")
            cursor = conn.execute(
                "INSERT INTO listening_pools "
                "(name, question, clip_dir, dose_size, reveal_at, spec, "
                " cooldown_minutes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (name, question, str(clip_dir), dose_size, reveal_at,
                 json.dumps(spec) if spec is not None else None,
                 cooldown_minutes, utc_now()))
            pool_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO listening_trials "
                "(pool_id, ordinal, block, kind, anchor_clip, first_clip, "
                " second_clip, first_arm, second_arm, facts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(pool_id, n, t.get("block", n // dose_size), t.get("kind", "compare"),
                  t.get("anchor_clip"), t["first_clip"], t["second_clip"],
                  t["first_arm"], t["second_arm"],
                  json.dumps(t.get("facts")) if t.get("facts") is not None else None)
                 for n, t in enumerate(trials)])
        return self.pool(pool_id)

    def set_pacing(self, pool_id, cooldown_minutes=..., dose_size=...) -> dict:
        """Change how a pool is served, without touching what it measures.

        Cooldown and dose size are the two properties safe to move mid-pool: both
        are about pacing, so neither can invalidate an answer the way changing an
        arm or a trial order would. Everything else about a registered pool is
        fixed.

        `...` means "leave alone" so that `None` can mean "remove the cooldown".
        """
        sets, values = [], []
        if cooldown_minutes is not ...:
            if cooldown_minutes is not None and int(cooldown_minutes) < 1:
                raise ValueError("cooldown_minutes must be at least 1, or None")
            sets.append("cooldown_minutes = ?")
            values.append(None if cooldown_minutes is None else int(cooldown_minutes))
        if dose_size is not ...:
            if dose_size is None or int(dose_size) < 1:
                raise ValueError("dose_size must be at least 1")
            sets.append("dose_size = ?")
            values.append(int(dose_size))
        if not sets:
            return self.pool(pool_id)
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM listening_pools WHERE id = ?",
                                (pool_id,)).fetchone():
                raise ValueError(f"no pool {pool_id}")
            conn.execute(f"UPDATE listening_pools SET {', '.join(sets)} WHERE id = ?",
                         (*values, pool_id))
        return self.pool(pool_id)

    def delete_pool(self, pool_id) -> int:
        """Drop an unanswered pool. Refuses one that has been graded.

        The guard is here rather than only in the caller because a pool with
        answers in it is a measurement, and 0039 records what discarding those
        costs: 360 unheard bouts burned on three rebuilds chasing a JavaScript
        bug. Trials and answers go with it through ON DELETE CASCADE.
        """
        answered = self.pool(pool_id)
        if answered is None:
            raise ValueError(f"no pool {pool_id}")
        if answered["answered"]:
            raise ValueError(
                f"pool {pool_id} has {answered['answered']} answered trial(s); "
                "rename the replacement rather than discarding a measurement")
        with self._connect() as conn:
            conn.execute("DELETE FROM listening_pools WHERE id = ?", (pool_id,))
        return answered["trials"]

    # --- reading ---

    def pools(self) -> list[dict]:
        with self._connect() as conn:
            return [self._with_progress(conn, dict(row)) for row in conn.execute(
                "SELECT * FROM listening_pools ORDER BY id DESC")]

    def pool(self, pool_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM listening_pools WHERE id = ?",
                               (pool_id,)).fetchone()
            return self._with_progress(conn, dict(row)) if row else None

    def pool_by_name(self, name) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM listening_pools WHERE name = ?",
                               (name,)).fetchone()
            return self._with_progress(conn, dict(row)) if row else None

    def _with_progress(self, conn, pool) -> dict:
        """Counts and the cooldown clock, and nothing that could leak the result.

        Deliberately no per-arm breakdown: this is the payload the page polls
        every dose, and a running score in it would defeat `reveal_at`.
        """
        pool["spec"] = json.loads(pool["spec"]) if pool["spec"] else None
        total = conn.execute("SELECT COUNT(*) FROM listening_trials WHERE pool_id = ?",
                             (pool["id"],)).fetchone()[0]
        row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(a.answered_at) AS last FROM listening_answers a "
            "JOIN listening_trials t ON t.id = a.trial_id WHERE t.pool_id = ?",
            (pool["id"],)).fetchone()
        pool["trials"] = total
        pool["answered"] = row["n"]
        pool["remaining"] = total - row["n"]
        pool["can_reveal"] = row["n"] >= pool["reveal_at"]
        pool["last_answered_at"] = row["last"]
        pool["locked_for"] = self._locked_for(pool, row["last"])
        return pool

    def _locked_for(self, pool, last_answered_at) -> int:
        """Seconds until the next dose may be handed out. 0 when open.

        MEASURED FROM THE LAST ANSWER because that is the only timestamp that
        records work done. Starting the clock when a dose is served would charge a
        reload, and the same pool is graded from a phone and a laptop.

        A dose already in progress is never locked: `dose()` returns the same
        unanswered trials until they are answered, so a partially graded block has
        to stay reachable or a reload mid-dose would strand it for half an hour.
        """
        minutes = pool.get("cooldown_minutes")
        if not minutes or not last_answered_at or pool["remaining"] <= 0:
            return 0
        if self._mid_dose(pool):
            return 0
        elapsed = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(last_answered_at)).total_seconds()
        return max(0, int(round(minutes * 60 - elapsed)))

    def _mid_dose(self, pool) -> bool:
        """Is the current block partly graded?

        A block is the unit the cooldown gates, so finishing one you started is
        always allowed and starting the next one is what waits.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT t.block, COUNT(a.id) AS done, COUNT(*) AS size "
                "FROM listening_trials t "
                "LEFT JOIN listening_answers a ON a.trial_id = t.id "
                "WHERE t.pool_id = ? GROUP BY t.block "
                "HAVING done > 0 AND done < size ORDER BY t.block LIMIT 1",
                (pool["id"],)).fetchone()
        return row is not None

    def dose(self, pool_id) -> list[dict]:
        """The next unanswered trials: whole blocks, never a partial one.

        A BLOCK IS THE BALANCE UNIT AND `dose_size` IS THE APPETITE, and they are
        not the same number. A block holds every arm in equal proportion, which is
        what makes doses poolable across days — 0038 measured 8.3 points of
        listener drift overnight, so a dose that carried an uneven arm mix would
        turn drift into the dominant variable. Any whole number of balanced blocks
        is itself balanced, so a dose can be two blocks or five; it just cannot be
        one and a half.

        So this takes whole blocks while they fit inside `dose_size`, and raising
        `dose_size` from 10 to 20 on a pool built in blocks of ten hands out two
        blocks instead of one with the guarantee untouched. Setting it to 15 would
        still hand out ten, which is the honest behaviour rather than a silent
        half-block.

        The one exception is a block already part-graded: its remainder always
        comes first and always in full, because stranding the back half of a dose
        somebody started is worse than overshooting the appetite slightly.
        """
        pool = self.pool(pool_id)
        if pool is None:
            return []
        if pool["locked_for"]:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.* FROM listening_trials t "
                "LEFT JOIN listening_answers a ON a.trial_id = t.id "
                "WHERE t.pool_id = ? AND a.id IS NULL "
                "ORDER BY t.ordinal", (pool_id,)).fetchall()
            sizes = {r["block"]: r["n"] for r in conn.execute(
                "SELECT block, COUNT(*) AS n FROM listening_trials "
                "WHERE pool_id = ? GROUP BY block", (pool_id,))}
        if not rows:
            return []

        pending = {}
        for row in rows:
            pending.setdefault(row["block"], []).append(row)

        out = []
        for n, block in enumerate(sorted(pending)):
            waiting = pending[block]
            part_graded = len(waiting) < sizes[block]
            # The first block goes in whichever way it comes; later ones only if
            # the whole block fits, so a dose never ends mid-block.
            if n and len(out) + len(waiting) > pool["dose_size"]:
                break
            if n and part_graded:
                break
            for row in waiting:
                trial = dict(row)
                trial["facts"] = json.loads(trial["facts"]) if trial["facts"] else None
                out.append(trial)
            if len(out) >= pool["dose_size"]:
                break
        return out

    # --- answering ---

    def answer(self, trial_id, grade, defects=None, note=None, decision_ms=None,
               plays_anchor=None, plays_first=None, plays_second=None,
               engaged_ms=None) -> dict:
        """Record or replace the answer to one trial.

        TWO TIMES, AND ONLY ONE OF THEM MEANS ANYTHING. `decision_ms` is
        wall-clock from the trial rendering to this call, so it counts the tab
        sitting open — a 121 s median on the first dose of churn-spread-0053 was a
        walk away, not a judgement. It is kept because it is what every earlier
        session recorded. `engaged_ms` runs from the first play and pauses while
        the tab is hidden, and is the one to analyse.
        """
        if grade not in GRADES:
            raise ValueError(f"grade must be one of {list(GRADES)}")
        tags = list(defects or [])
        unknown = [t for t in tags if t not in DEFECTS]
        if unknown:
            raise ValueError(f"unknown defect tag(s): {', '.join(sorted(unknown))}")
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM listening_trials WHERE id = ?",
                                (trial_id,)).fetchone():
                raise ValueError(f"no trial {trial_id}")
            conn.execute(
                "INSERT INTO listening_answers "
                "(trial_id, grade, defects, note, decision_ms, "
                " plays_anchor, plays_first, plays_second, engaged_ms, answered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(trial_id) DO UPDATE SET "
                " grade = excluded.grade, defects = excluded.defects, "
                " note = excluded.note, decision_ms = excluded.decision_ms, "
                " plays_anchor = excluded.plays_anchor, "
                " plays_first = excluded.plays_first, "
                " plays_second = excluded.plays_second, "
                " engaged_ms = excluded.engaged_ms, "
                " answered_at = excluded.answered_at",
                (trial_id, grade, json.dumps(tags) if tags else None, note,
                 decision_ms, plays_anchor, plays_first, plays_second,
                 engaged_ms, utc_now()))
            row = conn.execute(
                "SELECT * FROM listening_answers WHERE trial_id = ?",
                (trial_id,)).fetchone()
        answer = dict(row)
        answer["defects"] = json.loads(answer["defects"]) if answer["defects"] else []
        return answer

    # --- reading out ---

    def rows(self, pool_id) -> list[dict]:
        """Every answered trial, un-randomised, for analysis or export.

        `grade_for_first` is as recorded; `preferred_arm` resolves the
        presentation order the builder randomised, so the caller never has to
        know which side a clip was played on.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.*, a.grade, a.defects, a.note, a.decision_ms, "
                "       a.plays_anchor, a.plays_first, a.plays_second, "
                "       a.engaged_ms, a.answered_at "
                "FROM listening_trials t "
                "JOIN listening_answers a ON a.trial_id = t.id "
                "WHERE t.pool_id = ? ORDER BY t.ordinal", (pool_id,)).fetchall()
        out = []
        for row in rows:
            trial = dict(row)
            trial["facts"] = json.loads(trial["facts"]) if trial["facts"] else None
            trial["defects"] = json.loads(trial["defects"]) if trial["defects"] else []
            grade = trial["grade"]
            trial["grade_for_first"] = grade
            if grade > 0:
                trial["preferred_arm"] = trial["first_arm"]
                trial["other_arm"] = trial["second_arm"]
            elif grade < 0:
                trial["preferred_arm"] = trial["second_arm"]
                trial["other_arm"] = trial["first_arm"]
            else:
                trial["preferred_arm"] = None
                trial["other_arm"] = None
            trial["margin"] = abs(grade)
            out.append(trial)
        return out
