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
        self._swept = time.monotonic()

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.allowed

    def record_failure(self, key: str) -> None:
        with self._lock:
            recent = self._recent(key)
            recent.append(time.monotonic())
            self._failures[key] = recent
            self._sweep()

    def _sweep(self) -> None:
        """Once a window, forget every key that has gone quiet.

        `_recent` only prunes the key it is asked about, so an address that
        failed once and never returned stayed for the life of the process, and
        a caller with many addresses could grow the table without limit.
        """
        if time.monotonic() - self._swept < self.window:
            return
        self._swept = time.monotonic()
        for key in list(self._failures):
            self._recent(key)

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


class Allowance:
    """How many times a key may succeed inside a rolling window.

    The other half of the same idea, for a route where the successes are the
    cost: the promo's generate button spends real CPU on every press, and the
    caller has no secret to get wrong. `spend` counts the press and says
    whether it was within the allowance, so a refused press costs nothing.
    """

    def __init__(self, allowed: int, per_seconds: float):
        self._throttle = Throttle(allowed, per_seconds)
        self._lock = threading.Lock()

    def spent(self, key: str) -> bool:
        """Whether the allowance is already used up, without touching it:
        the question a route asks before doing any work for the caller."""
        with self._lock:
            return self._throttle.blocked(key)

    def spend(self, key: str) -> bool:
        # Check-and-record is one operation even when Flask handles a burst.
        with self._lock:
            if self._throttle.blocked(key):
                return False
            self._throttle.record_failure(key)
            return True
