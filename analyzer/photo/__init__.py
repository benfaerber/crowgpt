"""Photo identification: names the corvid in a photo.

    from analyzer.photo import PhotoIdentifier

Like the audio side, it knows nothing about the field server: a path and
optional coordinates in, a ranked list of species out. Runs in its own venv
(`make photo-venv`), because BioCLIP and the bird detector need torch and the
BirdNET venv has none. Names resolve lazily so `atlas` stays importable with
numpy alone.
"""

_NAMES = {
    "PhotoIdentifier": "identify",
    "Identification": "identify",
    "SpeciesScore": "identify",
    "ModelMissing": "identify",
    "Atlas": "atlas",
}

__all__ = list(_NAMES)


def __getattr__(name):
    if name in _NAMES:
        from importlib import import_module
        return getattr(import_module(f".{_NAMES[name]}", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
