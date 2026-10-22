#!/bin/sh
# The decoder finetune, both arms in order: spectral control, then adversarial.
#
# Built to run under a systemd user unit (see TODO.txt's decoder-finetune
# entry) and to be SAFE TO RESTART AT ANY POINT: each arm resumes from its
# latest checkpoint in results/decoder-finetune/<arm>/, and an arm that has
# already reached its step target exits immediately. So Restart=on-failure
# re-runs this script and loses at most one eval interval of work.
#
# Manage it with:
#   systemctl --user status crowgpt-finetune     is it running, since when
#   journalctl --user -u crowgpt-finetune -f     live stdout
#   systemctl --user stop crowgpt-finetune       pause (resume by re-running
#                                                the systemd-run command in
#                                                TODO.txt, or this script)
# Progress, as always: `make watch` and the dashboard Training panel.
set -e
cd "$(dirname "$0")/.."
PYTHONPATH=src .venv/bin/python -m crowgpt.decoder_finetune --arm spectral --passes 20
PYTHONPATH=src .venv/bin/python -m crowgpt.decoder_finetune --arm adversarial --passes 50
