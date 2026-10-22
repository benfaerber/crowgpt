"""A ceiling on how fast a caller can guess a shared secret.

The enrollment token, the operator token and a claim code are all strings that
somebody types into a phone, and the only thing between the Wi-Fi and the whole
corpus is that nobody guesses one. Without a limit, "guesses" is however fast a
laptop can post — thousands a second on a home network, which turns a token
short enough to type into one short enough to find.

In-process and in-memory on purpose: one server, one fleet, no Redis. It resets
on restart, and that is the right trade for something whose job is to keep an
online guess at online speed rather than to be a durable ledger.

Failures only. A recordist enrolling three handsets, or an operator reloading
the dashboard, never touches this — the count only moves for a caller who keeps
getting the secret wrong, which is the behaviour worth stopping and the one
nobody does by accident.
"""

import threading
import time


class Throttle:
    """How many failures a key is allowed inside a rolling window."""

    def __init__(self, allowed: int, per_seconds: float):
        self.allowed = allowed
        self.window = per_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.allowed

    def record_failure(self, key: str) -> None:
        with self._lock:
            recent = self._recent(key)
            recent.append(time.monotonic())
            self._failures[key] = recent

    def _recent(self, key: str) -> list[float]:
        """This key's failures inside the window, forgetting the ones outside it.

        Prunes on read rather than on a timer, and drops a key that has gone
        quiet — otherwise every address that ever mistyped a token stays in the
        dictionary for the life of the process.
        """
        cutoff = time.monotonic() - self.window
        kept = [at for at in self._failures.get(key, []) if at > cutoff]
        if kept:
            self._failures[key] = kept
        else:
            self._failures.pop(key, None)
        return kept
