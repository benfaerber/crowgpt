#!/bin/sh
# 0066's build: tokenize the standing corpus with the units-per-bout token,
# then train the standard recipe on it. Safe to re-run: tokenize rebuilds its
# own dir, train starts fresh at results/model-units. The v3 tokens and model
# are untouched — model-v3-scrape is 0066's control.
set -e
cd "$(dirname "$0")/.."
DATA=${DATA_DIR:-$(pwd)/../data}
PYTHONPATH=src .venv/bin/python -m crowgpt.cli tokenize --units --variants 2 \
  --out "$DATA/crowgpt/tokens-v4-units"
PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
  --n-embd 384 --n-layer 8 --dropout 0 --batch-size 32 \
  --token-dir "$DATA/crowgpt/tokens-v4-units" --out results/model-units
