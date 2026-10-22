#!/bin/sh
# The 2026-08-16 night chain, run while Ben sleeps at his ask: the batch-32
# retrain of the conditioned long-context model, then the paired validation.
# Any failed step emails Ben; progress cards feed the dashboard throughout.
REPO=/home/ben/Code/cawtalker
DATA=${DATA_DIR:-$REPO/data}
LOG=/tmp/crowgpt-night-0075.log
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

# Micro-batch stated honestly (8), accumulated to the 32 the flag always
# claimed. Same tokens, same steps, same everything else as model-longctx-ct.
step "0075 train b32" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
    --n-embd 384 --n-layer 8 --dropout 0 --batch-size 8 --accumulate 4 \
    --token-dir "$DATA/crowgpt/tokens-6s-ct" --out results/model-longctx-ct-b32

step "0075 validate" \
    .venv/bin/python "$REPO/experiments/0075-does-the-batch-the-recipe-claimed-matter/run.py"
