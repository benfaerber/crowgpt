"""Where the corpus lives: DATA_DIR, else data/ at the repo root.

The same rule every other reader in this repo follows, so the crawler writes
where crowgpt, the pipelines and the dashboard's corpus panel look.
"""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    override = os.environ.get("DATA_DIR")
    return Path(override).expanduser() if override else REPO / "data"
