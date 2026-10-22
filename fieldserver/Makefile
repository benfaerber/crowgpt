.PHONY: help serve worker transcriber generator dev stop test secrets scout

BIRDNET = ../pipelines/representation/.venv-birdnet/bin/python
# A torch venv, and it must not be the BirdNET one: birdnetlib takes CUDA away
# from torch permanently in whatever process loads it. crowgpt's already carries
# torch+cu128 and transformers, so this costs no new dependency — and being one
# variable is what makes moving to a dedicated venv a one-line change if
# crowgpt's ever drifts out from under it.
WHISPER ?= ../crowgpt/.venv/bin/python
# Crow Chat's generation worker: crowgpt's venv for the same torch/birdnetlib
# separation the transcriber documents.
GENERATOR ?= ../crowgpt/.venv/bin/python

help:
	@echo "CrowGPT field server"
	@echo "  make dev      Serve the API and run the inference worker together (Ctrl-C stops both)"
	@echo "  make serve    Serve the field API + operator dashboard on http://127.0.0.1:5100"
	@echo "  make worker   Run the BirdNET inference worker against the shared DB"
	@echo "  make transcriber  Run the speech-to-text worker for spoken field notes"
	@echo "  make stop     Stop a running server and worker"
	@echo "  make test     Run the API checks (temp DBs, no server needed)"
	@echo "  make scout    Rebuild + publish the CawScout layer (network fetches)"
	@echo "                (make dev also reruns it weekly via worker/scout_scheduler.py)"
	@echo "  make secrets  Show this fleet's enrollment and operator tokens"

secrets:
	@bash tools/secrets.sh --show

serve:
	@echo "Field server -> http://127.0.0.1:5100"
	uv run fieldserver

# `set -a` exports everything the file defines, so FIELD_LAT/FIELD_LON reach the
# analyzer without being named twice.
ENVFILE = .env
LOADENV = set -a; [ -f $(ENVFILE) ] && . ./$(ENVFILE); set +a

worker:
	@$(LOADENV); $(BIRDNET) worker/analyze_worker.py

# `-n auto` splits across cores. Each worker builds its own migrated template
# database, which sounds wasteful and is not: 359 tests went from 25 seconds to
# 5, because the cost is nineteen tables per worker against a suite that is
# almost entirely independent per test. `make test SERIAL=1` when a failure
# needs reading in order.
test:
	uv run pytest $(if $(SERIAL),,-n auto)

# Rebuilds the scouting layer from live public data and replaces
# instance/scout.json. A couple of minutes of iNaturalist and Overpass
# fetches; the server needs no restart, /api/scout reads the file per
# request. REGIONS="slug ..." limits it, but the file is replaced whole —
# with several regions defined, build them together.
scout:
	uv run python tools/build_scout.py $(foreach r,$(REGIONS),--region $(r))

# `kill 0` signals the whole process group, so Ctrl-C takes the worker down with
# the server instead of orphaning it holding the DB.
#
# The preflight matters more than it looks: Flask exits with "Address already in
# use" when a previous run is still up, but the worker beside it starts anyway.
# Repeat that a few times and you have several BirdNET workers running against
# one database while the server you just started is dead — which reads as
# "make field didn't work" with nothing saying why.
# Binds all interfaces so phones reach it over Wi-Fi. adb reverse only works
# over USB, which is the wrong constraint for a phone you carry into a field.
# Override with FIELD_HOST=127.0.0.1 to go back to loopback only.
FIELD_HOST ?= 0.0.0.0

dev:
	@if ss -ltn 2>/dev/null | grep -qE ':5100 '; then \
	  echo "Something is already serving :5100."; \
	  echo "Stop it first:  make -C fieldserver stop"; \
	  exit 1; \
	fi
	@echo "Field server -> http://$$(hostname -I | awk '{print $$1}'):5100   (+ inference worker)"
	@echo "                 set that as the server URL in the app's Settings"
	@echo "                 (loopback also works: http://127.0.0.1:5100)"
	@bash tools/secrets.sh --show
	@# Per device, not once: bare `adb reverse` fails outright with two phones
	@# attached, and it used to take the whole server down with it. A phone on
	@# wireless adb has no USB tunnel to set, so a failure here is skipped
	@# rather than fatal — Wi-Fi is how it reaches the server anyway.
	@if command -v adb >/dev/null; then \
	  for serial in $$(adb devices | awk '$$2 == "device" { print $$1 }'); do \
	    if adb -s $$serial reverse tcp:5100 tcp:5100 >/dev/null 2>&1; then \
	      echo "  $$serial can reach it on 127.0.0.1:5100 (adb reverse set)"; \
	    fi; \
	  done; \
	fi
	@trap 'kill 0' EXIT INT TERM; \
	  eval "$$(bash tools/secrets.sh)"; \
	  FIELD_HOST=$(FIELD_HOST) uv run fieldserver & \
	  $(LOADENV); $(BIRDNET) worker/analyze_worker.py & \
	  $(LOADENV); $(WHISPER) worker/transcribe_worker.py & \
	  $(LOADENV); $(GENERATOR) worker/generate_worker.py & \
	  $(LOADENV); uv run python worker/scout_scheduler.py & \
	  wait

transcriber:
	@$(LOADENV); $(WHISPER) worker/transcribe_worker.py

generator:
	@$(LOADENV); $(GENERATOR) worker/generate_worker.py

stop:
	bash tools/stop.sh

# --- schema ---------------------------------------------------------------
# Alembic owns the shape of the database. `make field` runs `upgrade head` on
# startup, so these are for inspecting and authoring rather than for deploying.
.PHONY: schema-current schema-history schema-check schema-revision

schema-current:
	uv run alembic current

schema-history:
	uv run alembic history --verbose

# What the live database has that a freshly migrated one would not, and vice
# versa. Empty output is the good answer.
schema-check:
	@uv run python -c "from fieldserver.core.schema import drift; \
	  d = drift(); \
	  print('\n'.join(d) if d else 'schema matches the migrations')"

# make schema-revision M="what it does"
schema-revision:
	uv run alembic revision -m "$(M)"
