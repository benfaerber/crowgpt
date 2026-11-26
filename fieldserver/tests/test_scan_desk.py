"""The labelling desk for a kept scan, and its promotion to a capture.

The link is the only credential, so most of what is pinned here is what the
link does NOT open: another recording, a free-text column, a recording that
has already been reviewed.
"""

import io
import math
import shutil
import struct
import wave

import pytest

from fieldserver.stores.scan_desk import MAX_LABELS, ScanDeskStore
from fieldserver.stores.scans import ScanStore

RESULT = {
    "duration_sec": 2.0, "waveform": [0.1, 0.9, 0.2], "truncated": False, "located": False,
    # The analyzer's own words, as the worker stores them: `start` and `end`.
    "calls": [{"start": 0.0, "end": 1.5, "species": "Common Raven",
               "scientific_name": "Corvus corax", "call_type": "alarm call",
               "confidence": 0.9, "alternates": [], "multi_label": True,
               "crow_conf": 0.8, "candidate": False, "location_filtered": False}],
}
LABEL = "0b7c1e52-aaaa-4bbb-8ccc-1234567890ab"
EVENT = "7d1f0c9e-dddd-4eee-8fff-ba0987654321"


def tone(seconds=2.0, rate=16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 1200 * i / rate)))
            for i in range(int(seconds * rate))))
    return out.getvalue()


@pytest.fixture
def scans(app, db_path):
    return ScanStore(db_path, db_path.parent / "demo-scans")


@pytest.fixture
def desk(scans):
    return ScanDeskStore(scans.db_path, scans.kept_dir)


ADDRESS = "203.0.113.7"


def kept(scans, name="dawn.wav", content=None, result=RESULT):
    kind, ref, path = scans.allocate(name)
    path.write_bytes(content or tone())
    row = scans.request(kind, ref, keep=True, requester_ip=ADDRESS)
    scans.claim_next("photo" if kind == "photo" else "sound")
    scans.complete(row["id"], result)
    return row["public_id"]


def put_label(client, public_id, uuid=LABEL, **body):
    return client.put(f"/api/scan-desk/{public_id}/labels/{uuid}", json={
        "start_sec": 0.0, "end_sec": 1.5, "call_type": "alarm call", "from_detection": True,
        **body})


