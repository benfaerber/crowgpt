.PHONY: help install wireless devices android start typecheck test test-native seed seed-clear icon

# The system java is 11, which AGP 8 rejects; Android Studio's bundled JDK 21 is
# what actually builds. `?=` so an env that already sets these wins.
JAVA_HOME ?= $(HOME)/.local/share/android-studio/jbr
ANDROID_HOME ?= $(HOME)/Android/Sdk

# node/npm/npx are nvm lazy-load *zsh functions*, so they don't exist in make's
# /bin/sh — and $(HOME)/.local/bin/node is a shim that execs bun, which is what
# a bare `node` would otherwise resolve to here. Resolve nvm's default version
# and put it first on PATH so the build runs on the node it's meant to.
NVM_DIR ?= $(HOME)/.nvm
NODE_ALIAS := $(shell cat $(NVM_DIR)/alias/default 2>/dev/null)
NODE_BIN := $(shell ls -d $(NVM_DIR)/versions/node/v$(NODE_ALIAS)*/bin 2>/dev/null | sort -V | tail -1)

export JAVA_HOME
export ANDROID_HOME
export PATH := $(if $(NODE_BIN),$(NODE_BIN):)$(JAVA_HOME)/bin:$(ANDROID_HOME)/platform-tools:$(PATH)

help:
	@echo "CrowGPT field app"
	@echo "  make install    Build + install the STANDALONE app for field use (no laptop needed)"
	@echo "  make devices    List attached phones"
	@echo "  make wireless   Put a phone on wireless adb (one cable, then none)"
	@echo "  make android    Dev client — needs Metro running on this machine"
	@echo "  make start      Start Metro only (the app is already installed)"
	@echo "  make typecheck  tsc --noEmit"
	@echo "  make test       Run the store/sync/HTTP checks on this machine (no device)"
	@echo "  make seed       Put captures made from real crow audio on the attached phone"
	@echo "  make seed-clear Remove seeded captures from the phone"
	@echo
	@echo "  node: $(if $(NODE_BIN),$(NODE_BIN),NOT FOUND under $(NVM_DIR))"

# The app icon is the CrowGPT mark — images/crowgpt-logo.svg at the repo
# root, the crow head with the sound wave. Every icon asset is derived from it,
# and both build targets depend on them, so updating the mark updates the icon
# on the next install with no extra step. The monochrome icon is derived too,
# now that the source is a glyph rather than a photo; Android reads only its
# alpha channel. The foreground and monochrome sizes keep the mark inside the
# adaptive icon's central safe zone (a circle of 66/108 of the canvas), which
# is why they are smaller than the canvas looks like it allows.
ICON_SRC = ../images/crowgpt-logo.svg
ICON_BG = \#F4FAFA
ICON_ASSETS = assets/icon.png assets/android-icon-foreground.png \
              assets/android-icon-background.png assets/android-icon-monochrome.png \
              assets/brand-mark.png

assets/icon.png: $(ICON_SRC)
	convert -size 1024x1024 xc:"$(ICON_BG)" \
	  \( -background none -density 288 $(ICON_SRC) -resize 660x660 \) \
	  -gravity center -composite -alpha off $@

assets/android-icon-foreground.png: $(ICON_SRC)
	convert -size 1024x1024 xc:none \
	  \( -background none -density 288 $(ICON_SRC) -resize 500x500 \) \
	  -gravity center -composite $@

assets/android-icon-background.png: $(ICON_SRC)
	convert -size 1024x1024 xc:"$(ICON_BG)" $@

assets/android-icon-monochrome.png: $(ICON_SRC)
	convert -size 432x432 xc:none \
	  \( -background none -density 288 $(ICON_SRC) -resize 200x200 \
	     -channel RGB -evaluate set 100% +channel \) \
	  -gravity center -composite $@

# The in-app header mark: transparent, no ground, recolored at runtime via
# tintColor so it follows the theme.
assets/brand-mark.png: $(ICON_SRC)
	convert -background none -density 288 $(ICON_SRC) -resize 128x128 $@

icon: $(ICON_ASSETS)

# The one to use before going out. Release build: JS bundled in, runs alone.
install: check-node icon
	bash tools/install_field_app.sh

devices:
	@$(ANDROID_HOME)/platform-tools/adb devices -l

# Put a phone on wireless adb. Needs one cable to set up, none afterwards.
# A phone that stays listed is a phone `make install` can never auto-pick.
wireless:
	bash tools/pair_wireless.sh

android: check-node icon
	npm run android

start: check-node
	npm start

# Errors located inside node_modules are reported but not fatal. Several Expo
# packages ship build/*.d.ts that re-export ../src/*.ts, so `tsc` typechecks
# their raw TypeScript — where they import untyped JS and trip noImplicitAny.
# skipLibCheck does not cover it (those are .ts, not .d.ts) and we cannot fix
# a dependency's published declarations from here. Anything in OUR files still
# fails the build, which is the whole point of the check.
typecheck: check-node
	@mine=$$(npx tsc --noEmit 2>&1 | grep 'error TS' | grep -v '^node_modules/'); \
	 if [ -n "$$mine" ]; then echo "$$mine"; exit 1; fi; \
	 theirs=$$(npx tsc --noEmit 2>&1 | grep -c '^node_modules/.*error TS' || true); \
	 echo "typecheck clean ($$theirs dependency error(s) ignored — see tsconfig.json)"

# vitest runs everything, sync suite included; the tsc pass afterwards is the
# tests' typecheck — vitest erases types, so without it a fixture drifting from
# an interface passes the whole run and fails no one.
test: check-node typecheck
	npx vitest run
	npx tsc -p tsconfig.tests.json --noEmit

# The Kotlin that has logic rather than Android calls — the pre-roll ring —
# runs on the JVM, no emulator. Separate from `test` because it starts a
# Gradle daemon, which the TS suite has no business waiting on.
test-native:
	cd android && ./gradlew :raw-audio:testDebugUnitTest

# SEED_ARGS passes through, e.g. make seed SEED_ARGS='--count 30 --radius 800'
seed:
	python3 tools/seed_captures.py $(SEED_ARGS)
	$(ANDROID_HOME)/platform-tools/adb shell am force-stop com.cawtalker.field

seed-clear:
	python3 tools/seed_captures.py --clear
	$(ANDROID_HOME)/platform-tools/adb shell am force-stop com.cawtalker.field

check-node:
ifeq ($(NODE_BIN),)
	@echo "No nvm node found under $(NVM_DIR) (alias/default = '$(NODE_ALIAS)')." >&2
	@echo "Install one with 'nvm install --lts', or set NODE_BIN=/path/to/node/bin." >&2
	@exit 1
endif
