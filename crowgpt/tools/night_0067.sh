#!/bin/sh
# The 2026-08-11 night chain: 0065's fixed-join rerun, then 0067's
# long-context build. Any failed step emails Ben (his ask: "ping me if you
# get blocked") with the tail of the step's own log; a hang shows up as a
# stale card on the dashboard instead, which every stage already feeds.
REPO=/home/ben/Code/cawtalker
DATA=${DATA_DIR:-$REPO/data}
LOG=/tmp/crowgpt-night-0067.log
EMAIL="$REPO/.claude/local/email_ben.py"

step() {
    name=$1; shift
    echo "== $name" >> "$LOG"
    if ! "$@" >> "$LOG" 2>&1; then
        python3 "$EMAIL" "crowgpt overnight blocked at: $name" \
            "$(tail -c 1800 "$LOG")" || true
        exit 1
    fi
}

cd "$REPO/crowgpt"
: > "$LOG"

step "0065 rerun (fixed source join)" \
    .venv/bin/python "$REPO/experiments/0065-did-the-diversity-arrive/run.py"

CROWGPT_BOUT_MAX_SEC=6 step "0067 extract, 6s cap" \
    env CROWGPT_BOUT_MAX_SEC=6 PYTHONPATH=src .venv/bin/python -m crowgpt.cli \
    extract --out "$DATA/crowgpt/bouts-6s"

step "0067 tokenize" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli tokenize --units \
    --variants 2 --bouts "$DATA/crowgpt/bouts-6s" --out "$DATA/crowgpt/tokens-6s"

step "0067 train" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
    --n-embd 384 --n-layer 8 --dropout 0 --batch-size 32 \
    --token-dir "$DATA/crowgpt/tokens-6s" --out results/model-longctx