class TestTheVisitorsDesk:
    def test_the_link_outlives_the_scan_row(self, client, scans):
        public_id = kept(scans)
        with scans._connect() as conn:
            conn.execute("DELETE FROM demo_scans")
        body = client.get(f"/api/scan-desk/{public_id}").get_json()
        assert [(call["start_sec"], call["end_sec"], call["call_type"], call["candidate"])
                for call in body["calls"]] == [(0.0, 1.5, "alarm call", 0)]
        assert body["labels"] == [] and body["context"] == []
        assert body["closed"] is False
        assert {label["key"] for label in body["config"]["labels"]} >= {"alarm call"}

    def test_the_scan_page_may_read_a_desk_and_nothing_else_may(self, client, scans):
        public_id = kept(scans)
        read = client.get(f"/api/scan-desk/{public_id}", headers={"Origin": "https://crowgpt.org"})
        assert read.headers["Access-Control-Allow-Origin"] == "https://crowgpt.org"
        other = client.get(f"/api/scan-desk/{public_id}", headers={"Origin": "https://example.com"})
        assert "Access-Control-Allow-Origin" not in other.headers
        write = client.options(f"/api/scan-desk/{public_id}/labels/{LABEL}",
                               headers={"Origin": "https://crowgpt.org",
                                        "Access-Control-Request-Method": "PUT"})
        assert "Access-Control-Allow-Origin" not in write.headers

    def test_a_guessed_or_photo_link_opens_nothing(self, client, scans):
        photo = kept(scans, "crow.jpg", b"jpeg", {"ranking": []})
        assert client.get("/api/scan-desk/nope").status_code == 404
        assert client.get(f"/api/scan-desk/{photo}").status_code == 404
        assert put_label(client, "nope").status_code == 404

    def test_the_kept_file_streams_with_range_support(self, client, scans):
        public_id = kept(scans)
        part = client.get(f"/api/scan-desk/{public_id}/audio", headers={"Range": "bytes=0-99"})
        assert part.status_code == 206
        assert len(part.data) == 100
        assert part.mimetype == "audio/wav"

    def test_a_label_is_stored_replaced_and_retracted(self, client, scans, desk):
        public_id = kept(scans)
        assert put_label(client, public_id).status_code == 200
        assert put_label(client, public_id, call_type="begging").get_json()["call_type"] == "begging"
        labels = client.get(f"/api/scan-desk/{public_id}").get_json()["labels"]
        assert [(row["client_uuid"], row["call_type"]) for row in labels] == [(LABEL, "begging")]
        assert client.delete(f"/api/scan-desk/{public_id}/labels/{LABEL}").status_code == 204
        assert client.get(f"/api/scan-desk/{public_id}").get_json()["labels"] == []

    def test_only_the_served_vocabulary_is_stored(self, client, scans):
        public_id = kept(scans)
        assert put_label(client, public_id, call_type="<script>").status_code == 400
        assert put_label(client, public_id, uuid="x").status_code == 400
        assert put_label(client, public_id, start_sec=3, end_sec=1).status_code == 400
        put_label(client, public_id)
        context = f"/api/scan-desk/{public_id}/context/{EVENT}"
        assert client.put(context, json={"key": "made up", "label_uuid": LABEL}).status_code == 400
        assert client.patch(f"/api/scan-desk/{public_id}/labels/{LABEL}",
                            json={"caller_role": "the big one"}).status_code == 400

    def test_context_hangs_off_a_label_and_leaves_with_it(self, client, scans):
        public_id = kept(scans)
        put_label(client, public_id)
        context = f"/api/scan-desk/{public_id}/context/{EVENT}"
        orphan = client.put(context, json={"key": "dog_visible",
                                           "label_uuid": "ffffffff-0000-4000-8000-000000000000"})
        assert orphan.status_code == 404
        stored = client.put(context, json={"key": "dog_visible", "label_uuid": LABEL,
                                           "start_sec": 0.0, "end_sec": 1.5})
        assert stored.get_json()["label_uuid"] == LABEL
        client.delete(f"/api/scan-desk/{public_id}/labels/{LABEL}")
        assert client.get(f"/api/scan-desk/{public_id}").get_json()["context"] == []

    def test_silence_and_a_label_cannot_both_stand(self, client, scans):
        public_id = kept(scans)
        silent = client.post(f"/api/scan-desk/{public_id}/silent", json={"silent": True})
        assert silent.get_json()["silent_confirmed_at"]
        put_label(client, public_id)
        assert client.get(f"/api/scan-desk/{public_id}").get_json()["silent_confirmed_at"] is None
        again = client.post(f"/api/scan-desk/{public_id}/silent", json={"silent": True})
        assert again.status_code == 409

    def test_one_link_cannot_reach_another_recording(self, client, scans):
        mine, theirs = kept(scans), kept(scans)
        put_label(client, theirs)
        assert client.delete(f"/api/scan-desk/{mine}/labels/{LABEL}").status_code == 204
        assert len(client.get(f"/api/scan-desk/{theirs}").get_json()["labels"]) == 1

    def test_a_recording_holds_only_so_many_labels(self, scans, desk):
        contribution = desk.by_public_id(kept(scans))
        for i in range(MAX_LABELS):
            desk.put_label(contribution["id"], f"label-{i:04d}", i, i + 1, "call")
        with pytest.raises(ValueError):
            desk.put_label(contribution["id"], "one-too-many", 0, 1, "call")


