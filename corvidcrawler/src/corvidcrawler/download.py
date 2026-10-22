"""Polite, resumable audio fetches, shared by both sources.

Writes to a .part file and renames only once the body is complete. Writing
straight to the destination turns any interruption into a truncated file that
skip-if-exists then treats as complete forever, which is the one failure a
corpus cannot see from the outside.
"""

import os
import time
from pathlib import Path

import requests

from .politeness import Bucket

DEFAULT_USER_AGENT = "CawTalker corpus crawler/0.2 (+https://cawtalker.org)"


def default_user_agent() -> str:
    return os.environ.get("CRAWLER_USER_AGENT", DEFAULT_USER_AGENT)


class Downloader:
    """Hosts that answer a Range request with 206 get a leftover .part resumed;
    hosts that answer 200 restart it, which is still correct, only slower."""

    def __init__(self, delay=0.4, retries=4, timeout=60, user_agent=None, session=None,
                 bucket=None):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.user_agent = user_agent or default_user_agent()
        self.last_request = 0.0
        self.bucket = bucket if bucket is not None else Bucket()
        self.throttled_seconds = 0.0

    def _wait(self, url):
        self.throttled_seconds += self.bucket.wait(url)
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request = time.monotonic()

    def fetch(self, url, dest, on_bytes=None) -> bool:
        """Download to dest. True if the file is there afterwards.

        `on_bytes(done, total)` fires as the body arrives, for a caller whose
        bar counts whole recordings and would otherwise sit still on a long one.
        """
        dest = Path(dest)
        if dest.exists() and dest.stat().st_size > 0:
            return True
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")

        for attempt in range(self.retries):
            resume_from = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": self.user_agent}
            if resume_from:
                headers["Range"] = f"bytes={resume_from}-"
            self._wait(url)
            try:
                response = self.session.get(url, headers=headers, stream=True,
                                            timeout=self.timeout)
            except requests.RequestException:
                self._backoff(attempt)
                continue

            with response:
                if response.status_code in (429, 500, 502, 503, 504):
                    self._backoff(attempt, response.headers.get("Retry-After"))
                    continue
                if response.status_code == 416:
                    part.unlink(missing_ok=True)
                    continue
                if response.status_code not in (200, 206):
                    return False
                mode = "ab" if response.status_code == 206 and resume_from else "wb"
                declared = response.headers.get("Content-Length")
                total = (int(declared) + resume_from) if declared and declared.isdigit() else None
                done = resume_from
                try:
                    with open(part, mode) as out:
                        for chunk in response.iter_content(chunk_size=65536):
                            out.write(chunk)
                            done += len(chunk)
                            if on_bytes:
                                on_bytes(done, total)
                except (requests.RequestException, OSError):
                    self._backoff(attempt)
                    continue

            if part.stat().st_size == 0:
                part.unlink(missing_ok=True)
                return False
            if self._is_error_page(part):
                # A server under strain answers 200 with an HTML error body.
                # No audio format starts with '<'.
                part.unlink(missing_ok=True)
                self._backoff(attempt)
                continue
            part.replace(dest)
            return True
        return False

    @staticmethod
    def _is_error_page(part) -> bool:
        try:
            with open(part, "rb") as handle:
                head = handle.read(64).lstrip()
        except OSError:
            return False
        return head[:1] == b"<"

    def _backoff(self, attempt, retry_after=None):
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 60.0))
                return
            except (TypeError, ValueError):
                pass
        time.sleep(min(2 ** attempt, 30.0))
