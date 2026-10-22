"""The scouting layer: published file in, JSON out, 404 when absent."""

import importlib.util
import json
from pathlib import Path

import pytest

PUBLISH_PY = Path(__file__).resolve().parents[1] / "tools" / "publish_scout.py"
spec = importlib.util.spec_from_file_location("publish_scout", PUBLISH_PY)
publish_scout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_scout)
validate = publish_scout.validate


def layer():
    return {"targets": [
        {"rank": 1, "lat": 40.67, "lon": -111.94, "score": 0.58,
         "near": "Somewhere Park", "signals": {"inat": 1.0}},
    ], "owls": [{"lat": 40.77, "lon": -111.85}]}


class TestApi:
    def test_404_until_published(self, client, enroll):
        device = enroll(contributor_name="Recordist")
        assert client.get("/api/scout",
                          headers=device.headers).status_code == 404

    def test_needs_auth(self, client):
        assert client.get("/api/scout").status_code == 401

    def test_serves_published_layer(self, client, enroll, db_path):
        (db_path.parent / "scout.json").write_text(json.dumps(layer()))
        device = enroll(contributor_name="Recordist")
        response = client.get("/api/scout", headers=device.headers)
        assert response.status_code == 200
        body = response.get_json(force=True)
        assert body["targets"][0]["rank"] == 1
        assert len(body["owls"]) == 1


class TestValidate:
    def test_accepts_the_shape(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text(json.dumps(layer()))
        assert validate(path) == (1, 1)

    def test_refuses_scoreless_targets(self, tmp_path):
        bad = layer()
        del bad["targets"][0]["score"]
        path = tmp_path / "s.json"
        path.write_text(json.dumps(bad))
        with pytest.raises(SystemExit, match="score"):
            validate(path)


class TestVisits:
    def visit(self, uuid="v-1"):
        return {"client_uuid": uuid, "kind": "tree", "latitude": 40.67,
                "longitude": -111.94, "outcome": "nothing",
                "visited_at": "2026-08-20T13:00:00Z"}

    def test_push_is_idempotent(self, client, enroll):
        device = enroll(contributor_name="Recordist")
        first = client.post("/api/scout/visits", json=self.visit(),
                            headers=device.headers)
        again = client.post("/api/scout/visits", json=self.visit(),
                            headers=device.headers)
        assert first.status_code == again.status_code == 201
        assert first.get_json()["id"] == again.get_json()["id"]
        listed = client.get("/api/scout/visits", headers=device.headers)
        assert len(listed.get_json()) == 1
        assert listed.get_json()[0]["outcome"] == "nothing"

    def test_refuses_unknown_outcome(self, client, enroll):
        device = enroll(contributor_name="Recordist")
        bad = {**self.visit(), "outcome": "maybe"}
        assert client.post("/api/scout/visits", json=bad,
                           headers=device.headers).status_code == 400

    def test_records_who_and_when(self, client, enroll):
        device = enroll(contributor_name="Recordist")
        row = client.post("/api/scout/visits", json=self.visit("v-2"),
                          headers=device.headers).get_json()
        assert row["contributor_id"] == device.contributor["id"]
        assert row["visited_at"] == "2026-08-20T13:00:00Z"
        assert row["created_at"]
