#!/bin/sh
# The 2026-08-17 chain, run while Ben is at work: the conditioned 6 s model
# with model-calltype's optimisation (n_head 6, 40k steps, true batch 32),
# then the paired validation. Any failed step emails Ben.
REPO=/home/ben/Code/cawtalker
LOG=/tmp/crowgpt-night-0077.log
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

step "0077 train ct2" \
    .venv/bin/python "$REPO/experiments/0077-does-matching-the-calltype-recipe-close-the-gap/train.py"

step "0077 validate" \
    .venv/bin/python "$REPO/experiments/0077-does-matching-the-calltype-recipe-close-the-gap/validate.py"
