"""What the recordist was to these crows when the recording was made.

The variable that flips the meaning of everything else on the tape. A crow that
knows you feeds it behaves nothing like one meeting you for the first time —
same bird, same street, same call type, different recording. Without this the
corpus holds two populations filed as one, and no amount of later analysis can
separate them.

Per capture, not per contributor: the same person is a stranger in a new
territory and a feeder on their own block on the same morning.
"""

import pytest

from fieldserver.stores.config_store import SEED_OBSERVER_ROLES


@pytest.fixture
def capture(client, recordist):
    def _make(**body):
        response = client.post("/api/captures",
                               json={"client_uuid": "cap-1", **body},
                               headers=recordist.headers)
        return response
    return _make


class TestVocabulary:

    def test_the_roles_are_served_to_the_fleet(self, client):
        config = client.get("/api/config?locale=en").get_json()
        assert [r["key"] for r in config["observer_roles"]] == SEED_OBSERVER_ROLES

    def test_they_are_ordered_by_how_much_history_the_birds_have(self, client):
        # Least to most, because that is the axis the behaviour moves along —
        # a picker in a random order makes the reader re-derive that every time.
        keys = [r["key"] for r in client.get("/api/config").get_json()["observer_roles"]]
        assert keys.index("stranger") < keys.index("feeder") < keys.index("handler")

    def test_each_one_reads_as_something_a_person_could_answer(self, client):
        roles = client.get("/api/config?locale=en").get_json()["observer_roles"]
        by_key = {r["key"]: r["text"] for r in roles}
        assert by_key["stranger"] == "Stranger to them"
        assert by_key["feeding_now"] == "Feeding them now"

    def test_it_is_translated_like_every_other_vocabulary(self, client):
        roles = client.get("/api/config?locale=de").get_json()["observer_roles"]
        assert {r["key"]: r["text"] for r in roles}["stranger"] == "Fremd"


class TestOnACapture:

    def test_a_capture_records_what_the_recordist_was(self, capture):
        assert capture(observer_role="feeding_now").get_json()["observer_role"] \
            == "feeding_now"

    def test_saying_nothing_is_not_the_same_as_saying_stranger(self, capture):
        # Null means nobody answered. Defaulting to "stranger" would invent
        # ground truth, and this field exists to be trusted.
        assert capture().get_json()["observer_role"] is None

    def test_a_role_outside_the_vocabulary_is_refused(self, capture):
        # Free text cannot be grouped, and grouping is the whole point.
        assert capture(observer_role="crow whisperer").status_code == 400

    def test_it_can_be_set_afterwards(self, client, recordist, capture):
        # The realistic case: remembered at the desk, like a family tag.
        created = capture().get_json()
        patched = client.patch(f"/api/captures/{created['id']}",
                               json={"observer_role": "feeder"},
                               headers=recordist.headers)
        assert patched.get_json()["observer_role"] == "feeder"

    def test_a_bad_role_cannot_sneak_in_through_the_edit_path(
            self, client, recordist, capture):
        created = capture().get_json()
        response = client.patch(f"/api/captures/{created['id']}",
                                json={"observer_role": "nonsense"},
                                headers=recordist.headers)
        assert response.status_code == 400

    def test_the_same_person_can_be_different_things_on_different_captures(
            self, client, recordist):
        # The reason this is per capture. A contributor-level field would have
        # to pick one of these and be wrong about the other.
        for uuid, role in (("home-block", "feeder"), ("new-park", "stranger")):
            client.post("/api/captures", json={"client_uuid": uuid, "observer_role": role},
                        headers=recordist.headers)
        roles = {c["client_uuid"]: c["observer_role"]
                 for c in client.get("/api/captures", headers=recordist.headers).get_json()}
        assert roles == {"home-block": "feeder", "new-park": "stranger"}
