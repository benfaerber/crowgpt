"""0004's SNR measures, re-exported from their new home in analyzer/quality.py.

Four experiments carried byte-identical copies of these; then one home, here.
Now the field system stores the same numbers per capture, so the functions
live with the analyzer and this module is the guarantee that an experiment and
the `capture_quality` table can never quote different arithmetic — the import
is what enforces it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analyzer.quality import band_snr, noise_floor_dbfs  # noqa: E402, F401
