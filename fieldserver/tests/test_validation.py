"""Garbage in a numeric field is a 400 naming the field, not a 500 or a row.

SQLite stores whatever it is handed — "north" goes into a REAL column without
complaint — so before these checks a bad value either crashed a store's own
float() as an unexplained 500 or landed in the corpus as text pretending to
be a number.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    return client.post("/api/captures", json={"client_uuid": "val-cap"},
                       headers=recordist.headers).get_json()


@pytest.fixture
def audio(client, recordist, capture):
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"client_uuid": "val-med"},
                        headers=recordist.headers).get_json()
    client.put(f"/api/media/{media['id']}", data=b"xyz",
               headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
    return media


class TestCaptureNumbers:
    def post(self, client, recordist, **body):
        return client.post("/api/captures", json={"client_uuid": "val-x", **body},
                           headers=recordist.headers)

    def test_a_healthy_capture_still_lands(self, client, recordist):
        response = self.post(client, recordist, latitude=40.7, longitude=-111.9,
                             duration_sec=34.2, crop_start_sec=1.0,
                             crop_end_sec=30.0, app_version=344)
        assert response.status_code == 201

    @pytest.mark.parametrize("body", [
        {"crop_start_sec": "x"},
        {"duration_sec": "34 seconds"},
        {"app_version": "three"},
        {"app_version": 3.5},
        {"latitude": "north"},
        {"latitude": 91},
        {"longitude": -181},
        {"duration_sec": -1},
    ])
    def test_garbage_is_named_and_refused(self, client, recordist, body):
        response = self.post(client, recordist, **body)
        assert response.status_code == 400
        field = next(iter(body))
        assert field in response.get_data(as_text=True)

    def test_a_crop_cannot_end_before_it_starts(self, client, recordist):
        response = self.post(client, recordist, crop_start_sec=10.0,
                             crop_end_sec=2.0)
        assert response.status_code == 400

    def test_an_edit_is_held_to_the_same_rule(self, client, recordist, capture):
        response = client.patch(f"/api/captures/{capture['id']}",
                                json={"latitude": "here"},
                                headers=recordist.headers)
        assert response.status_code == 400


class TestMediaNumbers:
    def test_a_spelled_out_sample_rate_is_refused(self, client, recordist, capture):
        response = client.post(f"/api/captures/{capture['id']}/media",
                               json={"client_uuid": "val-m2",
                                     "sample_rate": "fast"},
                               headers=recordist.headers)
        assert response.status_code == 400

    def test_negative_pre_roll_is_refused(self, client, recordist, capture):
        response = client.post(f"/api/captures/{capture['id']}/media",
                               json={"client_uuid": "val-m3",
                                     "pre_roll_sec": -2},
                               headers=recordist.headers)
        assert response.status_code == 400


class TestLabelSpans:
    def label(self, client, recordist, capture, **body):
        return client.post(f"/api/captures/{capture['id']}/labels",
                           json={"client_uuid": "val-lab",
                                 "call_type": "alarm call", **body},
                           headers=recordist.headers)

    def test_a_span_that_ends_before_it_starts_is_refused(
            self, client, recordist, capture, audio):
        assert self.label(client, recordist, capture,
                          start_sec=5.0, end_sec=1.0).status_code == 400

    def test_a_text_span_is_refused(self, client, recordist, capture, audio):
        assert self.label(client, recordist, capture,
                          start_sec="early").status_code == 400

    def test_a_text_distance_is_refused(self, client, recordist, capture, audio):
        response = client.post(f"/api/captures/{capture['id']}/sightings",
                               json={"client_uuid": "val-sgt",
                                     "key": "raptor_overhead",
                                     "offset_sec": 10,
                                     "distance_m": "about a block"},
                               headers=recordist.headers)
        assert response.status_code == 400


class TestFleetPaging:
    def test_an_absurd_limit_is_served_capped_rather_than_run(
            self, client, operator):
        response = client.get("/api/fleet/captures?limit=100000000",
                              headers=operator.headers)
        assert response.status_code == 200

    def test_a_negative_limit_is_a_page_not_an_error(self, client, operator):
        response = client.get("/api/fleet/logs?limit=-5",
                              headers=operator.headers)
        assert response.status_code == 200
