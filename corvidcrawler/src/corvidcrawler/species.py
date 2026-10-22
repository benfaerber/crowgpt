"""One species into data/species/<slug>/ — the tree `make train` reads.

Both archives write the same tree and the same manifest, each replacing only
its own records, so a species can be fed by both without either run deleting
the other's work. The manifest module is pipelines/ingest/manifest.py in this
repo, loaded by path so the format stays defined in one place.

The manifest is rewritten as the crawl runs, not only at the end: nothing
downstream can see a downloaded file no manifest mentions, so a crawl killed
at 90% used to leave gigabytes of audio invisible to the corpus.
"""

import importlib.util
from pathlib import Path

from .config import REPO, data_dir
from .download import Downloader
from .errors import SourceError
from .macaulay import MacaulayError, MacaulaySource
from .report import CrawlReport
from .runner import safe_stem
from .sources import CORVID_SPECIES
from .taxonomy import SPECIES, ebird_code
from .xeno_canto import XenoCantoSource, build_query

XENO_STAMP = "xeno-canto"
MACAULAY_STAMP = "macaulay"
MANIFEST_MODULE = REPO / "pipelines" / "ingest" / "manifest.py"


def load_manifest_module(path=MANIFEST_MODULE):
    spec = importlib.util.spec_from_file_location("cawtalker_manifest", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpeciesCrawl:
    def __init__(self, source_id, gen="Corvus", sp=None, slug=None, taxon=None, csv=None,
                 limit=500, delay=0.3, flush_every=200, refresh=False,
                 data=None, manifest=None, downloader=None, source=None, report=None):
        self.source_id = source_id
        self.gen, self.sp, self.taxon, self.csv = gen, sp, taxon, csv
        self.limit, self.flush_every, self.refresh = limit, flush_every, refresh
        self.slug = slug or self._preset_slug()
        self.data = Path(data) if data else data_dir()
        self.manifest = manifest or load_manifest_module()
        self.downloader = downloader or Downloader(delay=delay)
        self.report = report
        self.searched = {"listed": 0, "from_api": 0}
        self.source, self.query, self.total, self.stamp = self._plan(source)

    # -- planning ------------------------------------------------------------

    def _preset_slug(self) -> str:
        match = next((s for s in CORVID_SPECIES
                      if s["gen"].lower() == self.gen.lower()
                      and s["sp"].lower() == (self.sp or "").lower()), None)
        return (match["label"].lower().replace(" ", "-") if match
                else (self.sp or self.gen).lower())

    def _plan(self, source):
        if self.source_id == MacaulaySource.id:
            return self._plan_macaulay(source)
        return self._plan_xeno_canto(source)

    def _plan_xeno_canto(self, source):
        if not self.sp:
            raise SourceError("Xeno-canto needs --sp (the species epithet, e.g. corone).")
        source = source or XenoCantoSource()
        query = build_query({"gen": self.gen, "sp": self.sp})
        try:
            total = min(self.limit, source.count(query))
        except SourceError as exc:
            if "key" in str(exc).lower():
                raise
            total = self.limit
        return source, query, total, XENO_STAMP

    def _plan_macaulay(self, source):
        source = source or MacaulaySource(cache_dir=self.data / "cache", on_page=self._searched)
        if self.csv:
            return source, self.csv, min(self.limit, source.count(self.csv)), MACAULAY_STAMP
        code = self.taxon or ebird_code(self.slug)
        if not code:
            raise MacaulayError(
                f"No eBird taxon code known for '{self.slug}'. Pass --taxon or --csv. "
                f"Known: {', '.join(sorted(s for s in SPECIES if ebird_code(s)))}")
        # The search API reports no total, so the bar counts toward the limit.
        return source, code, self.limit, MACAULAY_STAMP

    def _searched(self, count, cached):
        self.searched["listed"] += count
        if not cached:
            self.searched["from_api"] += count

    # -- the crawl -----------------------------------------------------------

    @property
    def out_dir(self) -> Path:
        return self.data / "species" / self.slug / "audio"

    @property
    def manifest_path(self) -> Path:
        return self.data / "species" / self.slug / "manifest.json"

    def _flush(self, records):
        previous = self.manifest.load(self.manifest_path).get("recordings", [])
        merged, kept = self.manifest.merge_archive(previous, records, self.out_dir,
                                                   stamp=self.stamp)
        self.manifest.write(self.manifest_path, merged, slug=self.slug, gen=self.gen,
                            sp=self.sp, query=str(self.query))
        return merged, kept

    def _download(self, record, dest, on_bytes):
        """One file, or False if it was already on disk. Skipping is the cache."""
        if dest.exists() and dest.stat().st_size > 0:
            return False
        if hasattr(self.source, "download"):
            return self.source.download(record, dest, on_bytes=on_bytes)
        return self.downloader.fetch(record["audio_url"], dest, on_bytes=on_bytes)

    def run(self) -> dict:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        report = self.report or CrawlReport(f"corvidcrawler — {self.slug} from {self.source_id}",
                                            self.slug)
        summary = {"records": 0, "downloaded": 0, "on_disk": 0, "failed": 0, "megabytes": 0.0}
        records = []
        with report:
            report.update(0, 0, self.total)
            stream = self.source.fetch(self.query, max_recordings=self.limit,
                                       refresh=self.refresh)
            for rec in stream:
                rid = rec.get("source_ref")
                if not rec.get("audio_url") or not rid:
                    continue
                dest = self.out_dir / f"{safe_stem(rid)}.mp3"
                fetched = self._download(rec, dest, report.in_flight)
                if not dest.exists():
                    summary["failed"] += 1
                    continue
                if fetched:
                    summary["downloaded"] += 1
                    summary["megabytes"] += dest.stat().st_size / 1e6
                else:
                    summary["on_disk"] += 1
                records.append(self.manifest.record(
                    rid, dest, self.stamp,
                    call_type=rec.get("call_type"), quality=rec.get("quality"),
                    recordist=rec.get("recordist"), date=rec.get("date"),
                    locality=rec.get("location"),
                ))
                summary["records"] = len(records)
                if len(records) % self.flush_every == 0:
                    self._flush(records)
                report.update(len(records), summary["downloaded"], self.total,
                              detail=self._detail(summary))
            merged, kept = self._flush(records)
            summary["in_manifest"], summary["from_other_sources"] = len(merged), len(kept)
            report.note(self.describe(summary))
        return summary

    @staticmethod
    def _detail(summary) -> str:
        return (f"{summary['on_disk']} had"
                + (f" · {summary['failed']} failed" if summary["failed"] else "")
                + f" · {summary['megabytes']:.0f} MB")

    def describe(self, summary) -> str:
        return (f"{self.slug}: {summary['records']} recordings, "
                f"{summary['downloaded']} newly downloaded ({summary['megabytes']:.0f} MB), "
                f"{summary['on_disk']} already had"
                + (f", {summary['failed']} failed" if summary["failed"] else "")
                + (f", {self.searched['from_api']} listed from the search API"
                   if self.searched["listed"] else "")
                + f", {summary['in_manifest']} in manifest "
                  f"({summary['from_other_sources']} from other sources) -> {self.manifest_path}")
