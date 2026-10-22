"""Whether a person started the recording, or the phone's idle-mode trigger did.

The corpus discipline is knowing what is real, and an unattended capture is a
different kind of real: nobody witnessed it, its observer role and distance
are blank on purpose, and the thing that pressed the button can be fooled by
a siren. "auto" in captures.trigger is what keeps those rows from ever being
counted as deliberate field recordings.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    def _make(**body):
        return client.post("/api/captures",
                           json={"client_uuid": "cap-trigger-1", **body},
                           headers=recordist.headers)
    return _make


class TestOnCreate:

    def test_an_idle_capture_says_the_trigger_pressed_the_button(self, capture):
        assert capture(trigger="auto").get_json()["trigger"] == "auto"

    def test_absent_means_a_person_did_and_stays_null(self, capture):
        # Null, not "manual": nobody asked the question of the old rows, and
        # null-means-nobody-said is the convention every field here follows.
        assert capture().get_json()["trigger"] is None

    def test_anything_else_is_refused(self, capture):
        # A loose value could never be filtered on, and filtering unattended
        # captures out of counts is the entire reason the column exists.
        assert capture(trigger="motion").status_code == 400


class TestImmutability:

    def test_how_a_recording_started_is_not_an_edit(self, client, recordist, capture):
        # The edit path silently ignores it, like every non-MUTABLE column:
        # how a capture began is a fact about the recording, and a client that
        # could rewrite it could launder an auto capture into a witnessed one.
        created = capture(trigger="auto").get_json()
        client.patch(f"/api/captures/{created['id']}",
                     json={"trigger": None, "name": "renamed"},
                     headers=recordist.headers)
        fetched = client.get(f"/api/captures/{created['id']}",
                             headers=recordist.headers).get_json()
        assert fetched["trigger"] == "auto"
