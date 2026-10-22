.PHONY: help install dev build build-public deploy deploy-dry login typecheck clean ensure-bundle stats stats-check credits traffic

# node/npm are nvm lazy-load *zsh functions*, so they don't exist in make's
# /bin/sh. Resolve nvm's default version and put it first on PATH, the same way
# dashboard/Makefile does.
NVM_DIR ?= $(HOME)/.nvm
NODE_ALIAS := $(shell cat $(NVM_DIR)/alias/default 2>/dev/null)
NODE_BIN := $(shell ls -d $(NVM_DIR)/versions/node/v$(NODE_ALIAS)*/bin 2>/dev/null | sort -V | tail -1)
export PATH := $(if $(NODE_BIN),$(NODE_BIN):)$(PATH)

# Where `npm run build` writes, so `make field` can tell whether it needs to.
BUNDLE = ../fieldserver/src/fieldserver/static/promo/index.html

help:
	@echo "CrowGPT promo site"
	@echo "  make dev        Vite dev server on :5174"
	@echo "  make build        Build into the field server's static/, served at :5100/promo"
	@echo "  make build-public Build for crowgpt.org (rooted at /) into promo/dist"
	@echo "  make deploy       Typecheck, build, and publish to crowgpt.org"
	@echo "  make deploy-dry   Everything deploy does, except the upload"
	@echo "  make login        One-time Cloudflare browser login for wrangler"
	@echo "  make typecheck    tsc --noEmit"
	@echo "  make stats        Refresh stats.json from the field server and corpus"
	@echo "  make stats-check  Report stale figures without writing (exit 1 if any)"
	@echo "  make credits      Rebuild public/credits.json from the corpus"
	@echo "  make traffic      Last week of cawtalker.org traffic from Cloudflare, humans split from bots"

node_modules:
	npm install

install: node_modules

dev: node_modules
	npm run dev

build: node_modules
	npm run build

# The upload for the public host. Separate output directory on purpose: the two
# builds differ only in base path, and overwriting the field server's copy with
# a root-rooted one would break /promo without any error to notice it by.
build-public: node_modules
	PROMO_PUBLIC=1 npm run build
	@echo
	@echo "Built promo/dist for crowgpt.org. Upload that folder."

# Build only if the bundle is missing — `make field` calls this on every start
# and a full rebuild each time would add seconds to something run constantly.
$(BUNDLE): node_modules
	npm run build

ensure-bundle: $(BUNDLE)

typecheck: node_modules
	npm run typecheck

# ---- the numbers ----------------------------------------------------------
#
# Every figure the page prints lives in stats.json, and the page reads it at
# build time — so refreshing the numbers is these two commands and a rebuild,
# not an edit in five places. Credits first: the recording tally on the front
# page is counted out of credits.json.
stats: credits
	python3 tools/build_stats.py

stats-check:
	python3 tools/build_stats.py --check

credits:
	python3 tools/build_credits.py

# Who visited. Needs CLOUDFLARE_API_TOKEN in fieldserver/instance/secrets.env;
# eight days of retention on the free plan, so pull within a week of a push.
DAYS ?= 7
traffic:
	python3 tools/traffic.py --days $(DAYS)

clean:
	trash-put ../fieldserver/src/fieldserver/static/promo 2>/dev/null || true

# ---- publishing -----------------------------------------------------------
#
# One-time, opens a browser. Wrangler keeps the token afterwards, so the deploy
# targets below never prompt again.
login:
	npx wrangler login

# Typecheck and rebuild before every publish, always. The build is fast and the
# alternative is shipping whatever happened to be in dist/ — which, after a
# session of editing, is exactly the wrong thing to find out from the live site.
deploy: node_modules typecheck build-public
	npx wrangler deploy
	@echo
	@echo "Live at https://crowgpt.org — hard-reload to see it past the CDN cache."

# Same path, stopping short of the upload. Use it to check the config and see
# the file list wrangler would send.
deploy-dry: node_modules typecheck build-public
	npx wrangler deploy --dry-run
