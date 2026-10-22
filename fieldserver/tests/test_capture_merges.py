"""Which captures were folded into which, and why both copies stay.

A stop-start session — record, stop, the crow caws again, record — produces one
event as several captures. The phone joins them and uploads the result as an
ordinary capture, so the server never sees a merge happen; it is told about one
afterwards.

Both copies are kept for now: deleting the parts would make a merge
irreversible, and the ★ Keep flag is the only thing separating real field audio
from seeded clips. The price is that the corpus holds those calls twice, which
is only safe while `part_ids()` exists for anything counting — so that is what
these tests hold in place.
"""

import pytest


@pytest.fixture
def parts(client, recordist):
    """Four captures of one scene, as captures 94-97 were."""
    return [client.post("/api/captures", json={"client_uuid": f"part-{i}"},
                        headers=recordist.headers).get_json()
            for i in range(4)]


@pytest.fixture
def merged(client, recordist):
    return client.post("/api/captures", json={"client_uuid": "merged"},
                       headers=recordist.headers).get_json()


@pytest.fixture
def record(client, recordist, merged, parts):
    def _record(which=None, **over):
        chosen = parts if which is None else which
        body = {"parts": [{"capture_id": p["id"], "offset_ms": i * 22_000}
                          for i, p in enumerate(chosen)], **over}
        return client.post(f"/api/captures/{merged['id']}/merge", json=body,
                           headers=recordist.headers)
    return _record


class TestRecordingAMerge:
    def test_the_parts_come_back_in_order(self, record):
        body = record().get_json()
        assert [p["position"] for p in body["parts"]] == [0, 1, 2, 3]

    def test_the_offsets_are_kept(self, record):
        parts_back = record().get_json()["parts"]
        assert [p["offset_ms"] for p in parts_back] == [0, 22_000, 44_000, 66_000]

    def test_it_reads_back(self, client, recordist, merged, record):
        record()
        got = client.get(f"/api/captures/{merged['id']}/merge",
                         headers=recordist.headers).get_json()
        assert len(got["parts"]) == 4

    def test_a_capture_not_in_a_merge_reads_empty(self, client, recordist, parts):
        got = client.get(f"/api/captures/{parts[0]['id']}/merge",
                         headers=recordist.headers).get_json()
        assert got["parts"] == []


class TestTheOffsetsAreTheWholePoint:
    """The server cannot recompute them: the gap is the client's choice."""

    def test_a_missing_offset_is_refused(self, client, recordist, merged, parts):
        body = {"parts": [{"capture_id": p["id"]} for p in parts]}
        r = client.post(f"/api/captures/{merged['id']}/merge", json=body,
                        headers=recordist.headers)
        assert r.status_code == 400
        assert "offset_ms" in r.get_data(as_text=True)

    def test_a_negative_offset_is_refused(self, record, parts):
        r = record(parts=[{"capture_id": parts[0]["id"], "offset_ms": -1},
                          {"capture_id": parts[1]["id"], "offset_ms": 0}])
        assert r.status_code == 400


class TestRefusing:
    def test_one_part_is_recorded(self, record, parts):
        """A merge needs two captures; this record does not.

        Parts that never reached the server are folded in locally and only the
        joined audio is uploaded, so a three-way merge where one part had synced
        leaves exactly one row here to supersede. Refusing it would leave that
        capture duplicated by the merged audio with nothing saying so.
        """
        assert record(which=parts[:1]).status_code == 201

    def test_an_empty_list_is_not_a_record(self, client, recordist, merged):
        r = client.post(f"/api/captures/{merged['id']}/merge", json={"parts": []},
                        headers=recordist.headers)
        assert r.status_code == 400

    def test_a_capture_cannot_be_folded_into_itself(self, client, recordist, merged, parts):
        body = {"parts": [{"capture_id": merged["id"], "offset_ms": 0},
                          {"capture_id": parts[0]["id"], "offset_ms": 1000}]}
        r = client.post(f"/api/captures/{merged['id']}/merge", json=body,
                        headers=recordist.headers)
        assert r.status_code == 400

    def test_somebody_elses_recording_cannot_be_named_as_a_part(
            self, client, recordist, stranger, merged):
        """Ownership is checked per part, not just on the merged capture.

        Otherwise a merge is a way to write a row pointing at a recording you
        cannot otherwise touch.
        """
        theirs = client.post("/api/captures", json={"client_uuid": "theirs"},
                             headers=stranger.headers).get_json()
        mine = client.post("/api/captures", json={"client_uuid": "mine"},
                           headers=recordist.headers).get_json()
        body = {"parts": [{"capture_id": theirs["id"], "offset_ms": 0},
                          {"capture_id": mine["id"], "offset_ms": 1000}]}
        r = client.post(f"/api/captures/{merged['id']}/merge", json=body,
                        headers=recordist.headers)
        assert r.status_code == 403


class TestRetrying:
    """Sync retries. A retry must not record the merge twice."""

    def test_the_same_merge_twice_is_a_no_op(self, record, merged, client, recordist):
        record()
        record()
        got = client.get(f"/api/captures/{merged['id']}/merge",
                         headers=recordist.headers).get_json()
        assert len(got["parts"]) == 4

    def test_folding_a_part_into_a_second_merge_is_a_conflict(
            self, client, recordist, record, parts):
        record()
        other = client.post("/api/captures", json={"client_uuid": "other"},
                            headers=recordist.headers).get_json()
        body = {"parts": [{"capture_id": parts[0]["id"], "offset_ms": 0},
                          {"capture_id": parts[1]["id"], "offset_ms": 1000}]}
        r = client.post(f"/api/captures/{other['id']}/merge", json=body,
                        headers=recordist.headers)
        assert r.status_code == 409


class TestNotCountingTheSameBirdsTwice:
    def test_the_parts_are_listed_as_folded_away(self, db_path, record, parts):
        record()
        from fieldserver.stores.merges import MergeStore
        store = MergeStore(db_path)
        assert store.part_ids() == {p["id"] for p in parts}

    def test_the_merged_capture_is_not_one_of_them(self, db_path, record, merged):
        record()
        from fieldserver.stores.merges import MergeStore
        store = MergeStore(db_path)
        assert merged["id"] not in store.part_ids()

    def test_nothing_is_deleted(self, client, recordist, record, parts):
        """The whole reason both copies are kept: a merge stays reversible."""
        record()
        for part in parts:
            got = client.get(f"/api/captures/{part['id']}", headers=recordist.headers)
            assert got.status_code == 200
