#!/bin/sh
# The 2026-08-17 night chain: the 9 s window rung. Tokenize -> manifest gate ->
# 50-step VRAM preflight at the novel block size -> full train at true batch
# 32 -> structure validation against a 9 s real reference. Emails Ben on any
# failed step; every long stage feeds the dashboard.
REPO=/home/ben/Code/cawtalker
DATA=${DATA_DIR:-$REPO/data}
LOG=/tmp/crowgpt-night-0079.log
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

step "0079 tokenize" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli tokenize --units \
    --variants 2 --bouts "$DATA/crowgpt/bouts-9s" --out "$DATA/crowgpt/tokens-9s"

step "0079 manifest gate" \
    .venv/bin/python -c "
import json
m = json.loads(open('$DATA/crowgpt/tokens-9s/manifest.json').read())
assert m['call_types'] == [], m['call_types']
assert m['n_unit_buckets'] == 5, m['n_unit_buckets']
print('manifest passes:', {k: m[k] for k in ('vocab_size', 'prefix_len')})"

# The first block size past 4096 in the project: prove the card carries it
# before committing six hours to finding out it does not.
step "0079 preflight (50 steps)" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 50 \
    --n-embd 384 --n-layer 8 --dropout 0 --batch-size 4 --accumulate 8 \
    --block-size 6000 --token-dir "$DATA/crowgpt/tokens-9s" \
    --out results/.preflight-long9

step "0079 train" \
    env PYTHONPATH=src .venv/bin/python -m crowgpt.cli train --steps 30000 \
    --n-embd 384 --n-layer 8 --dropout 0 --batch-size 4 --accumulate 8 \
    --block-size 6000 --token-dir "$DATA/crowgpt/tokens-9s" \
    --out results/model-long9

step "0079 validate" \
    .venv/bin/python "$REPO/experiments/0079-does-nine-seconds-buy-more-structure/validate.py"
