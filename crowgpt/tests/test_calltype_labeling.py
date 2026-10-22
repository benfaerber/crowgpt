"""The positional call-type file and its pairing check.

bouts-v1's call_types.json outlived its bout store and the mismatch was silent;
`load_calltypes` is the one line that makes it fatal. The labelling pipeline
itself needs BirdNET and a corpus, so these tests stop at the file contract.
"""

import json

import pytest

from crowgpt.calltype_labels import load_calltypes


class FakeStore:
    def __init__(self, n):
        self.n = n

    def __len__(self):
        return self.n


def write_payload(tmp_path, n_bouts, call_types):
    path = tmp_path / "call_types.json"
    path.write_text(json.dumps({
        "bouts": "bouts-test", "n_bouts": n_bouts, "call_types": call_types,
    }))
    return path


def test_round_trip_keys_become_positions(tmp_path):
    path = write_payload(tmp_path, 3, {"0": "alarm call", "2": "song"})
    assert load_calltypes(path, FakeStore(3)) == {0: "alarm call", 2: "song"}


def test_mismatched_store_fails_loudly(tmp_path):
    path = write_payload(tmp_path, 3, {"0": "alarm call"})
    with pytest.raises(SystemExit, match="positional labels do not survive"):
        load_calltypes(path, FakeStore(5))
