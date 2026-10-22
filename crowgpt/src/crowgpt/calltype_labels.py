"""Reading the positional call-type map that `label-calltypes` writes.

Its own module rather than a corner of cli.py for one measured reason:
importing crowgpt.cli claims the GPU at module level (`claim()` pulls torch
and opens a CUDA context, ~800 ms), and the one test that exercises this
function was paying that to parse JSON. Anything that only needs the label
map imports it from here at no cost.
"""

import json
from pathlib import Path


def load_calltypes(path, store):
    """The positional label map from `label-calltypes`, checked against `store`.

    The check is the whole point of the metadata: bouts-v1's file outlived its
    index and the mismatch was silent. Here it is one line and fatal.
    """
    payload = json.loads(Path(path).read_text())
    if payload["n_bouts"] != len(store):
        raise SystemExit(
            f"{path} was built for {payload['n_bouts']} bouts "
            f"({payload.get('bouts')}); this store has {len(store)} — "
            "positional labels do not survive re-extraction; rerun "
            "label-calltypes")
    return {int(k): v for k, v in payload["call_types"].items()}
