"""The promo's Scan page: a stranger's upload, its queue, and what is kept.

The workers need BirdNET and torch, so these stop at the seam: rows queued by
the public route, claimed and finished the way the workers do, and the photo
worker's one step with a stand-in classifier. What matters most here is what
does NOT survive: the file after its job, the row after its hour.
"""

import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fieldserver.stores.scans import ALIVE_WITHIN, KEEP, MAX_WAITING, ScanStore, kind_of

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))
import photo_worker  # noqa: E402

BYTES = b"not really media"
RESULT = {"ranking": [{"slug": "american-crow", "probability": 0.9}]}


@pytest.fixture
def store(db_path, tmp_path):
    return ScanStore(db_path, tmp_path / "demo-scans")


def queued(store, name="crow.jpg", content=BYTES, **where):
    kind, ref, path = store.allocate(name)
    path.write_bytes(content)
    return store.request(kind, ref, **where)


class TestStore:
    def test_kind_comes_from_the_extension(self):
        assert kind_of("crow.JPG") == "photo"
        assert kind_of("dawn.flac") == "audio"
        assert kind_of("roost.MOV") == "video"
        assert kind_of("notes.pdf") is None
        assert kind_of("crow") is None

    def test_allocate_refuses_what_no_worker_reads(self, store):
        with pytest.raises(ValueError, match="not a photo, audio or video"):
            store.allocate("crow.heic")

    def test_request_queues_under_an_unguessable_id(self, store):
        first, second = queued(store), queued(store)
        assert first["state"] == "queued"
        assert first["kind"] == "photo"
        assert len(first["public_id"]) >= 20
        assert first["public_id"] != second["public_id"]
        assert store.get_public(first["public_id"])["id"] == first["id"]
        assert store.get_public(str(first["id"])) is None

    def test_a_refused_upload_leaves_no_file(self, store):
        kind, ref, path = store.allocate("crow.jpg")
        path.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            store.request(kind, ref)
        assert not path.exists()

        kind, ref, path = store.allocate("crow.jpg")
        path.write_bytes(BYTES)
        with pytest.raises(ValueError, match="both latitude and longitude"):
            store.request(kind, ref, latitude=40.7)
        assert not path.exists()

    def test_each_worker_claims_only_its_kinds(self, store):
        photo = queued(store, "crow.jpg")
        video = queued(store, "roost.mp4")
        audio = queued(store, "dawn.wav")
        assert store.claim_next("sound")["id"] == video["id"]
        assert store.claim_next("sound")["id"] == audio["id"]
        assert store.claim_next("sound") is None
        assert store.claim_next("photo")["id"] == photo["id"]

    def test_the_file_is_gone_when_the_job_is_done(self, store):
        row = queued(store)
        path = store.path(row)
        store.claim_next("photo")
        done = store.complete(row["id"], RESULT)
        assert done["state"] == "done"
        assert done["result"] == RESULT
        assert done["storage_ref"] is None
        assert not path.exists()

    def test_the_file_is_gone_when_the_job_fails(self, store):
        row = queued(store)
        path = store.path(row)
        store.claim_next("photo")
        failed = store.fail(row["id"], "Could not read this photo.")
        assert failed["state"] == "failed"
        assert not path.exists()

    def test_ahead_counts_only_the_same_queue(self, store):
        queued(store, "dawn.wav")
        first = queued(store, "a.jpg")
        second = queued(store, "b.jpg")
        assert store.ahead_of(first) == 0
        assert store.ahead_of(second) == 1
        assert store.waiting("photo") == 2
        assert store.waiting("sound") == 1

    def test_prune_drops_rows_and_files_past_their_hour(self, store):
        row = queued(store)
        path = store.path(row)
        assert store.prune() == 0
        later = datetime.now(timezone.utc) + KEEP + timedelta(minutes=1)
        assert store.prune(now=later) == 1
        assert store.get_public(row["public_id"]) is None
        assert not path.exists()

    def test_reclaim_gives_a_file_one_more_try_only(self, store):
        row = queued(store)
        store.claim_next("photo")
        assert store.reclaim_running("photo") == (1, 0)
        store.claim_next("photo")
        assert store.reclaim_running("photo") == (0, 1)
        assert store.get_public(row["public_id"])["state"] == "failed"

    def test_a_worker_is_alive_only_while_it_keeps_saying_so(self, store):
        assert not store.alive("photo")
        store.beat("photo")
        assert store.alive("photo")
        assert not store.alive("sound")
        later = datetime.now(timezone.utc) + ALIVE_WITHIN + timedelta(seconds=5)
        assert not store.alive("photo", now=later)


