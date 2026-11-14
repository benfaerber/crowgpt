"""The throttle's own table: it must forget, or it is a slow leak."""

from fieldserver.core import throttle
from fieldserver.core.throttle import Throttle


def test_addresses_that_never_return_are_forgotten(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(throttle.time, "monotonic", lambda: clock[0])
    guesses = Throttle(allowed=3, per_seconds=60)
    for n in range(500):
        guesses.record_failure(f"198.51.100.{n}")
    assert len(guesses._failures) == 500

    clock[0] += 61
    guesses.record_failure("203.0.113.9")
    assert list(guesses._failures) == ["203.0.113.9"]


def test_a_caller_still_guessing_is_not_forgotten_by_the_sweep(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(throttle.time, "monotonic", lambda: clock[0])
    guesses = Throttle(allowed=3, per_seconds=60)
    for _ in range(3):
        clock[0] += 25
        guesses.record_failure("198.51.100.7")
    assert guesses.blocked("198.51.100.7")
