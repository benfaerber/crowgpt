"""The one exception type callers catch. Every source raises a subclass, so a
second source's failures surface with their real reason rather than falling
through to a generic handler."""


class SourceError(RuntimeError):
    pass
