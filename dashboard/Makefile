.PHONY: help install dev build typecheck clean

# node/npm are nvm lazy-load *zsh functions*, so they don't exist in make's
# /bin/sh. Resolve nvm's default version and put it first on PATH, the same way
# mobile/Makefile does.
NVM_DIR ?= $(HOME)/.nvm
NODE_ALIAS := $(shell cat $(NVM_DIR)/alias/default 2>/dev/null)
NODE_BIN := $(shell ls -d $(NVM_DIR)/versions/node/v$(NODE_ALIAS)*/bin 2>/dev/null | sort -V | tail -1)
export PATH := $(if $(NODE_BIN),$(NODE_BIN):)$(PATH)

# Where `npm run build` writes, so `make field` can tell whether it needs to.
BUNDLE = ../fieldserver/src/fieldserver/static/app/index.html

help:
	@echo "Cawtalker operator dashboard"
	@echo "  make dev        Vite dev server on :5173, proxying /api to the field server"
	@echo "  make build      Build into the field server's static/, served at :5100/"
	@echo "  make typecheck  tsc --noEmit"

node_modules:
	npm install

install: node_modules

dev: node_modules
	npm run dev

build: node_modules
	npm run build

# Build only if the bundle is missing — `make field` calls this on every start
# and a full rebuild each time would add seconds to something run constantly.
$(BUNDLE): node_modules
	npm run build

ensure-bundle: $(BUNDLE)

typecheck: node_modules
	npm run typecheck

clean:
	trash-put ../fieldserver/src/fieldserver/static/app 2>/dev/null || true
