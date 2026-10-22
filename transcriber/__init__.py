"""The Cawtalker transcriber.

Takes a recording of somebody talking, returns what they said. A path in, text
out — the same shape as `analyzer/`, and deliberately knowing nothing about the
field server: the worker owns jobs and storage and calls in here.

    from transcriber import whisper

A SIBLING OF `analyzer/` RATHER THAN A MODULE INSIDE IT, and the reason is a venv
rather than taste. `analyzer/` runs in `pipelines/representation/.venv-birdnet`,
which has no torch; a Whisper module there would be one that package's own
environment cannot import. This one runs in a torch venv (crowgpt's today) and
must never be imported into a process that has loaded birdnetlib — see
`transcriber/whisper.py` for what that costs and for the guard that refuses.

Nothing is re-exported here on purpose. `analyzer/__init__.py` needs a lazy
`__getattr__` because it lifts names *out* of `birdnet` and importing that loads
a model; a submodule needs no such help — `import transcriber` costs nothing and
`from transcriber import whisper` is what pays for torch. An earlier version of
this file tried to be clever about it anyway and recursed forever.
"""
