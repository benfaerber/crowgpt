"""Detections the model was not sure about.

The loop this breaks: the analyzer proposes, the recordist confirms,
confirmations become training data — so the corpus can only ever hold calls the
model already scores well, and the faint ones it most needs are filtered out
before anyone sees them. A real alarm call scored 0.183 and vanished; a begging
fledgling scored 0.06.

A candidate is a question, not a finding. It is offered for labelling and counts
as nothing until a human rules on it.
"""

import sqlite3

import pytest

from fieldserver.stores.analysis import AnalysisStore


@pytest.fixture
def analyzed(client, recordist, db_path):
    """A capture with one confident detection and one uncertain one."""
    capture = client.post("/api/captures", json={"client_uuid": "cap-1", "keep": True},
                          headers=recordist.headers).get_json()
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"client_uuid": "med-1"},
                        headers=recordist.headers).get_json()
    client.put(f"/api/media/{media['id']}", data=b"xyz",
               headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})

    store = AnalysisStore(db_path)
    job = store.enqueue(capture["id"], media["id"])
    store.complete(
        job["id"], capture_id=capture["id"], duration=30.0, waveform=[],
        reliability=1.0, model_version="test",
        calls=[
            {"start": 3.0, "end": 6.0, "species": "American Crow",
             "scientific_name": "Corvus brachyrhynchos", "call_type": "alarm call",
             "confidence": 0.9, "crow_conf": 0.976, "candidate": False},
            {"start": 15.0, "end": 18.0, "species": "American Crow",
             "scientific_name": "Corvus brachyrhynchos", "call_type": "alarm call",
             "confidence": 0.6, "crow_conf": 0.183, "candidate": True},
        ])
    return capture


class TestTheFlagSurvives:

    def test_both_detections_are_stored(self, analyzed, db_path):
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM detected_calls").fetchone()[0] == 2

    def test_the_uncertain_one_is_marked(self, analyzed, db_path):
        with sqlite3.connect(db_path) as conn:
            flags = dict(conn.execute(
                "SELECT crow_conf, candidate FROM detected_calls"))
        assert flags[0.976] == 0
        assert flags[0.183] == 1

    def test_it_reaches_the_client(self, client, recordist, analyzed):
        calls = client.get(f"/api/captures/{analyzed['id']}/calls",
                           headers=recordist.headers).get_json()["calls"]
        by_conf = {c["crow_conf"]: c["candidate"] for c in calls}
        assert by_conf[0.183] == 1
        assert by_conf[0.976] == 0

    def test_a_candidate_is_still_offered_for_labelling(
            self, client, recordist, analyzed):
        # The whole point. Filtering it out of the client's list would rebuild
        # the gate one layer up.
        calls = client.get(f"/api/captures/{analyzed['id']}/calls",
                           headers=recordist.headers).get_json()["calls"]
        assert len(calls) == 2


class TestItCountsAsNothing:

    def test_the_fleet_count_is_confirmed_only(self, client, operator, analyzed):
        summary = client.get("/api/fleet/summary", headers=operator.headers).get_json()
        assert summary["detected_calls"] == 1
        assert summary["candidate_calls"] == 1

    def test_the_capture_row_counts_confirmed_only(self, client, operator, analyzed):
        captures = client.get("/api/fleet/captures", headers=operator.headers).get_json()
        row = next(c for c in captures if c["id"] == analyzed["id"])
        assert row["call_count"] == 1

    def test_a_family_profile_ignores_candidates(
            self, client, operator, recordist, analyzed):
        family = client.post("/api/families", json={"client_uuid": "fam-1",
                                                    "name": "The Poe Family"},
                             headers=recordist.headers).get_json()
        client.patch(f"/api/captures/{analyzed['id']}",
                     json={"family_id": family["id"]}, headers=recordist.headers)
        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        # A vocal profile built from uncertain guesses is a profile of the street.
        assert sum(r["n"] for r in detail["call_types"]) == 1
