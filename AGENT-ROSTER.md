# Agent roster

Who is working in this repo right now, and on what.

Several Claude sessions can be open at once — one restarting the field server,
one deep in a finetune, one editing the app — and from the outside they are
indistinguishable terminals. So every session takes a name, writes what it is
doing here, and answers to that name when asked. This file is to agents what
`GPU-CALENDAR.md` is to the card: the authority on who is doing what, read
before wondering and written before working.

**Convention.**

- **Take a name at the start of the session** — before the first substantive
  work, not when you remember to. Corvid names by tradition (Rook, Magpie,
  Jackdaw, Chough, Raven, Jay, Nutcracker, Treepie, Azure-winged…), but any
  name works as long as it is short, memorable, and **not already on an
  unstruck line below**. The name lasts the whole session; do not change it
  midway.
- **One line per session, newest at the top of Active.** Format:
  `- **Name** — since <date time> — <what you are doing now>. Updated <time>.`
- **Edit your own line in place** when the task changes or a milestone lands;
  don't append a new line per update. Never edit another agent's line, with
  one exception below. Keep the "what" concrete enough that Ben can tell
  whether it is safe to, say, restart the server or take the GPU — "rewriting
  `SyncEngine` retry logic, mobile only" beats "working on sync".
- **Strike your line through and move it to Done** when the session's work
  ends. Struck lines older than a week may be deleted by anyone tidying.
- **Stale lines:** a session can die without striking itself. Any agent may
  strike a line whose `Updated` stamp is more than a day old, noting
  `(struck as stale)`. If the session turns out to be alive, it un-strikes
  and refreshes the stamp — no harm done.
- **When Ben asks "what's your name?" / "who am I talking to?"**, answer with
  your roster name and what your line currently says, so the terminal and the
  file line up.
- **Subagents don't register.** They work under their parent's name; the
  roster tracks sessions Ben can actually talk to.

---

## Active

- **Daurian** — since 2026-10-21 21:11 — crowgpt.org attached to Cloudflare, Namecheap nameservers saved; waiting for DNS/HTTPS before enabling the prepared cawtalker.org redirect. Automatic checks every 15 minutes; metadata source committed as 65f5760, not deployed. Updated 2026-10-21 21:32.

