"""The crawler, driven from argv.

  corvidcrawler species --gen Corvus --sp corone            # data/species/<slug>/ + manifest
  corvidcrawler species --source macaulay --slug rook
  corvidcrawler crawl --gen Corvus --sp corone --download   # data/audio/<source>/ + corvid.db
  corvidcrawler sources | jobs | recordings | stats
"""

import argparse
import json
import time

from dotenv import load_dotenv

from .config import REPO, data_dir
from .database import DONE, TERMINAL, CrawlStore
from .errors import SourceError
from .report import CrawlReport
from .runner import JobRunner
from .sources import SOURCE_CLASSES, build_query_for, source_status

PACKAGE_ROOT = REPO / "corvidcrawler"


class CrawlFailed(RuntimeError):
    pass


class Cli:
    def __init__(self, data=None):
        load_dotenv(PACKAGE_ROOT / ".env")
        load_dotenv(REPO / ".env")
        self.data_dir = data or data_dir()
        self._store = None
        self._runner = None

    @property
    def store(self) -> CrawlStore:
        if self._store is None:
            self._store = CrawlStore(self.data_dir / "corvid.db")
            abandoned = self._store.fail_abandoned()
            if abandoned:
                print(f"closed {abandoned} job(s) left behind by a process that exited")
        return self._store

    @property
    def runner(self) -> JobRunner:
        if self._runner is None:
            self._runner = JobRunner(self.store, self.data_dir / "audio")
        return self._runner

    def _in_flight(self) -> str:
        live = self.runner.current
        if not live:
            return ""
        done = live["done"] / 1e6
        total = live.get("total")
        return f"{done:.0f}/{total / 1e6:.0f} MB" if total else f"{done:.0f} MB"

    def crawl(self, args) -> int:
        status = {s["id"]: s for s in source_status()}
        if args.source not in status:
            print(f"Unknown source '{args.source}'. One of: {', '.join(status)}")
            return 2
        if not status[args.source]["ready"]:
            print(f"{args.source} is not usable: {status[args.source]['blocked_by']}")
            return 2
        query = args.query or build_query_for(args.source, vars(args))
        max_recordings = max(1, args.max)
        job = self.store.create_job(
            source=args.source, query=query, params=vars(args),
            max_recordings=max_recordings, download=args.download, label=args.label or None)
        print(f"job {job['id']}: {args.source} '{query}', up to {max_recordings}"
              + (" (downloading)" if args.download else " (metadata only)"))
        step = args.query or args.sp or args.gen or args.source
        try:
            with CrawlReport(f"corvidcrawler — {step}", str(step)) as report:
                done = self._run_job(job["id"], report)
                if done["status"] != DONE:
                    raise CrawlFailed(done.get("error") or done["status"])
        except CrawlFailed as exc:
            print(f"  failed: {exc}")
            return 1
        print(f"  done: {done['fetched']} fetched, {done['downloaded']} downloaded")
        return 0

    def _run_job(self, job_id, report) -> dict:
        """Start the job and poll the store while it runs. The runner records
        fetched, downloaded and total on every file, so reading those rows
        twice a second is what keeps a two-hour crawl from looking like a hang."""
        self.runner.start(job_id)
        while True:
            job = self.store.get_job(job_id)
            if job is None:
                break
            found, cap = job.get("total_found"), job.get("max_recordings")
            target = min(found, cap) if found and cap else (found or cap)
            report.update(job.get("fetched") or 0, job.get("downloaded") or 0, target,
                          detail=self._in_flight())
            if job["status"] in TERMINAL:
                break
            time.sleep(0.5)
        self.runner.queue.join()
        return self.store.get_job(job_id) or {"status": "error", "fetched": 0, "downloaded": 0,
                                              "error": "job row vanished"}

    def species(self, args) -> int:
        from .species import SpeciesCrawl

        try:
            crawl = SpeciesCrawl(
                args.source, gen=args.gen, sp=args.sp, slug=args.slug, taxon=args.taxon,
                csv=args.csv, limit=args.limit, delay=args.delay,
                flush_every=args.flush_every, refresh=args.refresh, data=self.data_dir)
        except SourceError as exc:
            print(exc)
            return 2
        print(f"crawl {crawl.slug} from {args.source}: '{crawl.query}', "
              f"up to {crawl.total} recordings")
        summary = crawl.run()
        print(crawl.describe(summary))
        return 1 if summary["failed"] and not summary["records"] else 0

    def jobs(self, _args) -> int:
        print(json.dumps(self.store.list_jobs(), indent=2))
        return 0

    def recordings(self, args) -> int:
        rows = self.store.list_recordings(
            call_type=args.call_type, quality=args.quality, downloaded=args.downloaded,
            source=args.source, species=args.species, min_seconds=args.min_seconds,
            limit=min(args.limit, 1000))
        print(json.dumps(rows, indent=2))
        return 0

    def sources(self, args) -> int:
        rows = source_status()
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        for row in rows:
            mark = "ok " if row["ready"] else "-- "
            print(f"\n{mark}{row['name']}  ({row['id']})")
            print(f"     {row['description']}")
            print(f"     query is  {row['query_is']}")
            print(f"     docs      {row['docs']}")
            if row["blocked_by"]:
                print(f"     BLOCKED   {row['blocked_by']}")
        ready = [r["id"] for r in rows if r["ready"]]
        print(f"\n{len(ready)}/{len(rows)} usable right now: {', '.join(ready) or 'none'}")
        return 0

    def stats(self, args) -> int:
        data = self.store.stats()
        if args.json:
            print(json.dumps(data, indent=2))
            return 0
        print(f"{data['total']} recordings · {data['downloaded']} downloaded · "
              f"{data['hours']} h catalogued · {data['gigabytes']} GB · "
              f"{data['channels']} channels")
        print(f"\n{'by source':<24}{'recs':>7}{'dl':>7}{'hours':>8}{'GB':>7}")
        for row in data["by_source"]:
            print(f"  {row['source'][:22]:<22}{row['recordings']:>7}{row['downloaded'] or 0:>7}"
                  f"{row['hours']:>8.1f}{row['gigabytes']:>7.1f}")
        print(f"\n{'by species':<24}{'recs':>7}{'dl':>7}{'hours':>8}{'chans':>7}")
        for row in data["by_slug"]:
            print(f"  {row['slug'][:22]:<22}{row['recordings']:>7}{row['downloaded'] or 0:>7}"
                  f"{row['hours']:>8.1f}{row['channels']:>7}")
        print("\nhow the grouping was decided")
        for basis, count in data["by_group_basis"].items():
            note = {"rec-day": "recordist and day", "rec": "recordist only",
                    "file": "nothing — one recording per group"}.get(basis, "")
            print(f"  {basis:<12}{count:>8}   {note}")
        return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corvidcrawler", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sources = sorted(SOURCE_CLASSES)

    species = sub.add_parser("species", help="one species into data/species/<slug>/ "
                                             "with its manifest (what `make train` reads)")
    species.add_argument("--source", default="xeno_canto", choices=sources)
    species.add_argument("--gen", default="Corvus")
    species.add_argument("--sp", default=None, help="species epithet, e.g. corone")
    species.add_argument("--slug", default=None,
                         help="directory name; derived from the species preset if omitted")
    species.add_argument("--taxon", default=None, help="eBird taxon code, if the slug is unknown")
    species.add_argument("--csv", default=None,
                         help="Macaulay search export, instead of the search API")
    species.add_argument("--limit", type=int, default=500)
    species.add_argument("--delay", type=float, default=0.3)
    species.add_argument("--flush-every", dest="flush_every", type=int, default=200,
                         help="write the manifest this often, so a killed crawl keeps its audio")
    species.add_argument("--refresh", action="store_true",
                         help="re-ask the search API instead of using the cached asset list")
    species.set_defaults(run="species")

    crawl = sub.add_parser("crawl", help="fetch metadata (and optionally audio) into corvid.db")
    crawl.add_argument("--source", default="xeno_canto", choices=sources)
    crawl.add_argument("--query", default=None,
                       help="the source's own query, verbatim — see `sources` for what "
                            "each one means by it")
    crawl.add_argument("--gen", default="Corvus")
    crawl.add_argument("--sp", default=None, help="species epithet, e.g. corone")
    crawl.add_argument("--country", default=None)
    crawl.add_argument("--call-type", dest="call_type", default=None)
    crawl.add_argument("--quality", default=None, help="Xeno-canto grade A–E")
    crawl.add_argument("--max", type=int, default=100, help="how many recordings this job may fetch")
    crawl.add_argument("--download", action="store_true", help="also fetch the audio files")
    crawl.add_argument("--label", default=None)
    crawl.set_defaults(run="crawl")

    jobs = sub.add_parser("jobs", help="list crawl jobs")
    jobs.set_defaults(run="jobs")

    recs = sub.add_parser("recordings", help="list recordings in the store")
    recs.add_argument("--call-type", dest="call_type", default=None)
    recs.add_argument("--quality", default=None)
    recs.add_argument("--downloaded", action="store_true", default=None,
                      help="only rows whose audio is on disk")
    recs.add_argument("--source", default=None)
    recs.add_argument("--species", default=None, help="substring of the name, or a slug")
    recs.add_argument("--min-seconds", dest="min_seconds", type=int, default=None)
    recs.add_argument("--limit", type=int, default=200)
    recs.set_defaults(run="recordings")

    srcs = sub.add_parser("sources", help="the two sources, and whether each is usable now")
    srcs.add_argument("--json", action="store_true")
    srcs.set_defaults(run="sources")

    stats = sub.add_parser("stats", help="counts across the store")
    stats.add_argument("--json", action="store_true")
    stats.set_defaults(run="stats")
    return parser


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(getattr(Cli(), args.run)(args))


if __name__ == "__main__":
    main()
