"""Xeno-canto and the Macaulay Library, into the CrowGPT corpus.

Lazy on purpose: `corvidcrawler.database` is stdlib-only and other venvs may
import it. Importing the CLI here eagerly would drag requests and dotenv into
every consumer that only wants the store.
"""

__all__ = ["Cli", "main"]


def __getattr__(name):
    if name in __all__:
        from corvidcrawler import cli
        return getattr(cli, name)
    raise AttributeError(name)
