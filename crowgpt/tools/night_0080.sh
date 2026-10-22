#!/bin/sh
# The 2026-08-19 chain: the incumbent's recipe at the batch it always claimed,
# then the structure gate. Emails Ben on any failed step.
REPO=/home/ben/Code/cawtalker
DATA=${DATA_DIR:-$REPO/data}
LOG=/tmp/crowgpt-night-0080.log
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

step "0080 train" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
    --n-embd 384 --n-layer 8 --dropout 0 --batch-size 8 --accumulate 4 \
    --token-dir "$DATA/crowgpt/tokens-6s" --out results/model-longctx-b32

step "0080 validate" \
    .venv/bin/python "$REPO/experiments/0080-does-the-batch-fix-reach-the-incumbent/validate.py"
