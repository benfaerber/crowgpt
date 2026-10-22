"""How many birds were there, and how many were young.

Not recoverable from audio: a fledgling begging among five birds and one adult
calling alone are different recordings, and nothing in a WAV says which.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    def _make(**body):
        return client.post("/api/captures", json={"client_uuid": "cap-1", **body},
                           headers=recordist.headers)
    return _make


class TestCounting:

    def test_a_family_group_is_recorded_as_seen(self, capture):
        made = capture(adult_count=1, juvenile_count=2).get_json()
        assert (made["adult_count"], made["juvenile_count"]) == (1, 2)

    def test_birds_of_unknown_age_get_their_own_bucket(self, capture):
        # The reason there are three counters. "3 crows on 1 branch" states a
        # number and no ages, and adults/juveniles alone could only hold that by
        # inventing one.
        made = capture(unaged_count=3).get_json()
        assert made["unaged_count"] == 3
        assert made["adult_count"] is None

    def test_not_counting_is_different_from_counting_zero(self, capture):
        # Zero adults is a real observation about a group of fledglings; not
        # counting is the absence of one, and they must not collapse.
        made = capture(adult_count=0, juvenile_count=2).get_json()
        assert made["adult_count"] == 0
        assert made["unaged_count"] is None

    def test_saying_nothing_leaves_all_three_unset(self, capture):
        made = capture().get_json()
        assert (made["adult_count"], made["juvenile_count"], made["unaged_count"]) \
            == (None, None, None)

    def test_counts_can_be_added_afterwards(self, client, recordist, capture):
        # The realistic case: written up at the desk from a field note.
        made = capture().get_json()
        patched = client.patch(f"/api/captures/{made['id']}",
                               json={"adult_count": 1, "juvenile_count": 2},
                               headers=recordist.headers)
        assert patched.get_json()["juvenile_count"] == 2


class TestItRefusesNonsense:

    def test_a_negative_count_is_refused(self, capture):
        assert capture(adult_count=-1).status_code == 400

    def test_a_word_is_refused(self, capture):
        # "several" cannot be added up, and adding up is the entire point.
        assert capture(unaged_count="several").status_code == 400

    def test_a_fraction_is_refused(self, capture):
        assert capture(adult_count=1.5).status_code == 400

    def test_a_boolean_is_refused(self, capture):
        # Python would otherwise take True as 1 and record one adult because
        # something upstream sent a checkbox.
        assert capture(adult_count=True).status_code == 400

    def test_a_bad_count_cannot_sneak_in_through_the_edit_path(
            self, client, recordist, capture):
        made = capture().get_json()
        assert client.patch(f"/api/captures/{made['id']}",
                            json={"adult_count": -2},
                            headers=recordist.headers).status_code == 400
