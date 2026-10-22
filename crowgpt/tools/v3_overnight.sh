#!/bin/sh
# The v3 build: re-extract the corpus (now holding the 2026-08 scrape),
# tokenize to a fresh token dir, train the incumbent's exact recipe on it.
# Experiment 0064 holds the predictions this either confirms or kills.
#
# Deliberately NOT auto-restarting: extract and tokenize re-run from scratch
# on a restart, so a persistent failure would loop for hours. A failure shows
# on the dashboard instead — each stage reports through crowgpt.progress.Run,
# which carries the traceback into data/progress/<slug>.json.
#
# v2 artifacts are preserved on purpose: bouts.pre-v3 (hardlink snapshot),
# the standing tokens/ dir, and every model-* checkpoint. Only the bout
# store itself is rebuilt in place — 0056's re-extract precedent.
set -e
cd "$(dirname "$0")/.."
DATA=${DATA_DIR:-$(pwd)/../data}
PYTHONPATH=src .venv/bin/python -m crowgpt.cli extract
PYTHONPATH=src .venv/bin/python -m crowgpt.cli tokenize --out "$DATA/crowgpt/tokens-v3" --variants 2
PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
  --n-embd 384 --n-layer 8 --dropout 0 --batch-size 32 \
  --token-dir "$DATA/crowgpt/tokens-v3" --out results/model-v3-scrape
