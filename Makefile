.PHONY: help crowgpt field field-stop fieldserver worker transcriber generator analyzer dashboard promo install-app devices android metro reverse test seed \
        corpus corpus-build train train-crow export-labels backup watch field-deploy field-status field-logs apk-publish

ADB ?= adb

# Bare `make` prints the help, and says so here rather than relying on `help`
# being the first target written down.
#
# It is not, once Makefile.local exists: make takes its default goal from the
# first target it reads, the include below is read before `help`, and the first
# target in that file is an install. So `make` on its own built an APK and
# flashed it at a handset — no argument, no confirmation, and the choice of
# phone decided by whichever install target the file happened to open with.
#
# Pinning it here rather than moving the include keeps that true whatever a
# personal, gitignored file grows later.
.DEFAULT_GOAL := help

# Personal targets, gitignored. Handset serials belong to a desk, not a
# repository. The leading `-` means a machine without one builds as before.
-include Makefile.local

help:
	@echo "CrowGPT"
	@echo "  make field        Run the field server and its workers (analysis, dictation, generation, scout) together"
	@echo "  make field-stop   Stop them"
	@echo "  make field-deploy Ship the committed tree + bundles to field.crowgpt.org and restart its services"
	@echo "  make field-status Are the hosted server, its workers and Caddy up"
	@echo "  make field-logs   The hosted services' last hundred log lines"
	@echo "  make apk-publish  Build the app and publish the APK to the hosted invite pages"
	@echo "  make fieldserver  Run the field API + operator dashboard -> http://127.0.0.1:5100"
	@echo "  make dashboard    Dashboard with hot reload -> http://127.0.0.1:5173 (needs the server up)"
	@echo "  make promo        Promo site with hot reload -> http://127.0.0.1:5174 (served at :5100/promo)"
	@echo "  make worker       Run the BirdNET inference worker for the field server"
	@echo "  make transcriber  Run the speech-to-text worker for spoken field notes"
	@echo "  make generator    Run the Crow Chat generation worker"
	@echo "  make analyzer     Load the analyzer and list the call-type heads it found"
	@echo "  make corpus       Say what the vendored label corpus holds and how much audio is on disk"
	@echo "  make backup       Copy the recordings and database to BACKUP_DIR"
	@echo "  make crowgpt      Generating crow calls — lists its own stages"
	@echo "  make train        Train a species' call-type head    SLUG=carrion-crow"
	@echo "                    train takes ARGS=\"--flag …\" for the rest"
	@echo "  make train-crow   Retrain American Crow on the vendored label corpus + the archive set"
	@echo "  make corpus-build Re-pool the vendored label features (slow; after a re-import)"
	@echo "  make export-labels Fold the field server's human labels into a manifest SLUG="
	@echo "  make install-app  Install/update the standalone field app (keeps captures)"
	@$(if $(wildcard Makefile.local),echo "  (Makefile.local adds: $$(grep -oE '^(install|wireless)-[a-z0-9-]*' Makefile.local | tr '\n' ' '))")
	@echo "                    DEVICE=<serial> to pick a phone when several are attached"
	@echo "  make devices      List attached phones"
	@echo "  make android      Dev client for development — needs Metro running here"
	@echo "  make metro        Start Metro only (the app is already installed)"
	@echo "  make reverse      Point the attached device's :5100 at this machine"
	@echo "  make test         Run the checks across field server, mobile, crowgpt, dashboard and promo (no device needed)"
	@echo "  make seed         Seed the phone with captures made from real crow audio"
	@echo "  make watch        Follow the active runs reporting into data/progress"

# ---- Hosted field server ----------------------------------------------------
#
# field.crowgpt.org is an OVH VPS, reached as `crowfield` in ~/.ssh/config. It
# runs this same tree out of ~/crowgpt under systemd — crowgpt-field,
# crowgpt-analyze, crowgpt-generate, crowgpt-scout — with Caddy terminating
# TLS in front and the server bound to loopback behind it. A deploy ships the
# *committed* tree (git archive: nothing untracked or ignored leaves this
# machine), the two built bundles the server serves, re-syncs the fieldserver
# venv, and restarts the services. The release checkpoints and the instance
# directory were copied once by hand and are not part of a deploy; the crowgpt
# venv on the box carries CPU torch (`uv sync --index
# pytorch-cu128=https://download.pytorch.org/whl/cpu`) and is re-synced by
# hand when crowgpt/pyproject.toml changes.
DEPLOY_HOST ?= crowfield
DEPLOY_DIR ?= crowgpt