class TestTheOperatorsPile:
    def test_the_pile_needs_an_operator(self, client, scans, enroll):
        kept(scans)
        assert client.get("/api/fleet/scan-contributions").status_code == 401
        visitor = enroll()
        assert client.get("/api/fleet/scan-contributions", headers=visitor.headers).status_code == 403

    def test_the_pile_lists_what_was_said(self, client, scans, operator):
        public_id = kept(scans)
        put_label(client, public_id)
        rows = client.get("/api/fleet/scan-contributions",
                          headers=operator.headers).get_json()
        assert [scan["requester_ip"] for scan in rows["recent"]] == [ADDRESS]
        rows = rows["contributions"]
        assert len(rows) == 1
        assert rows[0]["label_count"] == 1 and rows[0]["call_count"] == 1
        assert rows[0]["desk_url"].endswith(f"/label/{public_id}")
        assert rows[0]["requester_ip"] == ADDRESS
        assert ADDRESS not in client.get(f"/api/scan-desk/{public_id}").get_data(as_text=True)
        detail = client.get(f"/api/fleet/scan-contributions/{rows[0]['id']}",
                            headers=operator.headers).get_json()
        assert detail["labels"][0]["call_type"] == "alarm call"

    def test_a_row_says_what_the_scanner_heard(self, client, scans, operator):
        heard = {**RESULT, "co_detections": [{"species": "Cooper's Hawk", "confidence": 0.74}],
                 "calls": RESULT["calls"] + [{**RESULT["calls"][0], "start": 1.5, "end": 2.0,
                                              "candidate": True}]}
        kept(scans, result=heard)
        row = client.get("/api/fleet/scan-contributions",
                         headers=operator.headers).get_json()["contributions"][0]
        assert row["format"] == "wav" and row["truncated"] is False
        assert row["heard"] == {
            "kind": "sound", "species": ["Common Raven"],
            "call_types": [{"call_type": "alarm call", "count": 2}], "candidates": 1,
            "co_detections": heard["co_detections"]}
        detail = client.get(f"/api/fleet/scan-contributions/{row['id']}",
                            headers=operator.headers).get_json()
        assert detail["result"] == heard
        assert detail["storage_ref"].endswith(".wav")

    def test_a_photo_row_names_the_bird_or_says_there_is_none(self, client, scans, operator):
        crow = {"ranking": [{"slug": "american-crow", "common_name": "American Crow",
                             "scientific_name": "Corvus brachyrhynchos", "probability": 0.93}],
                "bird_box": {"left": 1, "top": 2, "right": 30, "bottom": 40, "score": 0.98,
                             "birds": 2},
                "used_location": False, "latitude": None, "longitude": None,
                "location_source": None, "width": 64, "height": 48}
        kept(scans, "crow.jpg", b"jpeg", crow)
        kept(scans, "cat.jpg", b"jpeg", {**crow, "bird_box": None, "verdict": "other",
                                         "instead": "cat"})
        cat, bird = [row["heard"] for row in client.get(
            "/api/fleet/scan-contributions", headers=operator.headers).get_json()["contributions"]]
        assert bird == {"kind": "photo", "verdict": "corvid", "instead": None,
                        "species": "American Crow", "probability": 0.93, "birds": 2}
        assert (cat["verdict"], cat["instead"], cat["birds"]) == ("other", "cat", 0)

    def test_delete_removes_the_file_and_the_answers(self, client, scans, desk, operator):
        public_id = kept(scans)
        put_label(client, public_id)
        contribution = desk.by_public_id(public_id)
        gone = client.delete(f"/api/fleet/scan-contributions/{contribution['id']}",
                             headers=operator.headers)
        assert gone.status_code == 204
        assert not desk.path(contribution).exists()
        assert desk.labels(contribution["id"]) == []
        assert client.get(f"/api/scan-desk/{public_id}").status_code == 404


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="promotion decodes with ffmpeg")
class TestPromotion:
    def promote(self, client, desk, operator, public_id):
        contribution = desk.by_public_id(public_id)
        return client.post(f"/api/fleet/scan-contributions/{contribution['id']}/promote",
                           headers=operator.headers)

    def test_a_contribution_becomes_a_capture_that_is_never_kept(self, client, scans, desk, operator, app):
        public_id = kept(scans)
        put_label(client, public_id)
        client.put(f"/api/scan-desk/{public_id}/context/{EVENT}",
                   json={"key": "dog_visible", "label_uuid": LABEL, "start_sec": 0.0, "end_sec": 1.5})
        promoted = self.promote(client, desk, operator, public_id)
        assert promoted.status_code == 200
        capture_id = promoted.get_json()["capture_id"]
        with desk._connect() as conn:
            capture = dict(conn.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone())
            labels = [dict(r) for r in conn.execute("SELECT * FROM labels WHERE capture_id = ?", (capture_id,))]
            events = [dict(r) for r in conn.execute("SELECT * FROM context_events WHERE capture_id = ?", (capture_id,))]
            jobs = conn.execute("SELECT COUNT(*) FROM analysis_jobs WHERE capture_id = ?", (capture_id,)).fetchone()[0]
        assert capture["provenance"] == "scan"
        assert capture["keep"] == 0 and capture["generator_excluded"] == 1
        assert [(row["call_type"], row["label_source"], row["species"]) for row in labels] == [
            ("alarm call", "visitor", "Common Raven")]
        assert [(row["key"], row["label_id"]) for row in events] == [("dog_visible", labels[0]["id"])]
        assert jobs == 1

    def test_promoting_twice_makes_one_capture(self, client, scans, desk, operator):
        public_id = kept(scans)
        put_label(client, public_id)
        first = self.promote(client, desk, operator, public_id).get_json()["capture_id"]
        second = self.promote(client, desk, operator, public_id).get_json()["capture_id"]
        assert first == second
        with desk._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM labels WHERE capture_id = ?", (first,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM analysis_jobs WHERE capture_id = ?", (first,)).fetchone()[0] == 1

    def test_a_promoted_recording_is_closed_to_its_visitor(self, client, scans, desk, operator):
        public_id = kept(scans)
        self.promote(client, desk, operator, public_id)
        assert client.get(f"/api/scan-desk/{public_id}").get_json()["closed"] is True
        assert put_label(client, public_id).status_code == 409

    def test_a_photo_is_not_promotable(self, client, scans, desk, operator):
        kept(scans, "crow.jpg", b"jpeg", {"ranking": []})
        contribution = desk.list_all()[0]
        refused = client.post(f"/api/fleet/scan-contributions/{contribution['id']}/promote",
                              headers=operator.headers)
        assert refused.status_code == 409
