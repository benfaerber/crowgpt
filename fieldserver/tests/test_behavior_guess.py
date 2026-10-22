"""What the recordist thinks was going on.

Separate from labels, context and observations on purpose. Those record what a
human *witnessed*; this records what they *concluded*. A corpus that cannot tell
the two apart is one where every finding is already assumed somewhere in the
data — which is the failure the whole schema is arranged to avoid.

Its value is the opposite of ground truth: read a season of guesses and the ones
that keep recurring are the hypotheses worth designing a real test for.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    return client.post("/api/captures", json={"client_uuid": "cap-1"},
                       headers=recordist.headers).get_json()


class TestRecordingAGuess:

    def test_a_guess_rides_along_with_the_capture(self, client, recordist):
        made = client.post("/api/captures", json={
            "client_uuid": "cap-2",
            "behavior_guess": "I guess they caw at a group of teenagers",
        }, headers=recordist.headers).get_json()
        assert made["behavior_guess"] == "I guess they caw at a group of teenagers"

    def test_it_is_free_text_and_stays_that_way(self, client, recordist):
        # No vocabulary, no validation. A hypothesis you have to phrase in
        # preset terms is one you have already narrowed to what you expected.
        odd = "no idea — maybe the recycling truck, maybe the hawk from Tuesday?"
        made = client.post("/api/captures",
                           json={"client_uuid": "cap-3", "behavior_guess": odd},
                           headers=recordist.headers).get_json()
        assert made["behavior_guess"] == odd

    def test_it_can_be_written_later(self, client, recordist, capture):
        # The realistic case: the guess arrives on the walk home, not at the
        # moment of recording.
        patched = client.patch(f"/api/captures/{capture['id']}",
                               json={"behavior_guess": "mobbing the neighbour's cat"},
                               headers=recordist.headers)
        assert patched.get_json()["behavior_guess"] == "mobbing the neighbour's cat"

    def test_it_can_be_revised(self, client, recordist, capture):
        for guess in ("teenagers", "actually the cat"):
            client.patch(f"/api/captures/{capture['id']}",
                         json={"behavior_guess": guess}, headers=recordist.headers)
        current = client.get("/api/captures", headers=recordist.headers).get_json()[0]
        assert current["behavior_guess"] == "actually the cat"

    def test_no_guess_is_null_not_empty(self, capture):
        assert capture["behavior_guess"] is None

    def test_whitespace_is_not_a_guess(self, client, recordist):
        made = client.post("/api/captures",
                           json={"client_uuid": "cap-4", "behavior_guess": "   "},
                           headers=recordist.headers).get_json()
        assert made["behavior_guess"] is None


class TestItIsNotGroundTruth:

    def test_a_guess_creates_no_context(self, client, recordist, capture):
        client.patch(f"/api/captures/{capture['id']}",
                     json={"behavior_guess": "alarming at a dog"},
                     headers=recordist.headers)
        context = client.get(f"/api/captures/{capture['id']}/context",
                             headers=recordist.headers).get_json()
        assert context == []

    def test_it_never_reaches_the_calls_by_context_matrix(
            self, client, operator, recordist, capture):
        # The failure this arrangement exists to prevent: a guess that becomes
        # a tag becomes a co-occurrence becomes a finding, none of which anybody
        # observed.
        client.patch(f"/api/captures/{capture['id']}",
                     json={"behavior_guess": "raptor_overhead", "keep": True},
                     headers=recordist.headers)
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        assert matrix["pairs"] == []
        assert matrix["contexts"] == []

    def test_it_creates_no_labels(self, client, recordist, capture):
        client.patch(f"/api/captures/{capture['id']}",
                     json={"behavior_guess": "alarm call at teenagers"},
                     headers=recordist.headers)
        labels = client.get(f"/api/captures/{capture['id']}/labels",
                            headers=recordist.headers).get_json()
        assert labels == []
