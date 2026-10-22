# CrowGPT

Monorepo for the CrowGPT project — decoding crow calls with AI. Start from
`README.md` and `phases/` for the plan.

## Status: prototype, not deployed

One user, one fleet, running on a laptop on a home network. Nothing is public.
No TLS; enrollment is a single shared secret. Treat "how would this behave with
a thousand contributors" as a design question worth answering, not a problem to
solve today.

## Every session takes a name

Before starting substantive work, pick a name (corvid names by tradition),
register it on a line in `AGENT-ROSTER.md`, and keep that line current — what
you are doing now, with an `Updated` timestamp, edited in place as the work
moves. Strike the line when the session's work ends. The file explains its own
conventions, including how stale lines get struck.

The roster exists because several sessions run at once and Ben cannot tell the
terminals apart. Two consequences: when he asks "what's your name?", answer
with your roster name and what your line says; and when your work could
collide with someone — the server, the GPU, a file another agent is deep in —
read the roster first, the way you read `GPU-CALENDAR.md` before taking the
card.

## The two phones

| | Pixel 10 Pro | Pixel 8 |
|---|---|---|
| adb serial | `5B280DLCH000C7` | `43180DLJH002B4` |
| adb product | `blazer` | `shiba` |
| server device row | **10** | **9** |
| role | Ben's daily phone, real field recordings | throwaway, agents may use it freely |

**Never do anything destructive to the Pixel 10.** No purges, no uninstalls, no
seeding, no clearing app data. Read-only inspection is fine. Install updates
only when asked, and only with `make install-app` (which uses `adb install -r`
and preserves the local store).

Target a specific handset with `DEVICE=<serial>`. With **one** phone attached the
Makefile picks it automatically, which is how the wrong one gets flashed; with
two it refuses and makes you name one. `make wireless` puts a phone on wireless
adb so it stays listed, which keeps the count above one on purpose.

Device rows 1, 3, 4 and 8 are dead enrollments from before the contributor
layer — the same phones, re-enrolled after reinstalls. They still own captures,
so they are kept rather than deleted. Only 9 and 10 are live.

**Sync is push-only.** The app never pulls from the server, so anything changed
server-side is invisible to the phone. That rule is what stops a stale server
copy overwriting a field recording, and it stays.

**Restore is the one exception**, in Settings. It pulls captures the phone does
*not* have and never touches one it does — a phone that has lost a capture has
no truth to contradict. Capture 69 survived a reinstall only because it was on
the server, and until this existed there was no way to get it back: safe and
unreachable.

## Most of the capture data is not real

The corpus is mostly **seeded archive clips and test uploads**. A handful of
genuine field recordings sit among them, and the only thing telling them apart
is the **★ Keep flag** (`captures.keep`) the recordist sets by hand.

This matters constantly and is easy to forget:

- **Never present a count over all captures as a finding about crows.** Species
  totals, call-type totals and the calls × context matrix are dominated by
  seeded audio from other continents and by the same test clip uploaded several
  times.
- A number is about the *pipeline* unless it filters on `keep`. Say which it is.
- Deletions and purges must not touch kept captures. `mobile/tools/seed_captures.py`
  refuses to clear them, and anything similar should too.
- Detected calls are the model's guesses. Only rows in `labels` are human ground
  truth, and until recently there were none at all.

## The field server is Claude's to run

Ben delegated it: restart `make field` whenever server-side code changes, without
asking. Every schema migration runs at `create_app()`, so a server left up on old
code silently lacks new columns and routes — that already cost one sync, where a
newer phone pushed fields an older server accepted and discarded.

`make field-stop`, then `make field`. Verify with `/api/health` before calling
the work done. Restarting touches no data.

**Schema is Alembic's, on the server.** No store creates a table or adds a
column any more; `create_app` runs `upgrade head` and then refuses to start if
the database is not the shape the migrations describe. Author a change with
`make -C fieldserver schema-revision M="what it does"`, and use
`batch_alter_table` for anything SQLite has no ALTER for — dropping a column,
changing a NOT NULL. `make -C fieldserver schema-check` prints drift.

