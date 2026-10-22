"""The dictation routes: who may reach a memo, and when a transcript counts.

The confirmation route is the one worth the most attention. It is the entire
boundary between "a machine's guess at what he said" and "what he said", and the
whole design rests on that boundary being crossed deliberately, once, by a human.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    response = client.post("/api/captures", json={"notes": "Two crows on the wire."},
                           headers=recordist.headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def upload(client, headers, capture_id, data=b"RIFFxxxxWAVEfmt spoken", **body):
    made = client.post(f"/api/captures/{capture_id}/dictations",
                       json=body, headers=headers)
    assert made.status_code == 201, made.get_data(as_text=True)
    row = made.get_json()
    sent = client.put(f"/api/dictations/{row['id']}", data=data,
                      headers={**headers, "Content-Type": "application/octet-stream",
                               "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}"})
    assert sent.status_code == 200, sent.get_data(as_text=True)
    return sent.get_json()


class TestWhoMayReachOne:
    def test_a_stranger_cannot_add_one(self, client, capture, stranger):
        response = client.post(f"/api/captures/{capture['id']}/dictations",
                               json={}, headers=stranger.headers)
        assert response.status_code == 403

    def test_no_token_is_refused(self, client, capture):
        assert client.post(f"/api/captures/{capture['id']}/dictations",
                           json={}).status_code == 401

    def test_a_stranger_cannot_read_the_audio(self, client, capture, recordist, stranger):
        row = upload(client, recordist.headers, capture["id"])
        assert client.get(f"/api/dictations/{row['id']}/raw",
                          headers=stranger.headers).status_code == 403

    def test_a_job_cannot_be_walked_by_id(self, client, capture, recordist, stranger):
        """Ownership is re-derived through the job's capture. Without that, any
        enrolled phone could enumerate job ids and learn which captures exist on
        somebody else's account — the hole api/analysis.py records."""
        row = upload(client, recordist.headers, capture["id"])
        job_id = row["job"]["id"]
        assert client.get(f"/api/dictation-jobs/{job_id}",
                          headers=stranger.headers).status_code == 403
        assert client.get(f"/api/dictation-jobs/{job_id}",
                          headers=recordist.headers).status_code == 200


class TestUploading:
    def test_a_completed_upload_queues_exactly_one_job(self, client, capture, recordist):
        row = upload(client, recordist.headers, capture["id"])
        assert row["upload_state"] == "complete"
        assert row["job"]["state"] == "queued"

    def test_resending_the_final_chunk_does_not_queue_a_second(
        self, client, capture, recordist
    ):
        """Routine on a bad link. Without the guard the same ninety seconds gets
        transcribed twice."""
        data = b"RIFFxxxxWAVEfmt spoken"
        row = upload(client, recordist.headers, capture["id"], data=data)
        again = client.put(
            f"/api/dictations/{row['id']}", data=data,
            headers={**recordist.headers, "Content-Type": "application/octet-stream",
                     "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}"})

        assert again.get_json()["job"]["id"] == row["job"]["id"]

    def test_a_hole_is_refused(self, client, capture, recordist):
        made = client.post(f"/api/captures/{capture['id']}/dictations", json={},
                           headers=recordist.headers)
        row = made.get_json()
        response = client.put(
            f"/api/dictations/{row['id']}", data=b"late",
            headers={**recordist.headers, "Content-Type": "application/octet-stream",
                     "Content-Range": "bytes 4096-4099/4100"})
        assert response.status_code == 400

    def test_it_resumes_across_two_chunks(self, client, capture, recordist):
        made = client.post(f"/api/captures/{capture['id']}/dictations", json={},
                           headers=recordist.headers)
        row = made.get_json()
        head, tail = b"first half ", b"second half"
        total = len(head) + len(tail)
        client.put(f"/api/dictations/{row['id']}", data=head,
                   headers={**recordist.headers,
                            "Content-Range": f"bytes 0-{len(head) - 1}/{total}"})
        done = client.put(
            f"/api/dictations/{row['id']}", data=tail,
            headers={**recordist.headers,
                     "Content-Range": f"bytes {len(head)}-{total - 1}/{total}"})

        assert done.get_json()["upload_state"] == "complete"
        assert done.get_json()["bytes"] == total


def transcribe(db_path, dictation, text, model=None):
    """Finish the queued job the completing PUT created, the worker's way."""
    from fieldserver.stores.dictations import DictationStore

    store = DictationStore(db_path, db_path.parent / "dictations")
    job = store.claim_next()
    assert job and job["dictation_id"] == dictation["id"]
    store.complete(job["id"], dictation["id"], text, model=model)


class TestConfirmation:
    """The boundary between a machine's spelling and the recordist's words."""

    def test_it_refuses_before_there_is_a_transcript(self, client, capture, recordist):
        row = upload(client, recordist.headers, capture["id"])
        response = client.post(f"/api/dictations/{row['id']}/confirm",
                               json={}, headers=recordist.headers)
        assert response.status_code == 409

    def test_confirming_writes_one_observation_marked_as_spoken(
        self, client, capture, recordist, app, db_path
    ):
        row = upload(client, recordist.headers, capture["id"])
        transcribe(db_path, row, "two of them were mobbing the hawk", model="whisper")

        confirmed = client.post(f"/api/dictations/{row['id']}/confirm",
                                json={}, headers=recordist.headers)
        assert confirmed.status_code == 200
        assert confirmed.get_json()["confirmed_at"] is not None

        notes = client.get(f"/api/captures/{capture['id']}/observations",
                           headers=recordist.headers).get_json()
        assert len(notes) == 1
        assert notes[0]["body"] == "two of them were mobbing the hawk"
        assert notes[0]["source"] == "voice"

    def test_the_human_may_correct_it_on_the_way_through(
        self, client, capture, recordist, db_path
    ):
        """What gets promoted is what somebody stands behind, not what the model
        produced. A mis-heard name is corrected here or it is testimony forever."""
        row = upload(client, recordist.headers, capture["id"])
        transcribe(db_path, row, "Edgar Allen was on the wire")

        client.post(f"/api/dictations/{row['id']}/confirm",
                    json={"text": "Edgar was on the wire"}, headers=recordist.headers)

        notes = client.get(f"/api/captures/{capture['id']}/observations",
                           headers=recordist.headers).get_json()
        assert notes[0]["body"] == "Edgar was on the wire"

    def test_confirming_twice_corrects_rather_than_duplicating(
        self, client, capture, recordist, db_path
    ):
        """Otherwise one thirty seconds becomes two agreeing accounts of it."""
        row = upload(client, recordist.headers, capture["id"])
        transcribe(db_path, row, "first reading")

        client.post(f"/api/dictations/{row['id']}/confirm", json={},
                    headers=recordist.headers)
        client.post(f"/api/dictations/{row['id']}/confirm",
                    json={"text": "second, better reading"}, headers=recordist.headers)

        notes = client.get(f"/api/captures/{capture['id']}/observations",
                           headers=recordist.headers).get_json()
        assert len(notes) == 1
        assert notes[0]["body"] == "second, better reading"
