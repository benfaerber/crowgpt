"""Crow Chat: the generation queue and its API surface.

The worker itself needs torch and a checkpoint, so these tests stop at the seam
it works across: rows queued by the API, claimed and completed the way
generate_worker.py does, and the audio route serving what the worker wrote.
"""

import pytest

from fieldserver.stores.generations import MODELS, GenerationStore


@pytest.fixture
def store(db_path, tmp_path):
    return GenerationStore(db_path, tmp_path / "generated")


class TestStore:
    def test_request_queues_with_a_seed(self, store):
        row = store.request("alarm call", contributor_id=None)
        assert row["state"] == "queued"
        assert row["call_type"] == "alarm call"
        assert row["model"] == "model-calltype"
        assert isinstance(row["seed"], int)
        assert row["storage_ref"] is None

    def test_request_refuses_unknown_call_type(self, store):
        with pytest.raises(ValueError, match="takes a call_type from"):
            store.request("screech")

    def test_request_refuses_unknown_model(self, store):
        with pytest.raises(ValueError, match="model must be one of"):
            store.request("call", model="model-imaginary")

    def test_release_request_is_a_bare_caw(self, store):
        row = store.request(None, model="crowgpt2")
        assert row["call_type"] is None
        assert row["model"] == "crowgpt2"

    def test_release_refuses_a_call_type(self, store):
        with pytest.raises(ValueError, match="does not take a call_type"):
            store.request("alarm call", model="crowgpt1")

    def test_calltype_model_requires_a_call_type(self, store):
        with pytest.raises(ValueError, match="takes a call_type from"):
            store.request(None, model="model-calltype")

    def test_claim_complete_lifecycle(self, store):
        row = store.request("song")
        claimed = store.claim_next()
        assert claimed["id"] == row["id"]
        assert claimed["state"] == "running"
        assert claimed["attempts"] == 1
        assert store.claim_next() is None

        ref = store.allocate_ref()
        store.path({"storage_ref": ref}).write_bytes(b"RIFF")
        done = store.complete(row["id"], ref, 3.0, "model-calltype", 1.0, 200)
        assert done["state"] == "done"
        assert done["storage_ref"] == ref
        assert done["duration_sec"] == 3.0

    def test_fail_is_terminal(self, store):
        row = store.request("call")
        store.claim_next()
        failed = store.fail(row["id"], "no GPU")
        assert failed["state"] == "failed"
        assert failed["error"] == "no GPU"
        assert store.claim_next() is None

    def test_reclaim_requeues_then_abandons(self, store):
        row = store.request("begging")
        store.claim_next()
        requeued, abandoned = store.reclaim_running(max_attempts=2)
        assert (requeued, abandoned) == (1, 0)

        store.claim_next()
        assert store.get(row["id"])["attempts"] == 2
        requeued, abandoned = store.reclaim_running(max_attempts=2)
        assert (requeued, abandoned) == (0, 1)
        assert store.get(row["id"])["state"] == "failed"

    def test_forget_clears_rows_and_clips(self, store):
        row = store.request("song")
        store.claim_next()
        ref = store.allocate_ref()
        store.path({"storage_ref": ref}).write_bytes(b"RIFF")
        store.complete(row["id"], ref, 3.0, "model-calltype", 1.0, 200)

        assert store.forget() == 1
        assert store.recent() == []
        assert not store.path({"storage_ref": ref}).exists()

    def test_complete_after_forget_leaves_no_orphan(self, store):
        row = store.request("song")
        store.claim_next()
        store.forget()

        ref = store.allocate_ref()
        store.path({"storage_ref": ref}).write_bytes(b"RIFF")
        done = store.complete(row["id"], ref, 3.0, "model-calltype", 1.0, 200)
        assert done is None
        assert not store.path({"storage_ref": ref}).exists()

    def test_recent_is_in_chat_order(self, store):
        first = store.request("alarm call")
        second = store.request("song")
        rows = store.recent()
        assert [r["id"] for r in rows] == [first["id"], second["id"]]


class TestApi:
    def test_needs_an_operator(self, client, enroll):
        contributor = enroll(contributor_name="Recordist")
        assert client.get("/api/generations",
                          headers=contributor.headers).status_code == 403
        assert client.post("/api/generations", json={"call_type": "song"},
                           headers=contributor.headers).status_code == 403

    def test_create_and_list(self, client, operator):
        created = client.post("/api/generations", json={"call_type": "alarm call"},
                              headers=operator.headers)
        assert created.status_code == 201
        assert created.get_json()["state"] == "queued"

        listed = client.get("/api/generations", headers=operator.headers)
        assert listed.status_code == 200
        body = listed.get_json()
        assert body["models"] == [
            {"name": name, "call_types": list(call_types)}
            for name, call_types in MODELS.items()]
        assert [g["id"] for g in body["generations"]] == [created.get_json()["id"]]

    def test_create_without_a_model_is_the_calltype_default(self, client, operator):
        created = client.post("/api/generations", json={"call_type": "song"},
                              headers=operator.headers)
        assert created.status_code == 201
        assert created.get_json()["model"] == "model-calltype"

    def test_create_addressed_to_a_release(self, client, operator):
        created = client.post("/api/generations", json={"model": "crowgpt2"},
                              headers=operator.headers)
        assert created.status_code == 201
        body = created.get_json()
        assert body["model"] == "crowgpt2"
        assert body["call_type"] is None

    def test_create_refuses_unknown_call_type(self, client, operator):
        response = client.post("/api/generations", json={"call_type": "screech"},
                               headers=operator.headers)
        assert response.status_code == 400

    def test_create_refuses_unknown_model(self, client, operator):
        response = client.post("/api/generations",
                               json={"model": "model-imaginary",
                                     "call_type": "song"},
                               headers=operator.headers)
        assert response.status_code == 400

    def test_create_refuses_a_call_type_for_a_release(self, client, operator):
        response = client.post("/api/generations",
                               json={"model": "crowgpt1",
                                     "call_type": "alarm call"},
                               headers=operator.headers)
        assert response.status_code == 400

    def test_audio_409s_until_done_then_serves(self, client, operator, db_path):
        created = client.post("/api/generations", json={"call_type": "song"},
                              headers=operator.headers).get_json()
        pending = client.get(f"/api/generations/{created['id']}/audio",
                             headers=operator.headers)
        assert pending.status_code == 409

        store = GenerationStore(db_path, db_path.parent / "generated")
        store.claim_next()
        ref = store.allocate_ref()
        store.path({"storage_ref": ref}).write_bytes(b"RIFFfake")
        store.complete(created["id"], ref, 3.0, "model-calltype", 1.0, 200)

        served = client.get(f"/api/generations/{created['id']}/audio",
                            headers=operator.headers)
        assert served.status_code == 200
        assert served.mimetype == "audio/wav"
        assert served.data == b"RIFFfake"

    def test_audio_404s_for_missing_row(self, client, operator):
        assert client.get("/api/generations/9999/audio",
                          headers=operator.headers).status_code == 404

    def test_forget_needs_an_operator(self, client, enroll):
        contributor = enroll(contributor_name="Recordist")
        assert client.delete("/api/generations",
                             headers=contributor.headers).status_code == 403

    def test_forget_clears_the_thread(self, client, operator):
        client.post("/api/generations", json={"call_type": "song"},
                    headers=operator.headers)
        response = client.delete("/api/generations", headers=operator.headers)
        assert response.status_code == 200
        assert response.get_json() == {"forgotten": 1}
        listed = client.get("/api/generations", headers=operator.headers)
        assert listed.get_json()["generations"] == []
