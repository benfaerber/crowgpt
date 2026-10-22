"""One request budget per host, shared by every process on this machine.

The budget lives in a JSON file under DATA_DIR/cache/limits/, so two shells
crawling at once share one clock instead of each keeping their own — which is
a silent doubling of the request rate that nothing inside one process can see.

Neither archive publishes a rate limit. An unstated limit means we do not
know, so both run well under a request a second.
"""

import json
import time
from pathlib import Path
from urllib.parse import urlparse

from .config import data_dir

POLICIES = {
    "xeno-canto.org": {"per_minute": 60, "note": "no published limit"},
    "search.macaulaylibrary.org": {"per_minute": 30, "note": "no published limit"},
    "cdn.download.ams.birds.cornell.edu": {"per_minute": 60, "note": "the Macaulay media host"},
}

DEFAULT_POLICY = {"per_minute": 30, "note": "an unrecognised host — the slowest setting"}

WINDOW_SECONDS = 60.0


def policy_for(url: str) -> dict:
    host = (urlparse(str(url)).hostname or "").lower()
    if host in POLICIES:
        return {**POLICIES[host], "host": host}
    for known, policy in POLICIES.items():
        if host.endswith("." + known):
            return {**policy, "host": host}
    return {**DEFAULT_POLICY, "host": host or "unknown"}


class Bucket:
    """A per-host request budget shared through a file.

    Deliberately crude: the last N request timestamps, trimmed to the window.
    At tens of requests a minute the file never grows past a few hundred bytes.
    """

    def __init__(self, root=None, sleeper=time.sleep):
        self.dir = Path(root).expanduser() / "cache" / "limits" if root else data_dir() / "cache" / "limits"
        self.sleeper = sleeper

    def _path(self, host) -> Path:
        return self.dir / f"{host.replace('/', '_')}.json"

    def _read(self, path) -> list:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [float(t) for t in data.get("times", [])]
        except (OSError, ValueError, AttributeError):
            return []

    def wait(self, url) -> float:
        """Block until another request to this host is within budget.

        Returns the seconds waited, so a caller can report throttling instead
        of merely looking slow.
        """
        policy = policy_for(url)
        path = self._path(policy["host"])
        path.parent.mkdir(parents=True, exist_ok=True)

        now = time.time()
        allowed = max(1, int(policy["per_minute"]))
        times = [t for t in self._read(path) if now - t < WINDOW_SECONDS]
        waited = 0.0
        if len(times) >= allowed:
            sleep_for = WINDOW_SECONDS - (now - min(times))
            if sleep_for > 0:
                self.sleeper(sleep_for)
                waited = sleep_for
                now = time.time()
                times = [t for t in times if now - t < WINDOW_SECONDS]
        times.append(now)
        try:
            path.write_text(json.dumps({"times": times[-allowed * 2:]}), encoding="utf-8")
        except OSError:
            pass
        return waited
