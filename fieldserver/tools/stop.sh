#!/usr/bin/env bash
# Stop the field server and the inference worker.
#
# Lives in a script rather than inline in the Makefile for a reason: `pkill -f`
# matches against whole command lines, and a make recipe containing the pattern
# puts that pattern in make's own argv — so an inline version kills the shell
# running it before it reaches the real processes.

set -u

killed=0
# The worker scripts come from workers.toml, so a worker added there is
# stopped here without this file hearing about it.
registry="$(dirname "$0")/../workers.toml"
scripts=$(sed -n 's/^script = "\(.*\)"$/\1/p' "$registry")

for pattern in "bin/fieldserver" "uv run fieldserver" "fieldserver.core.workers dev" $scripts; do
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
