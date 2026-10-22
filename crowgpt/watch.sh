#!/usr/bin/env bash
# One screen answering: is it alive, where is it, and has anything landed yet.
# Called by `make -C crowgpt watch`; safe to run on its own.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Active runs, rendered from data/progress/*.json — the one canonical record.
progress="$(python3 "$HERE/src/crowgpt/progress.py" 2>/dev/null)"

if pgrep -f "overnight.py" >/dev/null 2>&1; then
  pid=$(pgrep -f "overnight.py" | head -1)
  started=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs)
  echo "RUNNING   pid $pid   since ${started:-?}"
else
  echo "NOT RUNNING   (finished, or never started — see the stages below)"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  gpu=$(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu \
        --format=csv,noheader,nounits 2>/dev/null | head -1)
  if [ -n "$gpu" ]; then
    used=$(echo "$gpu" | cut -d, -f1 | xargs)
    total=$(echo "$gpu" | cut -d, -f2 | xargs)
    util=$(echo "$gpu" | cut -d, -f3 | xargs)
    # An idle GPU during a training stage is the failure that cost a night:
    # torch falling back to the CPU and saying nothing.
    warn=""
    [ "$util" -lt 20 ] 2>/dev/null && printf '%s' "$progress" | grep -q "^  \[>\] train" \
      && warn="   <-- TRAINING BUT GPU IDLE, something is wrong"
    echo "GPU       ${used} / ${total} MiB   ${util}% util${warn}"
  fi
fi
echo "LOAD     $(uptime | sed 's/.*load average: //')"
echo

if [ -n "$progress" ]; then
  printf '%s\n' "$progress"
else
  echo "no runs reporting yet"
fi

shopt -s nullglob
judged=("$HERE"/results/model-*/judge.json)
if [ ${#judged[@]} -gt 0 ]; then
  echo
  echo "--- judged so far (generated / codec ceiling) ---"
  for j in "${judged[@]}"; do
    python3 - "$j" <<'PY' 2>/dev/null
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.load(p.open())
g, c = d["C_generated"]["detected_rate"], d["B_real_codec"]["detected_rate"]
print("  %-14s %5.1f%%  of %5.1f%%   (%.0f%% of ceiling)" %
      (p.parent.name.replace("model-", ""), 100*g, 100*c, 100*g/c if c else 0))
PY
  done
fi
