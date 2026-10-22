"""CawScout layer generation — the production home of experiment 0084's PoC.

The science (signals, weights, effort correction, district floors) is
documented in experiments/0084-where-should-i-scout/README.md; this package
is its maintained implementation. `tools/build_scout.py` is the entry point.
"""

from .builder import ScoutLayerBuilder, validate
from .regions import REGIONS, Region

__all__ = ["ScoutLayerBuilder", "validate", "REGIONS", "Region"]
