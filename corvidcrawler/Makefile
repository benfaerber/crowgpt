# The corpus crawler: Xeno-canto and the Macaulay Library into data/.
#
# Two ways in. `make crawl` / `make crawl-ml` fill data/species/<slug>/, the
# per-species tree `make train` at the repo root reads. `corvidcrawler crawl`
# fills data/audio/<source>/ indexed by data/corvid.db, which crowgpt and the
# dashboard's corpus panel read. Both go through the same source adapters and
# the same polite downloader.

.DEFAULT_GOAL := help
.PHONY: help venv test crawl crawl-ml

help:
	@echo "corvidcrawler — the two archives this repo may fetch from"
	@echo ""
	@echo "  make venv      create .venv (uv)"
	@echo "  make test      pytest, no network"
	@echo "  make crawl     one species from Xeno-canto   SP= [GEN=Corvus] [SLUG=] [LIMIT=500]"
	@echo "  make crawl-ml  one species from Macaulay     SLUG= [LIMIT=500] [CSV=]"
	@echo ""
	@echo "  uv run corvidcrawler crawl --gen Corvus --sp corone --download"
	@echo "  uv run corvidcrawler sources | jobs | recordings | stats"
	@echo ""
	@echo "  Xeno-canto needs XENOCANTO_KEY (free at https://xeno-canto.org/account);"
	@echo "  put it in .env here or at the repo root. DATA_DIR defaults to ../data."

venv:
	uv sync --python 3.10

test:
	uv run pytest -q

crawl:
	@test -n "$(SP)" || { echo "Which species? make crawl SP=corone [GEN=Corvus] [LIMIT=500]"; exit 1; }
	uv run corvidcrawler species --gen $(or $(GEN),Corvus) --sp $(SP) \
	  $(if $(SLUG),--slug $(SLUG)) $(if $(LIMIT),--limit $(LIMIT)) $(ARGS)

crawl-ml:
	@test -n "$(SLUG)" || { echo "Which species? e.g. make crawl-ml SLUG=rook"; exit 1; }
	uv run corvidcrawler species --source macaulay --slug $(SLUG) \
	  $(if $(LIMIT),--limit $(LIMIT)) $(if $(CSV),--csv $(CSV)) $(if $(REFRESH),--refresh) $(ARGS)
