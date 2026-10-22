"""The tall-trees layer: published file in, GeoJSON out, 404 when absent."""

import importlib.util
import json
from pathlib import Path

import pytest

PUBLISH_PY = Path(__file__).resolve().parents[1] / "tools" / "publish_trees.py"
spec = importlib.util.spec_from_file_location("publish_trees", PUBLISH_PY)
publish_trees = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_trees)
validate = publish_trees.validate


def geojson(n=3):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [-111.9, 40.76]},
         "properties": {"h": 20 + i, "area_m2": 500}} for i in range(n)]}


class TestApi:
    def test_404_until_published(self, client, enroll):
        device = enroll(contributor_name="Recordist")
        assert client.get("/api/trees",
                          headers=device.headers).status_code == 404

    def test_needs_auth(self, client):
        assert client.get("/api/trees").status_code == 401

    def test_serves_published_layer(self, client, enroll, db_path):
        (db_path.parent / "trees.geojson").write_text(json.dumps(geojson()))
        device = enroll(contributor_name="Recordist")
        response = client.get("/api/trees", headers=device.headers)
        assert response.status_code == 200
        body = response.get_json(force=True)
        assert len(body["features"]) == 3
        assert body["features"][0]["properties"]["h"] == 20


class TestValidate:
    def test_accepts_the_shape(self, tmp_path):
        path = tmp_path / "t.geojson"
        path.write_text(json.dumps(geojson()))
        assert validate(path) == 3

    def test_refuses_missing_height(self, tmp_path):
        bad = geojson()
        del bad["features"][0]["properties"]["h"]
        path = tmp_path / "t.geojson"
        path.write_text(json.dumps(bad))
        with pytest.raises(SystemExit, match="integer `h`"):
            validate(path)
