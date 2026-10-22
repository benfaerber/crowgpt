# CrowGPT — generating crow calls from the archive corpus.
#
# Every stage runs in this module's own venv, which carries torch and
# birdnetlib together so extraction and training never have to hand off through
# a second interpreter. `make venv` builds it; everything else assumes it.
#
# The stages are separate targets on purpose. Extraction takes half an hour, and
# `gate` can legitimately tell you to stop and not train anything at all.

PY := .venv/bin/python
RUN := PYTHONPATH=src $(PY) -m crowgpt.cli

.DEFAULT_GOAL := help
.PHONY: help venv test watch extract gate tokenize train sample judge demo listen evaluate compare trainer finetune-decoder overnight overnight-check overnight-check-clean clean

help:
	@echo "crowgpt — generating crow calls"
	@echo "  make venv      create .venv with torch + birdnetlib (one-off, several GB)"
	@echo "  make test      pytest: segmentation, tokens, splits"
	@echo "  make extract   corpus -> call bouts on disk (~30 min, reports via make watch)"
	@echo "  make gate      can a neural codec carry a caw? -> experiments/0014"
	@echo "  make tokenize  bouts -> token memmaps  (BW=6.0 to override bandwidth)"
	@echo "  make train     train the model on the GPU"
	@echo "  make sample    generate wavs into results/samples"
	@echo "  make judge     four-arm BirdNET judgement + memorisation check"
	@echo "  make demo      write the listening-test page  [MODEL=] [SPECIES=] [N=] [GENERATE=1]"
	@echo "  make listen    what the recorded listening sessions add up to"
	@echo "  make evaluate  compare models on matched conditions, with error bars"
	@echo "  make compare   real vs codec vs generated, to hear which stage is rough"
	@echo "  make trainer   the call-type ear trainer page  [N=12] [SEED=0]"
	@echo "  make finetune-decoder  retrain EnCodec's decoder, tokens untouched"
	@echo "                 [ARM=adversarial|spectral] [PASSES=20] — see 0058 for the costing"
	@echo "  make watch     live view of a running job, for a second terminal"
	@echo "  make overnight-check  5-min dry run of every overnight stage, touches nothing"
	@echo "  make overnight unattended: re-extract, sweep capacity, judge, rebuild demo"
	@echo "                 [HOURS=8] [STEPS=40000] [SKIP=extract,tokenize] [BALANCE=0.5]"
	@echo "  make clean     remove results/ (leaves the extracted corpus alone)"

venv:
	uv sync --python 3.10

test:
	PYTHONPATH=src .venv/bin/pytest tests/ -q

extract:
	$(RUN) extract $(if $(LIMIT),--limit $(LIMIT))

gate:
	$(RUN) gate $(if $(N),--per-species $(N))

tokenize:
	$(RUN) tokenize $(if $(BW),--bandwidth $(BW))

train:
	$(RUN) train $(if $(STEPS),--steps $(STEPS))

sample:
	$(RUN) sample $(if $(N),-n $(N))

judge:
	$(RUN) judge $(if $(N),--per-species $(N))

demo:
	$(RUN) demo $(if $(N),-n $(N)) $(if $(MODEL),--model $(MODEL)) $(if $(SPECIES),--species $(SPECIES)) $(if $(GENERATE),--generate) $(if $(STASH),--stash) $(if $(AGAINST),--against $(AGAINST))

listen:
	$(RUN) listen $(if $(DETAIL),--detail)

evaluate:
	$(RUN) evaluate $(if $(N),--per-species $(N)) $(if $(MODELS),--models $(MODELS))

compare:
	$(RUN) compare $(if $(N),-n $(N))

trainer:
	$(RUN) trainer $(if $(N),--per-class $(N)) $(if $(SEED),--seed $(SEED)) $(if $(OUT),--out $(OUT))

finetune-decoder:
	PYTHONPATH=src $(PY) -m crowgpt.decoder_finetune --arm $(or $(ARM),adversarial) --passes $(or $(PASSES),20)

# The unattended run. Reports continuously into data/progress; `make watch` for status.
# Never overwrites results/model/ unless a candidate beats it on the four arms.
# Five-minute proof that the overnight run works: every stage, real audio, three
# recordings per species, into crowgpt/.check which is thrown away after.
# Live view for a second terminal. Refreshes every 5s; Ctrl-C to leave.
watch:
	@watch -n 5 -t ./watch.sh

overnight-check:
	PYTHONPATH=src $(PY) overnight.py --check
	@echo
	@echo "scratch left in .check/ — remove with: make overnight-check-clean"

overnight-check-clean:
	trash-put .check 2>/dev/null || true

overnight:
	PYTHONPATH=src $(PY) overnight.py $(if $(HOURS),--budget-hours $(HOURS)) \
	  $(if $(STEPS),--steps $(STEPS)) $(if $(SKIP),--skip $(SKIP)) \
	  $(if $(BALANCE),--balance $(BALANCE)) $(if $(FRESH),--fresh)

clean:
	trash-put results/model results/samples results/demo.html results/compare.html results/clips.json results/judge.json 2>/dev/null || true
