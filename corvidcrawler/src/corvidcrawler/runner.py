"""Runs crawl jobs one at a time on a background thread: fetch metadata,
optionally download audio, and stream progress into the store.

One worker on purpose. Every job talks to the same archives, so jobs running
side by side would multiply the request rate the per-source delays cap. The
worker is a daemon thread: a killed process takes it down mid-write, which the
Downloader's .part-then-rename makes harmless, and fail_abandoned() at startup
closes the job rows such a death leaves behind.
"""

import re
import threading
from pathlib import Path
from queue import Queue
from urllib.parse import urlparse

from .database import CANCELED, RUNNING, CrawlStore
from .download import Downloader
from .errors import SourceError
from .sources import get_source

SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def safe_stem(source_ref) -> str:
    """`source_ref` is an id straight out of an archive's JSON. Unscrubbed, a
    value like '../../x' steers the write out of the audio directory."""
    return SAFE_FILENAME.sub("_", str(source_ref))


class JobRunner:
    def __init__(self, store: CrawlStore, audio_dir):
        self.store = store
        self.audio_dir = Path(audio_dir)
        self.downloader = Downloader()
        #: The file currently being transferred, for whoever is drawing a bar.
        self.current = None
        self.queue = Queue()
        self._worker_lock = threading.Lock()
        self._worker = None

    def start(self, job_id) -> None:
        self.queue.put(job_id)
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._drain, daemon=True)
                self._worker.start()

    def _drain(self) -> None:
        while True:
            job_id = self.queue.get()
            try:
                self._run(job_id)
            finally:
                self.queue.task_done()

    def _run(self, job_id) -> None:
        job = self.store.get_job(job_id)
        if job is None or job["status"] == CANCELED:
            return
        self.store.set_status(job_id, RUNNING)
        fetched = downloaded = 0
        try:
            source = get_source(job["source"])
            total_found = source.count(job["query"])
            self.store.update_progress(job_id, 0, 0, total_found)
            for rec in source.fetch(job["query"], max_recordings=job["max_recordings"],
                                    should_stop=lambda: self.store.is_canceled(job_id)):
                self.store.upsert_recording(job_id, rec)
                fetched += 1
                if job["download"] and self._download(source, rec):
                    downloaded += 1
                if fetched % 5 == 0 or job["download"]:
                    self.store.update_progress(job_id, fetched, downloaded, total_found)
            self.store.update_progress(job_id, fetched, downloaded, total_found)
            if not self.store.is_canceled(job_id):
                self.store.finish_job(job_id)
        except SourceError as exc:
            self.store.finish_job(job_id, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — surface any failure on the job row
            self.store.finish_job(job_id, error=f"Unexpected error: {exc}")

    def _download(self, source, rec: dict) -> bool:
        url = rec.get("audio_url")
        if not url:
            return False
        dest = self.audio_dir / rec["source"] / self._filename(rec, url)

        def on_bytes(done_bytes, total_bytes):
            self.current = {"name": dest.name, "done": done_bytes, "total": total_bytes}

        fetch = getattr(source, "download", None)
        try:
            done = (fetch(rec, dest, on_bytes=on_bytes) if fetch
                    else self.downloader.fetch(url, dest, on_bytes=on_bytes))
        finally:
            self.current = None
        if done:
            self.store.mark_downloaded(rec["source"], rec["source_ref"], str(dest))
        return done

    @staticmethod
    def _filename(rec: dict, url: str) -> str:
        suffix = Path(urlparse(url).path).suffix or ".mp3"
        return f"{safe_stem(rec['source_ref'])}{suffix}"
