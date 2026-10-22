# corvidcrawler

Fetches corvid recordings from **Xeno-canto** and the **Macaulay Library** into
`data/`, the corpus the rest of CawTalker reads. These are the two archives
this repository may name and fetch from; anything else in a corpus arrived
through other tooling that is not part of this tree.

Headless and CLI-only. No server, no browser automation: both archives have
JSON APIs.

## Setup

```bash
cd corvidcrawler
make venv                     # uv sync
cp .env.example .env          # add XENOCANTO_KEY (free at xeno-canto.org/account)
uv run corvidcrawler sources  # says which of the two is usable right now
```

`DATA_DIR` defaults to `data/` at the repo root, the same rule every other
reader in the repo follows. The repo-root `.env` is read too.

## Two ways in

**Per species, for training heads.** Writes `data/species/<slug>/audio/` and
the `manifest.json` beside it, which `make train SLUG=<slug>` at the repo root
reads. Each archive replaces only its own records in the manifest, so a species
can be fed by both, and field labels exported into it survive a re-crawl.

```bash
make crawl SP=corone LIMIT=500                 # Xeno-canto: Corvus corone -> carrion-crow
make crawl SP=corax SLUG=common-raven          # name the directory yourself
make crawl-ml SLUG=rook LIMIT=500              # Macaulay, by search
make crawl-ml SLUG=american-crow CSV=~/Downloads/ML_amecro.csv   # from a hand export
```

**Into the corpus database, for CrowGPT and the dashboard.** Writes
`data/audio/<source>/` and a row per recording in `data/corvid.db`, with the
species slug and the channel grouping resolved at write time.

```bash
uv run corvidcrawler crawl --gen Corvus --sp corone --max 200 --download
uv run corvidcrawler crawl --source macaulay --query rook --max 200 --download
uv run corvidcrawler stats
```

Both paths report through `data/progress/<slug>.json`, so a crawl shows on the
operator dashboard's Training panel and under `make watch`.

## What each source means by a query

| source | `--query` is | counts up front | reports duration |
|---|---|---|---|
| `xeno_canto` | a v3 search expression, `gen:Corvus sp:corone q:A` | yes | yes |
| `macaulay` | a species slug (`rook`), an eBird code (`rook1`), or a CSV export path | only the CSV | no |

Macaulay pages by opaque cursor and reports no total, so a bar on a Macaulay
crawl counts toward `--max`, never toward the species. Its search pages are
cached under `data/cache/macaulay/`, so a re-run or a raised limit costs no
search calls for assets already listed; `--refresh` throws the cache away.

**Prefer the CSV export for Macaulay.** The search host's `robots.txt`
disallows automated crawling, and since at least 2026-09-10 its search
endpoint answers a script with a browser check rather than JSON; the crawler
reports that and stops rather than retrying. Run the search in the web UI,
use Download to get the CSV, and pass it with `CSV=` — the media host serves
the same files either way. Cornell also fulfils research media requests
through its help desk. Cached search pages still serve without a request.

## Being a good citizen

- One request budget per host, shared across every process on the machine
  through `data/cache/limits/`, so two shells cannot double the rate.
- Downloads go to a `.part` file and are renamed only once complete; a
  leftover part is resumed where the host allows it. An HTML error body
  answered with a 200 is retried, never kept.
- The User-Agent names the project; set `CRAWLER_USER_AGENT` to add a way to
  reach you.
- Every row keeps the archive's licence text and the recordist, so attribution
  is possible. Macaulay media is not Creative Commons; the corpus stays out of
  git.

## Tests

```bash
make test
```

No network: every archive is a scripted fake.
