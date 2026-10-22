"""How far away the bird was.

The variable that confounds every comparison between recordists. A hooded crow
in Berlin that tolerates a two-metre approach and an American Crow thirty metres
up a rooftop produce audio differing in signal-to-noise and spectral tilt before
either bird has said anything different — so without this, a species difference
and a distance difference are the same number.
"""

import pytest

from fieldserver.stores.captures import DISTANCE_BANDS


@pytest.fixture
def capture(client, recordist):
    def _make(**body):
        return client.post("/api/captures", json={"client_uuid": "cap-1", **body},
                           headers=recordist.headers)
    return _make


class TestRecordingIt:

    def test_it_rides_along_with_the_capture(self, capture):
        assert capture(distance_band="20_50m").get_json()["distance_band"] == "20_50m"

    def test_every_band_is_accepted(self, client, recordist):
        for i, band in enumerate(DISTANCE_BANDS):
            made = client.post("/api/captures",
                               json={"client_uuid": f"cap-{i}", "distance_band": band},
                               headers=recordist.headers).get_json()
            assert made["distance_band"] == band

    def test_an_invented_band_is_refused(self, capture):
        # Free text here would defeat the point: the whole value is being able
        # to group by it, and "quite close" does not group with "under_5m".
        assert capture(distance_band="quite close").status_code == 400

    def test_metres_are_refused_too(self, capture):
        # A number would invite precision nobody has looking at a bird.
        assert capture(distance_band="27").status_code == 400

    def test_not_saying_is_allowed(self, capture):
        # Undefined means nobody said, which is honest and common — this is a
        # tap on the way past, not a required field.
        assert capture().get_json()["distance_band"] is None

    def test_it_can_be_set_afterwards(self, client, recordist, capture):
        made = capture().get_json()
        patched = client.patch(f"/api/captures/{made['id']}",
                               json={"distance_band": "under_5m"},
                               headers=recordist.headers)
        assert patched.get_json()["distance_band"] == "under_5m"

    def test_a_bad_band_cannot_sneak_in_through_the_edit_path(
            self, client, recordist, capture):
        made = capture().get_json()
        assert client.patch(f"/api/captures/{made['id']}",
                            json={"distance_band": "far-ish"},
                            headers=recordist.headers).status_code == 400
