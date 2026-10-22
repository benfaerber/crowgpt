#!/bin/sh
# The 2026-08-15 night chain: 0074's conditioned long-context build.
# label (CPU) -> histogram gate -> tokenize -> manifest gate -> train (GPU,
# booked in GPU-CALENDAR.md) -> smoke draws. Any failed step emails Ben with
# the tail of the step's own log; a hang shows up as a stale card on the
# dashboard instead, which the label, tokenize and train stages all feed.
#
# Extraction is deliberately absent: bouts-6s survives from night_0067, and
# re-extracting would orphan the call_types.json this chain begins by writing.
REPO=/home/ben/Code/cawtalker
DATA=${DATA_DIR:-$REPO/data}
LOG=/tmp/crowgpt-night-0074.log
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

step "0074 label" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli label-calltypes \
    --bouts "$DATA/crowgpt/bouts-6s"

step "0074 label gate" \
    .venv/bin/python "$REPO/experiments/0074-can-the-long-window-take-orders/check_labels.py"

step "0074 tokenize" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli tokenize --units \
    --variants 2 --bouts "$DATA/crowgpt/bouts-6s" \
    --call-types "$DATA/crowgpt/bouts-6s/call_types.json" \
    --out "$DATA/crowgpt/tokens-6s-ct"

step "0074 manifest gate" \
    .venv/bin/python "$REPO/experiments/0074-can-the-long-window-take-orders/check_manifest.py"

step "0074 train" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
    --n-embd 384 --n-layer 8 --dropout 0 --batch-size 32 \
    --token-dir "$DATA/crowgpt/tokens-6s-ct" --out results/model-longctx-ct

step "0074 smoke" \
    .venv/bin/python "$REPO/experiments/0074-can-the-long-window-take-orders/smoke.py"