Nothing lives in the stores any more: the contributor backfill, the last
schema/data coupling, moved into revision 0027 on 2026-08-09, and `schema.py`
tolerates no legacy columns — any drift it reports is real.

**Compatibility turns on `WIRE_VERSION`, not the commit count.** It lives in
`fieldserver/src/fieldserver/core/build_info.py` with its history in the comment, and
`REQUIRED_WIRE_VERSION` in `mobile/src/domain/compatibility.ts` mirrors it. Raise
both in the same commit that starts sending a new field. Tooling, UI and analysis
changes must not touch either — an earlier version compared commit counts and
called a server three tooling commits behind incompatible, which is how a warning
becomes noise.

## There are two to-do lists, split by horizon

`TODO.txt` is **the next three days**. `FUTURE.txt` is everything after that.

When Ben mentions something to build later rather than now, decide which one it
belongs in and write it there — a bullet with enough context that it is still
actionable in a month, not just a title. Delete or strike entries when they
ship.

The split is a horizon, not an importance. Something can be the most important
idea in the project and still belong in `FUTURE.txt` because it should not be
started this week; something can be trivial and belong in `TODO.txt` because it
is blocking a field session tomorrow. An item graduates from `FUTURE.txt` to
`TODO.txt` when it has a shape and a reason to happen now.

`FUTURE.txt` is also where questions go that are not work yet — consequences of
choices already made, asymmetries worth watching, decisions with a "revisit
when" attached. Several of its entries should end in "decided not to", which is
a real outcome worth writing down.

Both are plain text on purpose: scratch lists, not trackers. Anything needing
real discussion belongs in `phases/`, and anything needing a measurement belongs
in `experiments/`.

## Write experiments down

A question answered with thirty lines of numpy belongs in `experiments/`, as a
numbered folder with a `run.py` and a `README.md`. Not in a scratchpad, where a
dozen of them have already evaporated — "is my mic good enough", "was it
alarming at the hawk", "would a denoiser help" were each measured properly and
then lost.

Record the boring answers too. A measured null is worth as much as a positive
one and is the kind nobody remembers having done. End every README with what the
answer *changed* — a threshold, a purchase, a decision not to build something —
and say so plainly when it changed nothing.

Scripts resolve captures by server id through the database rather than
hardcoding a storage_ref or a home directory. The corpus is gitignored, so the
numbers are the durable part.

Distinct from `phases/`, which is the programme decided in advance.

## Listening sittings go through the pool system, no exceptions

Anything Ben grades by ear is a **listening pool** on the field server —
built by the experiment, registered with
`fieldserver/tools/register_pool.py`, clips in
`crowgpt/results/listening-pools/<name>/` — and graded from the dashboard's
Listening panel, which is the one place he looks. The pool system doses
(default 20 a block), enforces the cooldown between doses, refuses results
before `reveal_at` answers, takes graded −2..+2 responses with a fixed
defect vocabulary, and stores answers server-side. Do not build a
standalone sitting page, and do not add pacing anywhere else: on 2026-08-10
a PairPage got its own dosing because a grep missed
`fieldserver/stores/listening.py`, and Ben's first stop for his own sitting
was a dashboard that answered "Nothing to grade". Two instruments for one
sitting is the same rot as two vocabularies for one distinction.

`PairPage`/`ComparePage`/`RatingPage` in `crowgpt/demo.py` remain for quick
labelled diagnostics — a handful of rows answered in one visit, like 0057's
scream page — never for a sitting that produces a statistic.

## Working style

- **Commit as you go.** After each self-contained change — a working feature, a
  passing experiment, a doc update — make a focused git commit with a clear
  message. Don't let work pile up uncommitted.
- **Never push or commit to a remote without being asked.** Local commits only,
  unless explicitly told otherwise.
- The corpus (audio + its DB) lives in `data/` and is **gitignored** —
  never commit it.
