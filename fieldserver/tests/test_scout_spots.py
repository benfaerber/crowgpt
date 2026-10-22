"""'Best spots inside my circle' — the query the persisted score grids exist for."""

import numpy as np
import pytest


@pytest.fixture
def grid(db_path):
    """A 6x6 grid around (40.62, -111.81) with one hot cell and one runner-up
    far enough away to survive separation."""
    lats = 40.60 + np.arange(6) * 0.005
    lons = -111.83 + np.arange(6) * 0.006
    score = np.full((6, 6), 0.1)
    score[4, 4] = 0.9
    score[1, 1] = 0.6
    sig = np.zeros((6, 6))
    sig[4, 4] = 1.0
    grid_dir = db_path.parent / "scout_grid"
    grid_dir.mkdir()
    np.savez_compressed(
        grid_dir / "testbox.npz",
        lats=lats, lons=lons, score=score, sig_trees=sig,
        green_lat=np.array([40.6205]), green_lon=np.array([-111.8055]),
        green_name=np.array(["Hot Cell Park"]))
    return grid_dir


class TestScoutSpots:
    def test_needs_a_device_token(self, client, grid):
        response = client.get("/api/scout/spots?lat=40.62&lon=-111.81")
        assert response.status_code == 401

    def test_best_cell_leads_and_gets_its_park(self, client, recordist, grid):
        payload = client.get(
            "/api/scout/spots?lat=40.62&lon=-111.806&radius_m=3000",
            headers=recordist.headers).get_json()
        top = payload["spots"][0]
        assert top["rank"] == 1
        assert top["score"] == 0.9
        assert top["near"] == "Hot Cell Park"
        assert top["signals"]["trees"] == 1.0
        assert top["region"] == "testbox"

    def test_separation_keeps_spots_apart(self, client, recordist, grid):
        spots = client.get(
            "/api/scout/spots?lat=40.615&lon=-111.812&radius_m=4000&count=5",
            headers=recordist.headers).get_json()["spots"]
        assert len(spots) >= 2
        a, b = spots[0], spots[1]
        meters = np.hypot((a["lat"] - b["lat"]) * 110540,
                          (a["lon"] - b["lon"]) * 84500)
        assert meters >= 700

    def test_a_circle_in_the_ocean_is_a_note_not_an_error(
            self, client, recordist, grid):
        payload = client.get(
            "/api/scout/spots?lat=0&lon=0",
            headers=recordist.headers).get_json()
        assert payload["spots"] == []
        assert "outside" in payload["note"]

    def test_no_grids_published_is_the_same_note(self, client, recordist):
        payload = client.get(
            "/api/scout/spots?lat=40.62&lon=-111.81",
            headers=recordist.headers).get_json()
        assert payload["spots"] == []

    def test_garbage_coordinates_are_refused(self, client, recordist, grid):
        response = client.get("/api/scout/spots?lat=abc&lon=1",
                              headers=recordist.headers)
        assert response.status_code == 400