- **Jackdaw** — since 2026-10-21 17:55 — open-source move done (public github.com/benfaerber/crowgpt, one-commit squash; old history on local branch `private-history`, purge needs Ben's OK, see TODO.txt). Then the project renamed CrowGPT across titles/app/dashboard/docs (dbe27b7) and the promo's call-type cards shipped (18fd253), both deployed to cawtalker.org. Five local commits unpushed. Server and GPU untouched. Updated 2026-10-21 22:05.

- **Jynx** — since 2026-09-11 — promo reorder + em-dash scrub shipped (d5bb83c, be46cce, a67298e; cawtalker.org not deployed, on Ben's word). Auto-grading investigation delivered: findings in FUTURE.txt (top entry). Read-only on the DB; not touching the server or the GPU. Updated 2026-09-11 18:05.

- **Cissa** — since 2026-09-10 — minimal, distributable corpus crawler
  shipped in `corvidcrawler/` (Xeno-canto + Macaulay only, per Ben): own
  venv, 100 tests green, Xeno-canto verified live into a scratch DATA_DIR.
  Macaulay's search endpoint answers scripts with a bot check, so the CSV
  export is the route and the crawler says so. CLAUDE.md source rule updated.
  Not touching the server or the GPU. Updated 2026-09-10 17:30.

- **Chough (CrowGPT)** — since 2026-09-09 — experiment 0086 finished 16:38; all three rates trained, selected candidate and 48-trial capacity-0086 pool ready. GPU reservation released. Field dashboard/API remains healthy as `cawtalker-fieldserver` on :5100. Listening pending. Updated 2026-09-10 17:09.


- **Currawong** — since 2026-08-22 — CawScout: generation graduated into
  `fieldserver/src/fieldserver/scout/` (`make -C fieldserver scout`), then
  Davis + Utah county shipped the same day — 5 CHM tiles in
  data/experiments/0083-chm/, 0083 build_region.py with 1,650 m elevation
  mask, 45 targets published to instance/scout.json. Now running the field
  server: `make field` up at 16:58 on commit 31a6b29, health green, all
  three workers ready (they hold the GPU for inference as usual).
  Updated 2026-08-22 16:58.

- **Piapiac** — since 2026-08-20 — tree audit shipped (a963a87): hub
  safetensors now gitignored before anyone `git add -A`'d 170 MB of weights
  into history; tsbuildinfo untracked. Rest of the unstaged pile judged
  commit-worthy, left for its owners. Not touching the server or the GPU.
  Updated 2026-08-20.

- **Bokmakierie** — since 2026-08-20 — CawTalker t-shirt design canvas shipped
  (working files in `data/tshirt/`, gitignored): two front prints, a back
  print, and a placement mockup in the business-card style, saved as an
  artifact for Ben. Design only; not touching the server or the GPU.
  Updated 2026-08-20.

- **Nutcracker** (un-struck, same session) — since 2026-08-19 (Wed) — promo
  favicon made circular (icon-16/32/512 regenerated from the mark, masked to
  a disc), bundle rebuilt, cawtalker.org deployed and verified serving the
  new bytes. Promo only; server and GPU untouched. Updated after deploy.

- **Alpine** — since 2026-08-18 (Tue) 20:10 — doc tidy-up pass shipped across
  CLAUDE.md, the READMEs, FUTURE.txt, the outreach scripts and one tool
  docstring, per Ben's request this session. Docs only; not touching the
  server or the GPU. Updated 20:30.

- **Chihuahuan** — since 2026-08-18 (Mon) — logo rollout shipped (…a2be7e8,
  7b9470f): icons + favicons derive from `images/cawtalker-logo.svg`, brand
  spelled CawTalker everywhere user-facing; FlyingCrow replaced by the static
  mark, and tapping it now flies the promo flock across the screen (new
  `Flock.tsx`, same sprite). cawtalker.org redeployed, latest build on the
  Pixel 8, waiting on Ben's tap. Pixel 10 install on his word. Server
  untouched. Updated 2026-08-18 20:35.

- **Treepie** — since 2026-08-18 (Mon) — client-side CrowGPT prototype shipped
  as experiment 0080: crowgpt2 in the browser via ONNX/WASM, demo serving at
  http://127.0.0.1:8092/ (serve.py, left running for Ben). Nothing deployed
  to promo. Not touching the field server or the GPU. Updated 2026-08-18
  19:30.

- **Jay** — since 2026-08-17 (Mon) — assessing how the Song Meter Micro 2 +
  trail cam research station fits the pipeline, against `phases/roof-station.md`
  and `data-collection.md`. Reading only; not touching the server or the GPU.
  Updated 2026-08-17.

- **Rook** — since 2026-08-16 (Sun) — Bluetooth remote shutter shipped
  (0c0cc68): volume keys claimed as a record trigger behind a new setting,
  tests green; build installed on the Pixel 8, waiting on Ben's remote test.
  Mobile only; not touching the server or the GPU. Updated 13:55.

- **Magpie** — since 2026-08-15 (Sat) ~22:00 — promo site traffic analysis
  delivered (mostly AI crawlers + scanners; ~8–15 real visitors from the
  Instagram plug); wrote it up in FUTURE.txt ("The hard promo push"). Not
  touching the server or the GPU. Updated 22:20.

- **Raven** — since 2026-08-13 (Thu) — CawScout field sprint with Ben:
  compass beam + live GPS, Directions links, sighting dates/photos with
  server archive, family descriptions (server adopts re-pushed edits),
  by-ear labels on the capture timeline, brand font on wordmark titles,
  and the header's sun/temp scouting-window advice (Poe-calibrated).
  0084 field log: 2 hits (#1, #4 "The Scholars" 3 crows) / 2 nulls, both
  nulls at the predator-heavy pins. Pixel 8 current; Pixel 10 on Ben's
  word. GPU free; server restarted, healthy. Updated 2026-08-21 ~13:00.

- **Corbie** — since 2026-08-15 (Sat) ~19:00 — HF release repo shipped:
  faerber/crowgpt (private) holds both CrowGPTs as safetensors + JSON via
  the new `crowgpt.hub` (68477e3), verified bit-identical through a fresh
  download, CPU only; card's license section now attributes Xeno-canto per
  Ben's scope extension (58302a1). Earlier: Crow Chat model picker (180f293),
  Forget button (ad7c754). Not holding the server or the GPU. Updated 21:50.

- **Chough** — since 2026-08-15 (Sat) 19:45 — idle mode shipped, twice tested
  by Ben: fixed the self-masking floor his playback test found (hot buffers
  now excluded from the noise-floor window) and gave the armed bar a live
  phase + meter readout. Latest build on the Pixel 8; wire 23 live. Waiting
  on his re-test. Updated 21:45.

- **Jackdaw** — since 2026-08-15 (Sat) 20:15 — built this roster system and
  wired it into `CLAUDE.md`. Updated 20:15.

## Done

- ~~**Chough** — 2026-09-09/10 — CrowGPT3 candidate 0085 trained and evaluated successfully by 00:15; failed validation/structure screen, 24 diagnostic clips saved, GPU released. Morning results recorded 2026-09-10.~~

- ~~**Sirkeer** — 2026-08-21 — CawScout section shipped on the promo site:
  the score / the map / the visits beside the field screenshot
  (`app-cawscout.jpg`), nav link added, cawtalker.org deployed and verified.
  Changes landed inside Ben's bulk commit 94e25c2. Server and GPU
  untouched.~~

- ~~**Nutcracker** — 2026-08-18 (Tue) — cohesion pass landed in ten commits:
  demo.py → crowgpt.pages (templates byte-identical, shim keeps all 49
  imports), AppServices 1301→~880 via Annotations/Identity/BackfillRegions
  collaborators, analyzer/thresholds.py (constants importable in 8 ms, three
  subprocess workarounds deleted), config_seed.py, dashboard CaptureDetail →
  four sections + api/upload.ts, mobile pure-move ladder (CallCard,
  PullTranscripts, serverTypes, RecorderContext), load_calltypes out of
  cli.py's GPU-claiming import. All suites green; field server restarted and
  healthy; deferred seams written to FUTURE.txt. Untouched: Rook's and
  Chough's live regions, raw-audio, useRecorder's idle block.~~

- ~~**Nutcracker** — 2026-08-16 (Sun) — dead-code sweep landed in four commits
  (mobile ee81f5d, promo f3b275c, fieldserver 3dc01be, crowgpt 701ac55): ~975
  lines out, all suites green, field server restarted and healthy on the new
  code. Left alone: Chough's idle-mode files, Raven's finetune/night scripts,
  Corbie's hub.~~
