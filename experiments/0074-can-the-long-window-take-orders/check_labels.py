"""The histogram gate: fail the night before train spends two hours on junk.

Longer bouts mix call types, so single-class overlap gets rarer and the head
may abstain its way to a corpus that is all unknown — or an alarm-heavy head
may label everything alarm. Either way the conditioned model would learn
nothing worth the retrain, and this is the cheap place to find out.
"""

import json
import sys
from pathlib import Path

REPO = Path("/home/ben/Code/cawtalker")
LABELS = REPO / "data" / "crowgpt" / "bouts-6s" / "call_types.json"

# Per-class floors, not a blanket minimum: `call` was 272 bouts in the corpus
# that built model-calltype and still bought its 3.8% — the class is rare, not
# degenerate, and a flat 500 stopped the first run of this night for being its
# usual size. The floors are "no class below the corpus 0021 shipped with".
MIN_PER_CORE = {"alarm call": 20_000, "begging": 2_000, "call": 250, "song": 1_000}
MAX_UNKNOWN_SHARE = 0.85


def main():
    payload = json.loads(LABELS.read_text())
    histogram = payload["histogram"]
    total = sum(histogram.values())
    unknown_share = histogram.get("unknown", 0) / total
    print(f"labelled {total} bouts: " +
          " · ".join(f"{k} {v}" for k, v in sorted(histogram.items())))
    print(f"unknown share {unknown_share:.3f}")

    failures = []
    for core, floor in MIN_PER_CORE.items():
        if histogram.get(core, 0) < floor:
            failures.append(f"{core}: {histogram.get(core, 0)} < {floor}")
    if unknown_share > MAX_UNKNOWN_SHARE:
        failures.append(f"unknown share {unknown_share:.3f} > {MAX_UNKNOWN_SHARE}")
    if failures:
        print("DEGENERATE LABELS — stopping the night:", "; ".join(failures))
        return 1
    print("label histogram passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
