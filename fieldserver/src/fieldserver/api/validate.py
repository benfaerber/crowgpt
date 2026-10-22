"""Refuse garbage at the door, by name.

SQLite stores whatever it is handed — "north" goes into a REAL column without
complaint — so an unchecked value either crashed a store's own float() as a
500 with no field named, or landed in the corpus as text pretending to be a
number. The phone always sends real numbers; anything else is a bug worth a
400 that says which field, not a stack trace or a quiet corruption.

Same idiom as counts() in app.py: a bool is not a number, absent is fine.
"""

from flask import abort


def number(body, key, minimum=None, maximum=None):
    """The value as a float; None when absent; 400 when not a number."""
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        abort(400, f"{key} must be a number")
    if minimum is not None and value < minimum:
        abort(400, f"{key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        abort(400, f"{key} must be at most {maximum}")
    return float(value)


def whole(body, key, minimum=None):
    """The value as an int; None when absent; 400 when not an integer."""
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        abort(400, f"{key} must be an integer")
    if minimum is not None and value < minimum:
        abort(400, f"{key} must be at least {minimum}")
    return value


def span(body, start_key, end_key, minimum=0):
    """Two optional numbers where the end must not precede the start."""
    start = number(body, start_key, minimum=minimum)
    end = number(body, end_key, minimum=minimum)
    if start is not None and end is not None and end < start:
        abort(400, f"{end_key} must not precede {start_key}")
    return start, end
