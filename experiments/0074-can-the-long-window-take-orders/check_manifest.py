"""The manifest gate: prefix_len 4 has never existed before this run.

Units x call types is a first; if the vocabulary came out wrong the train
would still converge on something, and nothing downstream would say what.
"""

import json
import sys
from pathlib import Path

REPO = Path("/home/ben/Code/cawtalker")
MANIFEST = REPO / "data" / "crowgpt" / "tokens-6s-ct" / "manifest.json"

EXPECTED_CALL_TYPES = ["alarm call", "begging", "call", "song", "unknown"]


def main():
    manifest = json.loads(MANIFEST.read_text())
    checks = {
        "call_types": (manifest.get("call_types"), EXPECTED_CALL_TYPES),
        "prefix_len": (manifest.get("prefix_len"), 4),
        "n_unit_buckets": (manifest.get("n_unit_buckets"), 5),
    }
    bad = {k: got for k, (got, want) in checks.items() if got != want}
    for k, (got, want) in checks.items():
        print(f"{k}: {got}" + ("" if got == want else f"  (wanted {want})"))
    if bad:
        print("MANIFEST WRONG — stopping the night")
        return 1
    print("manifest passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
