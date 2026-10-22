#!/usr/bin/env bash
# Stop the field server and the inference worker.
#
# Lives in a script rather than inline in the Makefile for a reason: `pkill -f`
# matches against whole command lines, and a make recipe containing the pattern
# puts that pattern in make's own argv — so an inline version kills the shell
# running it before it reaches the real processes.

set -u

killed=0
for pattern in "bin/fieldserver" "uv run fieldserver" "worker/analyze_worker.py" \
               "worker/transcribe_worker.py" "worker/generate_worker.py" \
               "worker/scout_scheduler.py"; do
  for pid in $(pgrep -f "$pattern" 2>/dev/null); do
    # Never signal this script, its shell, or the make that invoked it.
    case " $$ $PPID " in *" $pid "*) continue ;; esac
    kill "$pid" 2>/dev/null && killed=$((killed + 1))
  done
done

sleep 1

if ss -ltn 2>/dev/null | grep -qE ':5100 '; then
  echo "Still bound — something else is serving :5100."
  exit 1
fi

echo "Field server and worker stopped (${killed} process(es))."
