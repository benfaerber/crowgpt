"""Something seen near a recording but not during it.

The motivating case: a crow gives an alarm bout, and five minutes later a block
away two hawks come into view. Worth recording — it is the start of a real
hypothesis — but it is not ground truth about what the crow was reacting to, and
the difference has to survive being written down.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    return client.post("/api/captures", json={"client_uuid": "cap-1"},
                       headers=recordist.headers).get_json()


@pytest.fixture
def see(client, recordist, capture):
    def _see(**body):
        return client.post(f"/api/captures/{capture['id']}/sightings",
                           json={"key": "raptor_overhead", "offset_sec": 300, **body},
                           headers=recordist.headers)
    return _see


class TestRecordingOne:

    def test_a_hawk_five_minutes_later_is_recordable(self, see):
        row = see(distance_m=120, notes="2 hawks, from the apartment window").get_json()
        assert row["key"] == "raptor_overhead"
        assert row["offset_sec"] == 300
        assert row["distance_m"] == 120

    def test_before_the_recording_is_a_negative_offset(self, see):
        # Signed on purpose. "A hawk went over just before he started" is a
        # different claim from "a hawk appeared afterwards", and it is the more
        # interesting one.
        assert see(offset_sec=-90).get_json()["offset_sec"] == -90

    def test_distance_is_optional_because_it_is_always_a_guess(self, see):
        # "About a block" is a real answer. Demanding metres would only produce
        # invented precision.
        assert see(distance_m=None).get_json()["distance_m"] is None

    def test_it_uses_the_same_vocabulary_as_context(self, see):
        # The whole point: it is what eventually lets "how often does an alarm
        # bout precede a raptor appearing" be answered from data.
        assert see(key="dog_visible").status_code == 201
        assert see(key="a hawk I think", client_uuid="x").status_code == 400

    def test_a_replayed_sync_does_not_duplicate_it(self, see):
        first = see(client_uuid="s-1").get_json()
        again = see(client_uuid="s-1").get_json()
        assert first["id"] == again["id"]


class TestTheOffsetIsMandatory:
    """A sighting with no time is a context event with the honesty removed."""

    def test_it_is_refused_without_one(self, client, recordist, capture):
        response = client.post(f"/api/captures/{capture['id']}/sightings",
                               json={"key": "raptor_overhead"},
                               headers=recordist.headers)
        assert response.status_code == 400

    def test_zero_is_allowed_and_is_not_missing(self, see):
        # "As I hit stop" is a real, precise answer — distinct from not saying.
        assert see(offset_sec=0).get_json()["offset_sec"] == 0

    def test_nonsense_is_refused_rather_than_stored_as_null(self, see):
        assert see(offset_sec="five minutes").status_code == 400


class TestItStaysOutOfTheGroundTruth:
    """The reason this is a separate table rather than a flag."""

    def test_a_sighting_is_not_a_context_event(self, client, recordist, capture, see):
        see(client_uuid="s-1")
        context = client.get(f"/api/captures/{capture['id']}/context",
                             headers=recordist.headers).get_json()
        assert context == []

    def test_it_does_not_reach_the_calls_by_context_matrix(
            self, client, operator, recordist, capture, see):
        # The failure this design exists to prevent: infer the alarm from the
        # hawk, tag the hawk, and the matrix reports alarm calls co-occur with
        # hawks — true by construction, and indistinguishable later from a
        # result that was actually earned.
        see(client_uuid="s-1")
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        assert "raptor_overhead" not in str(matrix)

    def test_it_is_still_readable_where_it_belongs(self, client, recordist, capture, see):
        see(client_uuid="s-1")
        rows = client.get(f"/api/captures/{capture['id']}/sightings",
                          headers=recordist.headers).get_json()
        assert len(rows) == 1

    def test_they_come_back_in_time_order(self, see, client, recordist, capture):
        for offset in (300, -90, 0):
            see(offset_sec=offset, client_uuid=f"s{offset}")
        rows = client.get(f"/api/captures/{capture['id']}/sightings",
                          headers=recordist.headers).get_json()
        assert [r["offset_sec"] for r in rows] == [-90, 0, 300]


class TestOwnership:

    def test_a_stranger_cannot_read_them(self, client, stranger, capture, see):
        see(client_uuid="s-1")
        response = client.get(f"/api/captures/{capture['id']}/sightings",
                              headers=stranger.headers)
        assert response.status_code == 403

    def test_a_stranger_cannot_retract_one(self, client, stranger, see):
        row = see(client_uuid="s-1").get_json()
        assert client.delete(f"/api/sightings/{row['id']}",
                             headers=stranger.headers).status_code == 403

    def test_the_author_can_retract_one(self, client, recordist, see):
        row = see(client_uuid="s-1").get_json()
        assert client.delete(f"/api/sightings/{row['id']}",
                             headers=recordist.headers).status_code == 204

    def test_deleting_the_capture_takes_its_sightings(self, db_path, capture, see):
        # ON DELETE CASCADE. A sighting is about a recording; once the recording
        # is gone its offset measures from nothing.
        #
        # Exercised at the store, because the API has no capture-delete route —
        # going through the client would assert against a 404 and prove nothing.
        import sqlite3
        row = see(client_uuid="s-1").get_json()
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM captures WHERE id = ?", (capture["id"],))
        with sqlite3.connect(db_path) as conn:
            left = conn.execute("SELECT COUNT(*) FROM sightings WHERE id = ?",
                                (row["id"],)).fetchone()[0]
        assert left == 0
