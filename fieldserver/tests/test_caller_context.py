"""What the calling bird did, as opposed to what everyone else did.

Capture 103 is the case this exists for: Edgar called from a roofline, four
crows flew off, he called again and stayed watching them go. `crow_departs`
plus `crows_still` records "some left, some stayed" and loses the only part
that matters — that the bird making the call was the one that stayed.

A caller who holds position while the group leaves is doing something different
from one that leaves with it. Without this the corpus cannot tell them apart,
so the question cannot be asked later however much labelling gets done.
"""

import pytest

from fieldserver.stores.config_store import SEED_CONTEXTS


@pytest.fixture
def context_keys(client, recordist):
    config = client.get("/api/config", headers=recordist.headers).get_json()
    return {c["key"]: c for c in config["contexts"]}


class TestTheVocabulary:
    def test_both_halves_are_offered(self, context_keys):
        assert "caller_stays" in context_keys
        assert "caller_leaves" in context_keys

    def test_they_sit_with_the_other_crow_tags(self, context_keys):
        assert context_keys["caller_stays"]["category"] == "crows"
        assert context_keys["caller_leaves"]["category"] == "crows"

    def test_they_read_as_something_seen(self, context_keys):
        """Not "receiver", not "listener" — those claim the bird heard it."""
        assert context_keys["caller_stays"]["text"] == "Caller stayed put"
        assert context_keys["caller_leaves"]["text"] == "Caller flew off"

    def test_the_others_tags_are_untouched(self, context_keys):
        # The existing tags were always about other birds; they just never had
        # to say so. Adding the caller half must not change what they mean.
        for key in ("crow_arrives", "crow_departs", "group_gathers"):
            assert key in context_keys


class TestTaggingCapture103sShape:
    """Edgar calls, the others leave, Edgar stays."""

    @pytest.fixture
    def label(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "c-103"},
                              headers=recordist.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"format": "wav"},
                            headers=recordist.headers).get_json()
        made = client.post(
            f"/api/captures/{capture['id']}/labels",
            json={"client_uuid": "l-1", "media_id": media["id"],
                  "species": "American Crow", "call_type": "alarm call",
                  "start_sec": 2.0, "end_sec": 3.5},
            headers=recordist.headers).get_json()
        return capture["id"], made["id"]

    def tag(self, client, recordist, capture_id, label_id, key, uuid):
        return client.post(f"/api/captures/{capture_id}/context",
                           json={"key": key, "label_id": label_id,
                                 "client_uuid": uuid},
                           headers=recordist.headers)

    def test_the_pair_composes(self, client, recordist, label):
        """Both tags on one call is the whole observation, unambiguously."""
        capture_id, label_id = label
        assert self.tag(client, recordist, capture_id, label_id,
                        "crow_departs", "x-1").status_code == 201
        assert self.tag(client, recordist, capture_id, label_id,
                        "caller_stays", "x-2").status_code == 201

        got = client.get(f"/api/captures/{capture_id}/context",
                         headers=recordist.headers).get_json()
        assert {e["key"] for e in got} == {"crow_departs", "caller_stays"}

    def test_it_hangs_off_the_call_not_the_capture(self, client, recordist, label):
        capture_id, label_id = label
        self.tag(client, recordist, capture_id, label_id, "caller_stays", "x-1")
        event = client.get(f"/api/captures/{capture_id}/context",
                           headers=recordist.headers).get_json()[0]
        assert event["label_id"] == label_id
        # It inherits the label's span, so it describes that call rather than
        # the whole recording.
        assert event["start_sec"] == 2.0

    def test_a_second_bout_can_disagree_with_the_first(self, client, recordist, label):
        """The point of per-call context: he stayed, then later he left."""
        capture_id, first = label
        media = client.get(f"/api/captures/{capture_id}/media",
                           headers=recordist.headers).get_json()[0]
        second = client.post(
            f"/api/captures/{capture_id}/labels",
            json={"client_uuid": "l-2", "media_id": media["id"],
                  "species": "American Crow", "call_type": "call",
                  "start_sec": 40.0, "end_sec": 41.0},
            headers=recordist.headers).get_json()

        self.tag(client, recordist, capture_id, first, "caller_stays", "x-1")
        self.tag(client, recordist, capture_id, second["id"], "caller_leaves", "x-2")

        got = client.get(f"/api/captures/{capture_id}/context",
                         headers=recordist.headers).get_json()
        by_label = {e["label_id"]: e["key"] for e in got}
        assert by_label[first] == "caller_stays"
        assert by_label[second["id"]] == "caller_leaves"


def test_an_existing_fleet_is_offered_the_new_tags(db_path):
    """A server seeded before these existed must publish them, not just a fresh one.

    Reconciling on startup is the mechanism, and a phone only re-fetches when
    the config version moves — so a tag added without a version bump is one
    nobody in the field ever sees.
    """
    import sqlite3

    from fieldserver.stores.config_store import ConfigStore

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM context_defs WHERE key LIKE 'caller_%'")
        before = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM config_versions").fetchone()[0]

    store = ConfigStore(db_path)
    served = {c["key"] for c in store.get_config()["contexts"]}
    assert {"caller_stays", "caller_leaves"} <= served

    with sqlite3.connect(db_path) as conn:
        after = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM config_versions").fetchone()[0]
    assert after > before, "the fleet is only told when the version moves"


class TestWhatAPersonIsDoing:
    """People tags describe behaviour, never a kind of person.

    The distinction is not only decency, though it is that. A crow cannot
    perceive somebody's housing or sobriety; it perceives noise, shouting and
    sudden movement. A tag naming a kind of person would record a judgement
    about a human in a column meant for evidence about a bird — and would not
    even be the variable doing the work.
    """

    def test_machinery_is_its_own_stimulus(self, context_keys):
        # Someone walking past is a moment; someone running a mower is an hour
        # of noise over the ground the birds are foraging on.
        assert context_keys["loud_worker"]["category"] == "people"
        assert context_keys["loud_worker"]["text"] == "Someone working with machinery"

    def test_it_is_about_the_machine_not_the_trade(self, context_keys):
        # Mowing, blowing, digging and hammering are one thing to a crow. A tag
        # per job would be four tags with three examples each.
        for absent in ("landscaper", "construction_worker", "gardener"):
            assert absent not in context_keys

    def test_shouting_is_recorded_as_behaviour(self, context_keys):
        assert context_keys["person_shouting"]["text"] == "Someone shouting or agitated"

    def test_no_tag_names_a_kind_of_person(self, context_keys):
        for absent in ("homeless", "drunk", "aggressive_person", "vagrant"):
            assert absent not in context_keys


def test_the_seed_list_and_the_translations_agree():
    """A tag with no text renders as its key on the phone."""
    from fieldserver.stores.config_store import SEED_TRANSLATIONS

    texts = SEED_TRANSLATIONS["context"]
    for key, _ in SEED_CONTEXTS:
        assert key in texts, f"{key} has no label to show"
