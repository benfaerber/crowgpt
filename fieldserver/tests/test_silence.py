"""Recordings where the crows said nothing.

Silence is the denominator. The corpus can already say what was happening when a
crow called; without confirmed-silent recordings it can never say how often that
same thing happened and the crow said nothing — and until it can, "crows alarm at
dogs" is a count of the times somebody pressed record, not a finding.

Silence only counts as evidence when it is recorded *as* silence. An unreviewed
capture and a listened-to-and-genuinely-quiet one are identical from outside, so
the difference has to be written down.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    """A kept capture with uploaded audio, so a label can be hung on it."""
    made = client.post("/api/captures", json={"client_uuid": "cap-1", "keep": True},
                       headers=recordist.headers).get_json()
    media = client.post(f"/api/captures/{made['id']}/media",
                        json={"client_uuid": "med-1"},
                        headers=recordist.headers).get_json()
    client.put(f"/api/media/{media['id']}", data=b"xyz",
               headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
    return made


@pytest.fixture
def confirm(client, recordist, capture):
    def _confirm(silent=True):
        return client.patch(f"/api/captures/{capture['id']}",
                            json={"silent": silent}, headers=recordist.headers)
    return _confirm


@pytest.fixture
def tag(client, recordist, capture):
    def _tag(**body):
        return client.post(f"/api/captures/{capture['id']}/context",
                           json={"key": "human_gives_food", **body},
                           headers=recordist.headers)
    return _tag


class TestConfirmingSilence:

    def test_a_recording_can_be_marked_as_holding_no_calls(self, confirm):
        assert confirm().get_json()["silent_confirmed_at"] is not None

    def test_unreviewed_is_not_the_same_as_silent(self, capture):
        # The distinction the whole feature rests on. Nothing else in the schema
        # tells "nobody has checked" from "someone checked and there was nothing".
        assert capture["silent_confirmed_at"] is None

    def test_the_mark_can_be_taken_back(self, confirm):
        confirm()
        assert confirm(silent=False).get_json()["silent_confirmed_at"] is None


class TestALabelContradictsIt:

    def test_labelling_a_call_clears_the_silence_mark(
            self, client, recordist, capture, confirm):
        confirm()
        client.post(f"/api/captures/{capture['id']}/labels",
                    json={"call_type": "alarm call", "start_sec": 1, "end_sec": 2,
                          "client_uuid": "lab-1"},
                    headers=recordist.headers)
        after = client.get("/api/captures", headers=recordist.headers).get_json()[0]
        assert after["silent_confirmed_at"] is None

    def test_the_label_is_accepted_rather_than_refused(
            self, client, recordist, capture, confirm):
        # Finding a call in something you thought was silent is a correction,
        # not an error. Nobody should have to undo a checkbox to record it.
        confirm()
        response = client.post(f"/api/captures/{capture['id']}/labels",
                               json={"call_type": "alarm call", "start_sec": 1,
                                     "end_sec": 2, "client_uuid": "lab-1"},
                               headers=recordist.headers)
        assert response.status_code == 201


class TestCaptureLevelContext:
    """The one honest exception to 'context hangs off a call'."""

    def test_a_silent_capture_can_be_tagged_without_a_label(self, confirm, tag):
        confirm()
        assert tag(client_uuid="ctx-1").status_code == 201

    def test_this_is_what_records_peanuts_down_and_nobody_speaking(
            self, client, recordist, capture, confirm):
        confirm()
        # `several_birds` used to be one of these and was retired when group
        # composition arrived — a head count says the same thing and says how
        # many. The scene is unchanged: peanuts down, crows there, nobody
        # calling.
        for key in ("human_gives_food", "group_gathers", "crows_still"):
            client.post(f"/api/captures/{capture['id']}/context",
                        json={"key": key, "client_uuid": f"ctx-{key}"},
                        headers=recordist.headers)
        rows = client.get(f"/api/captures/{capture['id']}/context",
                          headers=recordist.headers).get_json()
        assert {r["key"] for r in rows} == {
            "human_gives_food", "group_gathers", "crows_still"}
        assert all(r["label_id"] is None for r in rows)

    def test_an_unreviewed_capture_still_needs_a_label(self, tag):
        # Otherwise this becomes a back door to capture-wide tagging, which is
        # what would report that crows sing at dogs.
        assert tag(client_uuid="ctx-1").status_code == 400

    def test_a_capture_with_calls_still_needs_a_label(
            self, client, recordist, capture, confirm, tag):
        confirm()
        client.post(f"/api/captures/{capture['id']}/labels",
                    json={"call_type": "alarm call", "start_sec": 1, "end_sec": 2,
                          "client_uuid": "lab-1"}, headers=recordist.headers)
        # The label cleared the silence mark, so the exception no longer applies.
        assert tag(client_uuid="ctx-1").status_code == 400


class TestItDoesNotPolluteTheMatrix:

    def test_capture_level_context_never_pairs_with_a_call(
            self, client, operator, recordist, capture, confirm):
        confirm()
        client.post(f"/api/captures/{capture['id']}/context",
                    json={"key": "human_gives_food", "client_uuid": "ctx-1"},
                    headers=recordist.headers)
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        # No call to pair with, so no pair. Inventing one would be exactly the
        # confusion the label_id rule exists to prevent.
        assert matrix["pairs"] == []

    def test_it_arrives_as_the_denominator_instead(
            self, client, operator, recordist, capture, confirm):
        confirm()
        client.post(f"/api/captures/{capture['id']}/context",
                    json={"key": "human_gives_food", "client_uuid": "ctx-1"},
                    headers=recordist.headers)
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        assert matrix["silent_captures"] == 1
        assert matrix["silent_contexts"] == [{"key": "human_gives_food", "captures": 1}]

    def test_the_context_totals_count_witnessed_calls_only(
            self, client, operator, recordist, capture, confirm):
        confirm()
        client.post(f"/api/captures/{capture['id']}/context",
                    json={"key": "human_gives_food", "client_uuid": "ctx-1"},
                    headers=recordist.headers)
        matrix = client.get("/api/fleet/semantics", headers=operator.headers).get_json()
        assert matrix["contexts"] == []