field-deploy:
	$(MAKE) -C dashboard ensure-bundle
	$(MAKE) -C promo ensure-bundle
	git archive --format=tar HEAD | ssh $(DEPLOY_HOST) 'tar -x -C ~/$(DEPLOY_DIR)'
	rsync -a fieldserver/src/fieldserver/static/app fieldserver/src/fieldserver/static/promo \
	  $(DEPLOY_HOST):~/$(DEPLOY_DIR)/fieldserver/src/fieldserver/static/
	ssh $(DEPLOY_HOST) 'export PATH=$$HOME/.local/bin:$$PATH; cd ~/$(DEPLOY_DIR)/fieldserver \
	  && UV_PYTHON=3.10 uv sync --frozen --no-dev -q \
	  && sudo systemctl restart crowgpt-field crowgpt-analyze crowgpt-generate crowgpt-scout'
	@sleep 3; ssh $(DEPLOY_HOST) 'curl -fsS http://127.0.0.1:5100/api/health'; echo

# The preview page serves the newest .apk in the box's instance/apk/, so
# publishing a build is a copy. The name carries the date and the commit so a
# tester's download folder says which build it is; the server does not care.
apk-publish:
	$(MAKE) -C mobile apk
	ssh $(DEPLOY_HOST) 'mkdir -p ~/$(DEPLOY_DIR)/fieldserver/instance/apk'
	scp -q mobile/android/app/build/outputs/apk/release/app-release.apk \
	  $(DEPLOY_HOST):~/$(DEPLOY_DIR)/fieldserver/instance/apk/crowgpt-field-$$(date +%Y%m%d)-$$(git rev-parse --short HEAD).apk
	@echo "published: every approved invite at https://field.crowgpt.org/preview/<token> now serves it"

field-status:
	@ssh $(DEPLOY_HOST) 'systemctl --no-pager status crowgpt-field crowgpt-analyze crowgpt-generate crowgpt-scout caddy 2>/dev/null | grep -E "^.? ?[a-z-]+\.service|Active:"'

field-logs:
	@ssh $(DEPLOY_HOST) 'sudo journalctl -u crowgpt-field -u crowgpt-analyze -u crowgpt-generate -u crowgpt-scout -n 100 --no-pager -o short'

# The dashboard and the promo site are built bundles the server serves, so they
# have to exist before it starts. Both only build when missing — this runs
# constantly.
field:
	$(MAKE) -C dashboard ensure-bundle
	$(MAKE) -C promo ensure-bundle
	$(MAKE) -C fieldserver dev

field-stop:
	$(MAKE) -C fieldserver stop

fieldserver:
	$(MAKE) -C fieldserver serve

worker:
	$(MAKE) -C fieldserver worker

transcriber:
	$(MAKE) -C fieldserver transcriber

generator:
	$(MAKE) -C fieldserver generator

# Load BirdNET and the call-type heads without a server or a database — the
# fastest way to tell whether a newly trained head is being picked up.
analyzer:
	@pipelines/representation/.venv-birdnet/bin/python -c "\
	import sys; sys.path.insert(0, '.'); from analyzer import HEADS; \
	print('heads:', ', '.join(sorted(h.display for h in HEADS.heads.values())))"

# ---- Corpus and training ---------------------------------------------------
#
# The pipelines are loose scripts split across two venvs, and naming the whole
# loop here is what saves anyone having to remember which:
#
#   make train SLUG=...       train a species' head from its manifest (BirdNET venv)
#   make corpus-build         re-pool the vendored label features after a re-import
#   make train-crow           retrain American Crow on the vendored labels + the archive set
#   make export-labels SLUG=  fold the field server's human labels into a manifest
#
# Paths outside the repo (DATA_DIR) come from the gitignored .env — see
# .env.example. Nothing here needs it set.
#
# The interpreter below is the whole reason this used to go through bin/cawtrain:
# a shell wrapper holding a venv path and exec'ing one script, which is what a
# make variable does. The scripts keep flags these targets do not name (--jobs),
# so ARGS= passes anything through to them — the one thing dropping bin/ cost.
# There were two such variables until the corpus tooling left; see below.