- **This repo is headed for open source, and `corvidcrawler/` is the only
  corpus fetching it may carry.** It speaks to **Xeno-canto and the Macaulay
  Library**, the two sources Ben cleared for distribution on 2026-09-10, and
  those two are the only sources this tree may name — in code, comments,
  docs, tests, commit messages. Everything else in `data/` arrived through
  private tooling in another repo: never name that tooling, its repo, or any
  other source anywhere here. Say "the corpus tooling". The tree was scrubbed
  to this standard on 2026-08-07; do not reintroduce anything. Nothing from
  the private tooling gets vendored here beyond what `corvidcrawler/` already
  holds without asking Ben first.

  Corpus provenance, and what may be published when, are Ben's call and
  settled — not questions for agents to re-open, gate on, or annotate in
  docs. When something is ready to publish, ask Ben; do not write licensing
  analysis into the tree.
- **Long-running commands write live status through `crowgpt.progress.Run`,
  and `data/progress/<slug>.json` is the only record.** There are no
  `PROGRESS.txt` files any more, anywhere — the text half was removed
  2026-08-09 after stale copies littered the tree and a shared path let two
  runs overwrite each other. A terminal that wants the old `cat`-able view
  runs `make watch`, which renders the JSON on demand
  (`crowgpt/src/crowgpt/progress.py` as a script, stdlib only).

  The operator dashboard's Training panel lists `data/progress/*.json` through
  `/api/training` — one file per run, active runs first — so a run that only
  prints to stdout is invisible to Ben; he is not watching the terminal an
  agent started. Use `crowgpt.progress.Run`; do not hand-roll a status file.
  One file per run means several jobs report at once — a single shared file
  was the design until a scan and a finetune overwrote each other's state.
  Same-titled runs share a slug, so a restart replaces its own card rather
  than growing a second one. `Run` also carries the traceback into the file
  when a stage raises, which is the difference between a failed overnight run
  that says why and one that just stopped.

  Three rules that follow, all of them learned by getting them wrong:

  - **Write more often than every ten minutes.** The server marks a run stale
    after 600 s without a write (`STALE_AFTER` in
    `fieldserver/src/fieldserver/api/training.py`) and the panel then shows a
    live run as hung. Only `Run.write()` refreshes the clock, and it is called
    by `stage.update()` — so a stage that computes silently for an hour looks
    dead the whole time.
  - **Give every long stage a progress callback, and thread it through.**
    Tokenising the corpus is one to two hours and training is several more;
    neither reports itself unless asked. `TokenWriter.run(on_progress=...)`,
    `Trainer.run(on_eval=..., on_step=...)` exist for exactly this. `on_eval`
    alone is not enough — at `eval_every=500` that is nine minutes between
    writes, which is inside the stale window by luck rather than design.
  - **Count across the whole job, not per sub-part.** A bar that resets to zero
    for each split reads as a stall. Sum the totals first and offset into them.

  The same applies to any long job outside crowgpt: if it runs unattended, it
  reports through `Run` (`sys.path.insert` of `crowgpt/src` is enough — the
  module is stdlib-only), and its `data/progress` file is what makes it
  visible.

## Layout

- `mobile/` — the field app (Expo/React Native); records, labels, syncs on demand
- `fieldserver/` — CRUD + ingest API for the app, plus the operator dashboard
- `analyzer/` — BirdNET inference: a path in, findings out. No server, no DB.
- `fieldserver/worker/` — polls for analysis jobs and calls the analyzer
- `dashboard/` — the operator dashboard (Vite + React), served by fieldserver
- `promo/` — the public promo page, a compiled bundle fieldserver serves at `/promo`;
  every number on it is hardcoded at build time, so it reads no store and takes no token
- `crowgpt/` — generating crow calls; own venv carrying torch *and* birdnetlib
- `corvidcrawler/` — the corpus crawler: Xeno-canto and the Macaulay Library into `data/`; own venv
- `pipelines/` — batch experiments, no UI (e.g. Phase 3 representation)
- `phases/` — the phased plan and dated results
- `data/` — shared corpus, gitignored (`DATA_DIR` overrides the location)