class StubIdentifier:
    def __init__(self, error=None):
        self.error = error

    def identify(self, path, latitude, longitude):
        if self.error:
            raise self.error

        class Result:
            @staticmethod
            def to_dict():
                return RESULT

        return Result()


class TestPhotoWorker:
    def test_a_visitor_photo_is_answered_and_deleted(self, store):
        row = queued(store)
        path = store.path(row)
        scans = photo_worker.VisitorScans(store, StubIdentifier())
        assert scans.work_one() is True
        done = store.get_public(row["public_id"])
        assert done["state"] == "done"
        assert done["result"] == RESULT
        assert not path.exists()
        assert scans.work_one() is False

    def test_a_visitor_sees_a_fixed_sentence_not_the_exception(self, store):
        row = queued(store)
        scans = photo_worker.VisitorScans(store, StubIdentifier(OSError("/srv/secret/path broke")))
        scans.work_one()
        assert store.get_public(row["public_id"])["error"] == "Could not read this photo."

    def test_the_heartbeat_marks_the_photo_queue_alive(self, store):
        photo_worker.VisitorScans(store, StubIdentifier()).beat()
        assert store.alive("photo")


def upload(client, name="crow.jpg", content=BYTES, **form):
    return client.post("/api/demo/scan", data={"file": (io.BytesIO(content), name), **form},
                       content_type="multipart/form-data")


@pytest.fixture
def scans(app, db_path):
    """The app's own store, with both workers marked alive."""
    store = ScanStore(db_path, db_path.parent / "demo-scans")
    store.beat("photo")
    store.beat("sound")
    return store


class TestApi:
    def test_config_offers_only_kinds_with_a_live_worker(self, client, db_path):
        ScanStore(db_path, db_path.parent / "demo-scans").beat("sound")
        body = client.get("/api/demo/scan").get_json()
        assert body["kinds"] == {"photo": False, "audio": True, "video": True}
        assert body["max_mb"]["photo"] == 15
        assert body["sound_seconds"] == 90
        assert "jpg" in body["formats"]["photo"]

    def test_upload_needs_no_token_and_answers_with_a_public_id(self, client, scans):
        created = upload(client, latitude="40.76", longitude="-111.89")
        assert created.status_code == 202
        body = created.get_json()
        assert body["state"] == "queued"
        assert body["kind"] == "photo"
        assert body["ahead"] == 0
        assert set(body) == {"id", "kind", "state", "ahead"}

        polled = client.get(f"/api/demo/scan/{body['id']}")
        assert polled.status_code == 200
        assert polled.get_json()["state"] == "queued"

    def test_the_result_is_served_once_the_worker_is_done(self, client, scans):
        body = upload(client).get_json()
        row = scans.claim_next("photo")
        scans.complete(row["id"], RESULT)
        polled = client.get(f"/api/demo/scan/{body['id']}").get_json()
        assert polled == {"id": body["id"], "kind": "photo", "state": "done", "result": RESULT}

    def test_a_kind_with_no_worker_is_refused_before_anything_is_stored(self, client, db_path, tmp_path):
        store = ScanStore(db_path, db_path.parent / "demo-scans")
        store.beat("sound")
        assert upload(client, "crow.jpg").status_code == 503
        assert upload(client, "dawn.wav").status_code == 202
        assert store.waiting("photo") == 0
        assert len(list(store.scan_dir.iterdir())) == 1

    def test_refuses_formats_missing_files_and_bad_coordinates(self, client, scans):
        assert upload(client, "notes.pdf").status_code == 400
        assert upload(client, "crow.jpg", content=b"").status_code == 400
        assert upload(client, latitude="north", longitude="1").status_code == 400
        assert upload(client, latitude="40.7").status_code == 400
        missing = client.post("/api/demo/scan", data={}, content_type="multipart/form-data")
        assert missing.status_code == 400

    def test_a_full_queue_says_busy(self, client, scans):
        for _ in range(MAX_WAITING):
            assert upload(client).status_code == 202
        assert upload(client).status_code == 503

    def test_one_address_gets_an_allowance(self, client, scans):
        from fieldserver.api.scan import SCANS_PER_HOUR

        statuses = []
        for _ in range(SCANS_PER_HOUR + 1):
            statuses.append(upload(client).status_code)
            row = scans.claim_next("photo")
            if row:
                scans.complete(row["id"], RESULT)
        assert statuses[-1] == 429
        assert statuses[:-1] == [202] * SCANS_PER_HOUR

    def test_an_unknown_id_is_404(self, client, scans):
        assert client.get("/api/demo/scan/nope").status_code == 404

    def test_the_promo_origin_may_read_it(self, client, scans):
        response = client.get("/api/demo/scan", headers={"Origin": "https://crowgpt.org"})
        assert response.headers["Access-Control-Allow-Origin"] == "https://crowgpt.org"
