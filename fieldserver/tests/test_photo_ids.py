"""Photo ID: the upload queue, its API surface, and the worker's one step.

The classifier itself needs torch and a trained model, so these stop at the
seam it works across: rows queued by the API, claimed and completed the way
photo_worker.py does, with a stand-in where the classifier would be.
"""

import io
import sys
from pathlib import Path

import pytest

from fieldserver.stores.photo_ids import MAX_BYTES, PhotoIdStore

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))
import photo_worker  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0 not really a photo"
RESULT = {
    "ranking": [{"slug": "american-crow", "common_name": "American Crow",
                 "scientific_name": "Corvus brachyrhynchos", "probability": 0.9}],
    "bird_box": None, "used_location": False, "latitude": None, "longitude": None,
    "width": 64, "height": 48,
}


@pytest.fixture
def store(db_path, tmp_path):
    return PhotoIdStore(db_path, tmp_path / "photo-id")


class TestStore:
    def test_request_stores_the_photo_and_queues(self, store):
        row = store.request(JPEG, ".JPG", original_name="crow.JPG")
        assert row["state"] == "queued"
        assert row["storage_ref"].endswith(".jpg")
        assert row["result"] is None
        assert store.path(row).read_bytes() == JPEG

    def test_request_refuses_a_format_the_classifier_cannot_open(self, store):
        with pytest.raises(ValueError, match="photo must be one of"):
            store.request(JPEG, "heic")

    def test_request_refuses_empty_and_oversized(self, store):
        with pytest.raises(ValueError, match="empty"):
            store.request(b"", "jpg")
        with pytest.raises(ValueError, match="over"):
            store.request(b"x" * (MAX_BYTES + 1), "jpg")

    def test_request_wants_both_coordinates_or_neither(self, store):
        with pytest.raises(ValueError, match="both latitude and longitude"):
            store.request(JPEG, "jpg", latitude=40.7)
        with pytest.raises(ValueError, match="out of range"):
            store.request(JPEG, "jpg", latitude=140.7, longitude=10)

    def test_claim_complete_lifecycle(self, store):
        row = store.request(JPEG, "jpg", latitude=40.76, longitude=-111.89)
        claimed = store.claim_next()
        assert claimed["id"] == row["id"]
        assert claimed["state"] == "running"
        assert store.claim_next() is None

        done = store.complete(row["id"], RESULT)
        assert done["state"] == "done"
        assert done["result"] == RESULT

    def test_fail_is_terminal(self, store):
        row = store.request(JPEG, "jpg")
        store.claim_next()
        failed = store.fail(row["id"], "no model")
        assert failed["state"] == "failed"
        assert failed["error"] == "no model"
        assert store.claim_next() is None

    def test_reclaim_requeues_then_abandons(self, store):
        row = store.request(JPEG, "jpg")
        store.claim_next()
        assert store.reclaim_running(max_attempts=2) == (1, 0)
        store.claim_next()
        assert store.reclaim_running(max_attempts=2) == (0, 1)
        assert store.get(row["id"])["state"] == "failed"

    def test_recent_is_newest_first(self, store):
        first = store.request(JPEG, "jpg")
        second = store.request(JPEG, "png")
        assert [r["id"] for r in store.recent()] == [second["id"], first["id"]]

    def test_forget_clears_rows_and_photos(self, store):
        row = store.request(JPEG, "jpg")
        assert store.forget() == 1
        assert store.recent() == []
        assert not store.path(row).exists()


class StubIdentifier:
    def __init__(self, error=None):
        self.error = error
        self.seen = None

    def identify(self, path, latitude, longitude):
        self.seen = (path, latitude, longitude)
        if self.error:
            raise self.error

        class Result:
            @staticmethod
            def to_dict():
                return RESULT

        return Result()


class TestWorker:
    def test_process_completes_the_row_with_the_ranking(self, store):
        store.request(JPEG, "jpg", latitude=40.76, longitude=-111.89)
        job = store.claim_next()
        identifier = StubIdentifier()
        done = photo_worker.process(job, store, identifier)
        assert done["state"] == "done"
        assert done["result"]["ranking"][0]["slug"] == "american-crow"
        assert identifier.seen == (store.path(job), 40.76, -111.89)

    def test_process_records_why_it_failed(self, store):
        store.request(JPEG, "jpg")
        job = store.claim_next()
        failed = photo_worker.process(job, store, StubIdentifier(RuntimeError("No photo model")))
        assert failed["state"] == "failed"
        assert failed["error"] == "RuntimeError: No photo model"


def upload(client, headers, name="crow.jpg", **form):
    data = {"photo": (io.BytesIO(JPEG), name), **form}
    return client.post("/api/photo-ids", data=data, headers=headers,
                       content_type="multipart/form-data")


class TestApi:
    def test_needs_an_operator(self, client, enroll):
        contributor = enroll(contributor_name="Recordist")
        assert client.get("/api/photo-ids", headers=contributor.headers).status_code == 403
        assert upload(client, contributor.headers).status_code == 403

    def test_upload_list_and_fetch_the_photo(self, client, operator):
        created = upload(client, operator.headers, latitude="40.76", longitude="-111.89")
        assert created.status_code == 201
        row = created.get_json()
        assert row["state"] == "queued"
        assert row["original_name"] == "crow.jpg"
        assert (row["latitude"], row["longitude"]) == (40.76, -111.89)

        listed = client.get("/api/photo-ids", headers=operator.headers).get_json()
        assert [r["id"] for r in listed["identifications"]] == [row["id"]]

        photo = client.get(f"/api/photo-ids/{row['id']}/photo", headers=operator.headers)
        assert photo.status_code == 200
        assert photo.data == JPEG

    def test_upload_refuses_what_the_store_refuses(self, client, operator):
        assert upload(client, operator.headers, name="crow.heic").status_code == 400
        assert upload(client, operator.headers, latitude="north").status_code == 400
        assert upload(client, operator.headers, latitude="40.7").status_code == 400
        missing = client.post("/api/photo-ids", data={}, headers=operator.headers,
                              content_type="multipart/form-data")
        assert missing.status_code == 400

    def test_forget(self, client, operator):
        upload(client, operator.headers)
        forgotten = client.delete("/api/photo-ids", headers=operator.headers)
        assert forgotten.get_json() == {"forgotten": 1}
        assert client.get("/api/photo-ids", headers=operator.headers).get_json() == {
            "identifications": []}

    def test_unknown_photo_is_404(self, client, operator):
        assert client.get("/api/photo-ids/999/photo", headers=operator.headers).status_code == 404