BIRDNET := pipelines/representation/.venv-birdnet/bin/python

# The same question as `make analyzer`, one stage earlier: is the training data
# where the pipelines think it is? Plain python — corpus.py is stdlib-only, so
# this answers even when the BirdNET venv is missing.
corpus:
	@python3 pipelines/ingest/corpus.py

# Half an hour of embedding. Only needed after a re-import of the labels, or when
# the flag -> CORE mapping changes; the .npz it writes is what training reads.
corpus-build:
	$(BIRDNET) pipelines/ingest/build_dataset.py $(if $(DATASET),--dataset $(DATASET))

train-crow:
	$(BIRDNET) pipelines/ingest/train_american_crow.py

# crowgpt has its own venv (torch + birdnetlib in one) and its own Makefile;
# `make -C crowgpt help` lists the stages. Not wired further in on purpose —
# `gate` is a stop point that can legitimately say do not train anything.
crowgpt:
	$(MAKE) -C crowgpt help

# Fetching lives in corvidcrawler/ (`make -C corvidcrawler crawl SP=...`), which
# writes the per-species tree `make train` reads. It covers Xeno-canto and the
# Macaulay Library; anything else in data/ came from private tooling elsewhere.

train:
	@test -n "$(SLUG)" || { echo "Which head? make train SLUG=carrion-crow"; exit 1; }
	$(BIRDNET) pipelines/ingest/train_species.py --slug $(SLUG) $(ARGS)

# The recordings and the database, to BACKUP_DIR (see .env.example). Safe with
# the server running: the database is snapshotted through SQLite's own locking
# rather than copied as a file. CORPUS=1 adds data/, which is large and can be
# re-downloaded.
#
# The date is stamped here rather than in the script so a re-run within the same
# minute overwrites its own snapshot instead of leaving two.
backup:
	@BACKUP_STAMP=$$(date +%Y%m%d-%H%M) python3 tools/backup.py

# Reads the field DB directly, so the server can be up or down.
export-labels:
	@test -n "$(SLUG)" || { echo "Which species? make export-labels SLUG=american-crow"; exit 1; }
	@python3 pipelines/ingest/export_manifest.py --slug $(SLUG)

# Hot reload for dashboard work. Vite proxies /api to :5100, so `make field`
# still has to be running in another terminal.
dashboard:
	$(MAKE) -C dashboard dev

# Hot reload for promo work, on its own port so it can run beside the dashboard's.
# It calls no API, so it needs nothing else running.
promo:
	$(MAKE) -C promo dev

# One target, because there was never a second behaviour. `update-app` used to
# sit beside this passing `-r`, which reads like `adb install -r` but is a *make*
# flag — so the two were identical and the naming implied a choice that did not
# exist. The install always replaces in place and keeps the local store.
install-app:
	$(MAKE) -C mobile install DEVICE="$(DEVICE)"

devices:
	$(MAKE) -C mobile devices

android:
	$(MAKE) -C mobile android

metro:
	$(MAKE) -C mobile start

reverse:
	$(ADB) reverse tcp:5100 tcp:5100

test:
	$(MAKE) -C fieldserver test
	$(MAKE) -C mobile test
	$(MAKE) -C crowgpt test
	$(MAKE) -C dashboard typecheck
	$(MAKE) -C promo typecheck

seed:
	$(MAKE) -C mobile seed SEED_ARGS="$(SEED_ARGS)"

# Follows every run reporting into data/progress, active first, rendered by
# the same module that writes the records. watch(1) only ends on Ctrl-C, and
# the failing exit stops make from treating anything after it as a goal.
watch:
	@watch -n 2 python3 crowgpt/src/crowgpt/progress.py; exit 130
