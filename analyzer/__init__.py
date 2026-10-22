"""The CrowGPT analyzer.

Takes a recording, returns what is in it. Deliberately knows nothing about the
field server: the worker owns jobs and storage and calls in here, which keeps
the model runnable over a loose directory of files without a server, a database
or a queue.

    from analyzer import HEADS, analyze, to_wav, waveform_envelope

The BirdNET names below resolve lazily. Importing `birdnet` loads the model
and the heads, which is seconds — right for the worker, which imports the
module explicitly and wants to fail at startup, and wrong for `quality`, whose
consumers (the experiments, the backfill's common path) need thirty lines of
numpy and no model at all.
"""

_BIRDNET_NAMES = (
    "CROW_MIN_CONF",
    "CROW_TERMS",
    "HEADS",
    "NoAudioTrack",
    "analyze",
    "to_wav",
    "waveform_envelope",
)

__all__ = [*_BIRDNET_NAMES, "quality"]


def __getattr__(name):
    if name in _BIRDNET_NAMES:
        from . import birdnet
        return getattr(birdnet, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
