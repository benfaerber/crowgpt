"""The two shared secrets, and the refusal to serve with them unchanged.

Two, because they buy different things. The enrolment token lets a phone join
the fleet and see its own captures; the operator token unlocks /api/fleet/* —
every device, every capture, every recording. Operator status used to be
whatever the registering client claimed it was, which meant anyone who could
enrol could read the whole corpus.

Here rather than in app.py because the routes that check them now live in their
own module, and a second copy of a secret is how one of them ends up compared
against the wrong thing.
"""

import os
import secrets

DEFAULT_ENROLL_TOKEN = "dev-enroll"
DEFAULT_OPERATOR_TOKEN = "dev-operator"
# The browser is a contributor like any other; it just never records anything.
DASHBOARD_CONTRIBUTOR = "Operator dashboard"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
# `or DEFAULT`, not `get(name, DEFAULT)`: an exported-but-empty variable
# (a blank line in a sourced env file, a truncated secrets.env) is not a secret
# of "", it is no secret at all. Folding it to the default means the empty case
# is caught by the same off-loopback refusal every other weak secret is, instead
# of silently authenticating a request that omits the field entirely.
ENROLL_SECRET = os.environ.get("FIELD_ENROLL_TOKEN") or DEFAULT_ENROLL_TOKEN
OPERATOR_SECRET = os.environ.get("FIELD_OPERATOR_TOKEN") or DEFAULT_OPERATOR_TOKEN


def presented(body: dict, field: str, secret: str) -> bool:
    """Constant-time check of a client-presented secret.

    An empty configured secret matches nothing: without this guard a blank
    secret compares equal to a request that simply omits the field, which is
    authentication turned off wearing the shape of authentication left on.
    """
    if not secret:
        return False
    return secrets.compare_digest(str(body.get(field) or ""), secret)
