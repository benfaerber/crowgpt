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

- **Fish Crow** — since 2026-11-25 18:33 — reviewed `cdb8ef8` for Ben (read-only), then rebuilt the dashboard's Kept scans detail: the row and the opened view show the scanner's whole answer (photo ranking and box, calls, co-detections, visitor labels), and `shared/scan` now holds the result-reading code the dashboard and the promo both compile in. Committed locally. Local `make field` restarted on it (:5100, healthy) and is my instance now; two test photo scans of mine sit in the local pile (ids 3, 4). NOT deployed, promo not republished. GPU, phones, hosted box untouched. Updated 2026-11-26 13:20.

- **Tufted Jay** — since 2026-11-22 16:40 — owl film with real mobbing footage committed (6b56755, 19c9660); preview `data/video/crowgpt-owl-preview.mp4` sent to Ben, waiting on his review. Footage cut data-side under `data/video/footage`. Nothing running; GPU, server, phones, hosted box untouched; nothing pushed. Updated 2026-11-22 17:40.

- ~~**Whiskyjack** — since 2026-11-22 15:28 — 0112 (CrowGPT/Perch no better than BirdNET on meaning; CrowGPT counts crows better; Perch confirms posture), 0113 (one crow's graded calling reads context, 0.665), 0114 (context token: narrow null, mostly crowd). All committed (397b06b, 6135a6e, 66a0487); GPU released 16:57. Server, phones, hosted box untouched; nothing pushed. Updated 2026-11-22 16:58.~~

- **Piapiac** — since 2026-11-22 15:20 — corpus page quality indicators committed (remark text, grades, labels, other species, timed annotations); local `make field` restarted on it (:5100, healthy). Waiting on Ben's look. NOT deployed. Phones, GPU, hosted box untouched. Updated 2026-11-22 15:50.

- **Alala** — since 2026-11-21 18:44 — for Ben, the archive-remarks path, all committed locally: 0104–0108, 0109 (crow-count head, 0.80 inside a call type), 0110 (frozen archive context heads outside the archives: begging 0.9996, roost 0.78 and mostly crowd, raptor mobbing 0.73), 0111 (begging head false alarms: 21% on hand-labelled archive files, 4% on winter phone recordings, right on all 24 kept captures — fails the pre-set bar; next step is a listening pool, in FUTURE). Idle now. Local field server is now Piapiac's instance (they restarted it; mine ended). Phones untouched; nothing pushed or deployed. Updated 2026-11-22 15:11.

- **Pinyon** — since 2026-11-21 18:42 — GPU released 21:05. Acted on Alala's audit: reverted `7185300` (`94d5e81`), corrected `0102/README.md` (`b4efa8d`), and completed pre-registered Experiment `0103-caw-level-and-posture-controls` (locked `2023-01-01` temporal holdout, all-non-crow BirdNET masking, caw-level CV + single-shot holdout, blind posture coding across 148 strict remarks). Server, phones, and GPU untouched; nothing pushed or deployed. Updated 2026-11-21 22:05.

- **Rook** — since 2026-11-16 17:15 — feature film (`promo/video`, `--film feature`, 6.8 min): preview with a cloned scratch voice is at `data/video/crowgpt-feature-preview.mp4` and `crowgpt-feature.blend`; waiting on Ben's review and narration before a final 1080p render (will book the GPU). Not using the GPU now. Updated 2026-11-21 15:46.

- **Raven** — since 2026-11-15 18:35 — scan labelling desk built and committed (51a41c1..4a812a2): revision 0041, `/api/scan-desk` + `/label/<id>`, the app's `LabelingScreen` compiled for the browser by `mobile/web`, dashboard Scans page with promote, Scan-page link. Local `make field` restarted on it (:5100, healthy, 0041 applied to the local `field.db`). NOT deployed: a deploy would ship Jay's 0094, and the promo is not republished. Phones and GPU untouched. Since then: desk blank-page fix (95fedb8), `coo`/`pop` call types and `known_speaking`/`stranger_speaking` contexts (df12e39, local config version moved), video picture in the desk, Scan page remembers kept recordings and the desk links back. Updated 2026-11-15 20:15.

- **Chough** — since 2026-11-14 15:00 — not repo work: global `gemini-image` Claude skill in `~/.claude/skills/`; crow gifs (flying, cawing, flying with a peanut) and a peanut asset under `~/Pictures/` (read `promo/src/assets/crow-caw.png` as a template, changed nothing in promo). Nothing in this tree, server, phones or GPU touched. Updated 2026-11-14 15:31.
- **Magpie** — since 2026-11-14 14:31 — pulled promo traffic for 11-06..11-13 (`make -C promo traffic DAYS=8`) and reported it to Ben; read-only, nothing committed. Server, phones and GPU untouched. Updated 2026-11-14 14:31.
- **Treepie** — since 2026-11-13 19:30 — yield measurement done; now ranking short clips for a soft click-in-a-tone call for Ben to label (CPU only, tooling kept with the corpus). GPU released. Server and phones untouched. Updated 2026-11-13 20:15.
- **Jackdaw** — since 2026-11-13 — Promo front-page split DEPLOYED by Ben 2026-11-20 (d6a8cfa..e94dc8e, version 52a91431): front 41 → 18 phone screens; crows/app/cawscout/cawdex pages; old anchors forwarded. Waiting on Ben's review. Vite dev server of mine on 0.0.0.0:5187 (LAN, for Ben's phone review); carousels added (48e115b). Traffic page live on field.crowgpt.org (a22e0d8). Box reboot for kernel/libc updates awaits Ben. Updated 2026-11-20.
- **Jay** — since 2026-11-12 — GPU released 2026-11-16 20:50. Done and committed today: 0096 (larger CrowGPT at 60k: 4.668 against CrowGPT2's 4.793), 0097 (CrowGPT2's size at 60k: 4.690, so it was mostly the steps), 0098 (trainer 2.7× faster with `sliced_loss` + `bucketed` + `token_budget`, all opt-in). Listening pool capacity-0096 is with Ben (18 of 54). Photo ID: the "not a corvid" verdict (0094, 2cf16f2) is committed, NOT deployed, waiting on Ben. Server and phones untouched. Updated 2026-11-16 20:55.
- **Nutcracker** — since 2026-11-10 20:00 — Instagram batch imported and re-analysed on field.crowgpt.org (captures 199-208); experiment 0089; region fix + per-account consent deployed (wire 24, revision 0036), FIELD_REGION=Utah live on the analyze worker. App onboarding committed (13bb9a1), APK NOT published. Emulator crowgpt-test headless with Metro and a local `make field` (:5100). Phones untouched. Updated 2026-11-10 21:10.
- **Daurian** — since 2026-11-06 19:39 — proxy/no-store, staged Turnstile and streaming upload hash deployed; all units healthy. Promo built and Chrome-tested, NOT published. Waiting for Ben’s widget/secret setup and Pixel 8 migration confirmation; DNS/firewall untouched, no push. Updated 2026-11-06 20:02.
- **Pica** — since 2026-11-06 — marketing plan written to phases/outreach.md; promo reordered, audited and deployed by Ben; traffic report fixed; Hub card fixed locally, NOT pushed; repo NOT pushed; promo dev server running on :5174 for Ben to review. Field server and GPU untouched. Updated 2026-11-06.
- **Hooded Crow** — since 2026-10-30 — hosting answers (0087, 0088); CawTalker→CrowGPT rename pass (5e6d9bd); Hub model card pushed to faerber/crowgpt (still private, flip is Ben's); stale-docs pass from a subagent survey (CLAUDE.md status, READMEs, Makefile help, TODO/FUTURE strikes, 18 stale roster lines struck). Server and GPU untouched. Then: HF links on README+promo, Apache 2.0 LICENSE+NOTICE, contact address to hello@crowgpt.org, dashboard keys renamed (62e87d1). Promo rebuilt locally, NOT deployed. Then: promo nav/footer link GitHub and HF by logo, HF link under the Hear-it players (built locally, NOT deployed). Then 2026-10-31: deploying the field server to the OVH VPS (ssh crowfield): venvs, systemd units, Caddy for field.crowgpt.org, instance copied; fixed deps.py Path import; FIELD_TRUST_PROXY ProxyFix.  DONE: field.crowgpt.org live over TLS, all units up; docs + TODOs written.  Then: app default URL = hosted; /preview APK page (877d807) deployed and a build published.  Then: enrollment gate in the app (4d6be97); /preview is request-access + dashboard Access page + invite links (6b3508c), deployed; promo got a request-access section (e818b6c, 6104fc2; built, NOT deployed). DONE: live CrowGPT on the promo (78c021b) — /api/demo shelf deployed to field.crowgpt.org (model-calltype checkpoint copied to the box; ~31 s a bout on CPU), promo built locally with the Ask-it-yourself buttons, NOT deployed (Ben runs `make -C promo deploy`). Updated 2026-10-31 21:12.


## Done

- ~~**Bushcrow** — 2026-11-22 21:14 → 2026-11-25 17:17 — completed experiments 0115–0121 (437b51c..d946a1f) and shipped the 0121-validated 3-part analyzer upgrade locally (cdb8ef8): retrained `american-crow` on uniform 1024-d `birdnet_window_mean` (`C=0.1`, pure `crow-tools` `rattle`, AUC 0.966; archive `none` left out per 0121), emitted `"rattle"` instead of `"call"` on American Crow, added true taxonomic raptor co-detections (`>= 0.70`, revision 0045) rendered as `"BirdNET also heard: <Species> (<conf>)"` in dashboard and promo scan, rebuilt local static bundles, and restarted local `make field` (:5100 healthy on cdb8ef8). Phones and hosted box untouched; nothing pushed or deployed.~~

- ~~**Currawong** — 2026-11-21 12:25 → 12:31 — built and registered blinded listening pool `quality-0101` (pool 9: `0101 Dual-AR q4_crisp CFG 1.6` vs `CrowGPT2`, 54 trials in 3 doses of 18, 30-min cooldown, 40 compares + 8 catches + 6 repeats, fresh unseen test groups and seed block `101500+`). GPU released 12:30.~~

- ~~**Currawong** — 2026-11-20 07:28 → 2026-11-20 09:26 — experiment 0101 complete (recording-quality conditioning `q0..q4` + 15% CFG dropout on Dual-AR 17M @ 240k, batch-2 CFG in `dualar.py` + unit test): `q4_crisp + CFG 1.3–1.6` lifted median SNR 16.9 → 24.3 dB, halved quiet-frame flatness (0.173 → 0.088), raised worst-quartile pitch 0.417 → 0.498, cut dust 21.8% → 12.0–16.2%, keep rate 75.8% → 87–88.5%, 0% 32-frame memorisation. Diagnostic page opened at `crowgpt/results/quality-0101/compare.html`. GPU released 09:25. Field server, phones, and `capacity-0096` untouched.~~

- ~~**Currawong** — 2026-11-19 23:27 → 2026-11-20 05:35 — overnight GPU Option A + follow-up: added Frame-RoPE+SwiGLU (`model.py`), Dual-AR (`dualar.py`), per-stage val & stage-weighted loss (`sliced.py`), and `min_p`/`repeat_penalty`/split-T (`sample.py`) with 6 new unit tests (358/358 passing). Completed experiments 0099 (architecture & objective shootout: Dual-AR 17.34M beat flat baselines at 60k in 20m [4.6388] and 120k in 40m [4.5674], 4.5× faster on CPU) and 0100 (Dual-AR scaling: 17.34M @ 240k reached 4.5308 full American Crow val CE [−0.262 below CrowGPT2], beating 39.6M @ 120k [4.5337], zero memorisation on 0015 check, diagnostic page at `crowgpt/results/scaling-0100/compare.html`). GPU released 05:34. Field server, phones, and `capacity-0096` pool untouched; changes left uncommitted on disk (sandbox `.git` read-only).~~

- ~~**Rook** — 2026-11-14 13:10–14:25 — security audit of the field server and its fixes, all committed (9820968..6ce0051) and deployed to field.crowgpt.org: hosted units sandboxed and written from the registry (server unit included; workers start from `instance/worker.env`, no sudo, no network), waitress in place of the dev server, per-invite enrollment codes + 2 GB allowance for invited contributors (revision 0040), scan uploads verified before the body and decoded only as accepted formats, photo size limits, security headers in Caddy. On the box: shared enrollment token rotated (new value in `instance/secrets.env`), Cloudflare API token removed, env backups moved to `~/env-backups`, Caddyfile backup at `/etc/caddy/Caddyfile.before-headers-20261114`, DB backup `instance/backups/pre-0040-security-20261114.db`. Open items in FUTURE.txt. Phones and GPU untouched; nothing pushed.~~

- ~~**Treepie** — 2026-11-12 — measured call yield of newly collected short video clips (experiment kept with the corpus tooling); GPU released, server untouched.~~

- ~~**Chough** — since 2026-11-01 — promo: `#` anchor links on every heading, committed and built, NOT deployed. Updated 2026-11-01.~~

- ~~**Jackdaw** — since 2026-10-21 17:55 — open-source move done (public github.com/benfaerber/crowgpt, one-commit squash; old history on local branch `private-history`, purge needs Ben's OK, see TODO.txt). Then the project renamed CrowGPT across titles/app/dashboard/docs (dbe27b7) and the promo's call-type cards shipped (18fd253), both deployed to cawtalker.org. Five local commits unpushed. Server and GPU untouched. Updated 2026-10-21 22:05.~~ (struck as stale 2026-10-30)

- ~~**Jynx** — since 2026-09-11 — promo reorder + em-dash scrub shipped (d5bb83c, be46cce, a67298e; cawtalker.org not deployed, on Ben's word). Auto-grading investigation delivered: findings in FUTURE.txt (top entry). Read-only on the DB; not touching the server or the GPU. Updated 2026-09-11 18:05.~~ (struck as stale 2026-10-30)

- ~~**Cissa** — since 2026-09-10 — minimal, distributable corpus crawler
  shipped in `corvidcrawler/` (Xeno-canto + Macaulay only, per Ben): own
  venv, 100 tests green, Xeno-canto verified live into a scratch DATA_DIR.
  Macaulay's search endpoint answers scripts with a bot check, so the CSV
  export is the route and the crawler says so. CLAUDE.md source rule updated.
  Not touching the server or the GPU. Updated 2026-09-10 17:30.~~ (struck as stale 2026-10-30)

- ~~**Chough (CrowGPT)** — since 2026-09-09 — experiment 0086 finished 16:38; all three rates trained, selected candidate and 48-trial capacity-0086 pool ready. GPU reservation released. Field dashboard/API remains healthy as `cawtalker-fieldserver` on :5100. Listening pending. Updated 2026-09-10 17:09.~~ (struck as stale 2026-10-30)

- ~~**Currawong** — since 2026-08-22 — CawScout: generation graduated into
  `fieldserver/src/fieldserver/scout/` (`make -C fieldserver scout`), then
  Davis + Utah county shipped the same day — 5 CHM tiles in
  data/experiments/0083-chm/, 0083 build_region.py with 1,650 m elevation
  mask, 45 targets published to instance/scout.json. Now running the field
  server: `make field` up at 16:58 on commit 31a6b29, health green, all
  three workers ready (they hold the GPU for inference as usual).
  Updated 2026-08-22 16:58.~~ (struck as stale 2026-10-30)

- ~~**Piapiac** — since 2026-08-20 — tree audit shipped (a963a87): hub
  safetensors now gitignored before anyone `git add -A`'d 170 MB of weights
  into history; tsbuildinfo untracked. Rest of the unstaged pile judged
  commit-worthy, left for its owners. Not touching the server or the GPU.
  Updated 2026-08-20.~~ (struck as stale 2026-10-30)

- ~~**Bokmakierie** — since 2026-08-20 — CawTalker t-shirt design canvas shipped
  (working files in `data/tshirt/`, gitignored): two front prints, a back
  print, and a placement mockup in the business-card style, saved as an
  artifact for Ben. Design only; not touching the server or the GPU.
  Updated 2026-08-20.~~ (struck as stale 2026-10-30)

- ~~**Nutcracker** (un-struck, same session) — since 2026-08-19 (Wed) — promo
  favicon made circular (icon-16/32/512 regenerated from the mark, masked to
  a disc), bundle rebuilt, cawtalker.org deployed and verified serving the
  new bytes. Promo only; server and GPU untouched. Updated after deploy.~~ (struck as stale 2026-10-30)

- ~~**Alpine** — since 2026-08-18 (Tue) 20:10 — doc tidy-up pass shipped across
  CLAUDE.md, the READMEs, FUTURE.txt, the outreach scripts and one tool
  docstring, per Ben's request this session. Docs only; not touching the
  server or the GPU. Updated 20:30.~~ (struck as stale 2026-10-30)

- ~~**Chihuahuan** — since 2026-08-18 (Mon) — logo rollout shipped (…a2be7e8,
  7b9470f): icons + favicons derive from `images/cawtalker-logo.svg`, brand
  spelled CawTalker everywhere user-facing; FlyingCrow replaced by the static
  mark, and tapping it now flies the promo flock across the screen (new
  `Flock.tsx`, same sprite). cawtalker.org redeployed, latest build on the
  Pixel 8, waiting on Ben's tap. Pixel 10 install on his word. Server
  untouched. Updated 2026-08-18 20:35.~~ (struck as stale 2026-10-30)

- ~~**Treepie** — since 2026-08-18 (Mon) — client-side CrowGPT prototype shipped
  as experiment 0080: crowgpt2 in the browser via ONNX/WASM, demo serving at
  http://127.0.0.1:8092/ (serve.py, left running for Ben). Nothing deployed
  to promo. Not touching the field server or the GPU. Updated 2026-08-18
  19:30.~~ (struck as stale 2026-10-30)

- ~~**Jay** — since 2026-08-17 (Mon) — assessing how the Song Meter Micro 2 +
  trail cam research station fits the pipeline, against `phases/roof-station.md`
  and `data-collection.md`. Reading only; not touching the server or the GPU.
  Updated 2026-08-17.~~ (struck as stale 2026-10-30)

- ~~**Rook** — since 2026-08-16 (Sun) — Bluetooth remote shutter shipped
  (0c0cc68): volume keys claimed as a record trigger behind a new setting,
  tests green; build installed on the Pixel 8, waiting on Ben's remote test.
  Mobile only; not touching the server or the GPU. Updated 13:55.~~ (struck as stale 2026-10-30)

- ~~**Magpie** — since 2026-08-15 (Sat) ~22:00 — promo site traffic analysis
  delivered (mostly AI crawlers + scanners; ~8–15 real visitors from the
  Instagram plug); wrote it up in FUTURE.txt ("The hard promo push"). Not
  touching the server or the GPU. Updated 22:20.~~ (struck as stale 2026-10-30)

- ~~**Raven** — since 2026-08-13 (Thu) — CawScout field sprint with Ben:
  compass beam + live GPS, Directions links, sighting dates/photos with
  server archive, family descriptions (server adopts re-pushed edits),
  by-ear labels on the capture timeline, brand font on wordmark titles,
  and the header's sun/temp scouting-window advice (Poe-calibrated).
  0084 field log: 2 hits (#1, #4 "The Scholars" 3 crows) / 2 nulls, both
  nulls at the predator-heavy pins. Pixel 8 current; Pixel 10 on Ben's
  word. GPU free; server restarted, healthy. Updated 2026-08-21 ~13:00.~~ (struck as stale 2026-10-30)

- ~~**Corbie** — since 2026-08-15 (Sat) ~19:00 — HF release repo shipped:
  faerber/crowgpt (private) holds both CrowGPTs as safetensors + JSON via
  the new `crowgpt.hub` (68477e3), verified bit-identical through a fresh
  download, CPU only; card's license section now attributes Xeno-canto per
  Ben's scope extension (58302a1). Earlier: Crow Chat model picker (180f293),
  Forget button (ad7c754). Not holding the server or the GPU. Updated 21:50.~~ (struck as stale 2026-10-30)

- ~~**Chough** — since 2026-08-15 (Sat) 19:45 — idle mode shipped, twice tested
  by Ben: fixed the self-masking floor his playback test found (hot buffers
  now excluded from the noise-floor window) and gave the armed bar a live
  phase + meter readout. Latest build on the Pixel 8; wire 23 live. Waiting
  on his re-test. Updated 21:45.~~ (struck as stale 2026-10-30)

- ~~**Jackdaw** — since 2026-08-15 (Sat) 20:15 — built this roster system and
  wired it into `CLAUDE.md`. Updated 20:15.~~ (struck as stale 2026-10-30)

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
- ~~**Jackdaw** — 2026-11-12 (Thu) — crowgpt.org traffic read (token IP filter fixed by Ben); invite email now names hello@crowgpt.org for questions, deployed.~~
