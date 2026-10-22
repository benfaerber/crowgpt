"""Idempotent create for captures, media, observations and families.

The field app records offline and syncs on demand, so a retried POST after a lost
response is routine rather than exceptional. These pin the behaviour that keeps a
retry from duplicating a capture or stranding a half-uploaded file.
"""

import sqlite3

import pytest

from fieldserver.app import DEFAULT_ENROLL_TOKEN, create_app


class TestCaptureReplay:
    def test_a_replayed_create_returns_the_same_row(self, client, recordist):
        body = {"client_uuid": "cap-abc", "latitude": 40.76, "longitude": -111.89}
        first = client.post("/api/captures", json=body, headers=recordist.headers).get_json()
        again = client.post("/api/captures", json=body, headers=recordist.headers).get_json()
        assert first["id"] == again["id"]

    def test_the_client_uuid_is_persisted(self, client, recordist):
        created = client.post("/api/captures", json={"client_uuid": "cap-abc"},
                              headers=recordist.headers).get_json()
        assert created["client_uuid"] == "cap-abc"

    def test_a_different_uuid_creates_a_new_capture(self, client, recordist):
        first = client.post("/api/captures", json={"client_uuid": "cap-abc"},
                            headers=recordist.headers).get_json()
        other = client.post("/api/captures", json={"client_uuid": "cap-xyz"},
                            headers=recordist.headers).get_json()
        assert other["id"] != first["id"]

    def test_three_posts_with_two_uuids_leave_two_captures(self, client, recordist):
        body = {"client_uuid": "cap-abc"}
        client.post("/api/captures", json=body, headers=recordist.headers)
        client.post("/api/captures", json=body, headers=recordist.headers)
        client.post("/api/captures", json={"client_uuid": "cap-xyz"},
                    headers=recordist.headers)
        assert len(client.get("/api/captures", headers=recordist.headers).get_json()) == 2

    def test_uuidless_creates_are_still_distinct(self, client, recordist):
        """Old clients and api.rest post without one; they must not collapse."""
        first = client.post("/api/captures", json={"notes": "no uuid"},
                            headers=recordist.headers).get_json()
        second = client.post("/api/captures", json={"notes": "no uuid"},
                             headers=recordist.headers).get_json()
        assert first["id"] != second["id"]


class TestMediaResume:
    @pytest.fixture
    def capture(self, client, recordist):
        return client.post("/api/captures", json={"client_uuid": "cap-abc"},
                           headers=recordist.headers).get_json()

    @pytest.fixture
    def half_uploaded(self, client, recordist, capture):
        slot = client.post(f"/api/captures/{capture['id']}/media",
                           json={"client_uuid": "med-1", "format": "wav"},
                           headers=recordist.headers).get_json()
        client.put(f"/api/media/{slot['id']}", data=b"0123456789",
                   headers={**recordist.headers, "Content-Range": "bytes 0-9/20"})
        return slot

    def test_a_replayed_slot_is_the_same_slot(
            self, client, recordist, capture, half_uploaded):
        again = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1", "format": "wav"},
                            headers=recordist.headers).get_json()
        assert again["id"] == half_uploaded["id"]
        assert again["storage_ref"] == half_uploaded["storage_ref"]

    def test_the_replay_reports_the_resume_offset(
            self, client, recordist, capture, half_uploaded):
        """The server's byte count is what the client resumes from."""
        again = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1", "format": "wav"},
                            headers=recordist.headers).get_json()
        assert again["bytes"] == 10

    def test_resuming_from_that_offset_finalizes_the_upload(
            self, client, recordist, half_uploaded):
        done = client.put(f"/api/media/{half_uploaded['id']}", data=b"abcdefghij",
                          headers={**recordist.headers,
                                   "Content-Range": "bytes 10-19/20"}).get_json()
        assert done["upload_state"] == "complete"
        assert done["bytes"] == 20


class TestMicrophoneProvenance:
    """Which mic recorded a clip cannot be recovered after the fact.

    Nothing in a WAV says it arrived over a Bluetooth headset, and such a clip is
    narrowband and speech-processed — much less use for training. Cheap to record
    at capture time, impossible to backfill.
    """

    @pytest.fixture
    def capture(self, client, recordist):
        return client.post("/api/captures", json={"client_uuid": "cap-abc"},
                           headers=recordist.headers).get_json()

    def test_the_microphone_is_stored_with_the_audio(self, client, recordist, capture):
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1", "input_device": "BUILTIN_MIC",
                                  "input_honoured": True},
                            headers=recordist.headers).get_json()
        assert media["input_device"] == "BUILTIN_MIC"
        assert media["input_honoured"] == 1

    def test_a_refused_pin_is_recorded_as_such(self, client, recordist, capture):
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1",
                                  "input_device": "BLUETOOTH_SCO",
                                  "input_honoured": False},
                            headers=recordist.headers).get_json()
        assert media["input_device"] == "BLUETOOTH_SCO"
        assert media["input_honoured"] == 0

    def test_pre_roll_says_how_much_predates_the_button(
            self, client, recordist, capture):
        # A pre-rolled clip has its call near the 15s mark, not at the start.
        # Nothing in the WAV says so, and no analysis recovers it afterwards.
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1", "pre_roll_sec": 14.5},
                            headers=recordist.headers).get_json()
        assert media["pre_roll_sec"] == pytest.approx(14.5)

    def test_no_pre_roll_is_null_not_zero(self, client, recordist, capture):
        # Zero is a claim — "this recording began when the button was pressed".
        # Every capture made before the rolling buffer existed can't make it.
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1"},
                            headers=recordist.headers).get_json()
        assert media["pre_roll_sec"] is None

    def test_a_replay_does_not_lose_it(self, client, recordist, capture):
        # The slot is created once and replayed on every resumed sync; a replay
        # that returned the row without this would look like an unknown mic.
        body = {"client_uuid": "med-1", "input_device": "BUILTIN_MIC",
                "input_honoured": True}
        client.post(f"/api/captures/{capture['id']}/media", json=body,
                    headers=recordist.headers)
        again = client.post(f"/api/captures/{capture['id']}/media", json=body,
                            headers=recordist.headers).get_json()
        assert again["input_device"] == "BUILTIN_MIC"

    def test_an_older_client_that_sends_nothing_is_accepted(
            self, client, recordist, capture):
        # Null means "nobody knows", which is the honest answer for every
        # recording made before this existed. It must not become a hard failure.
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1"},
                            headers=recordist.headers).get_json()
        assert media["input_device"] is None
        assert media["input_honoured"] is None

    def test_the_dashboard_reports_it(self, client, recordist, operator, capture):
        client.post(f"/api/captures/{capture['id']}/media",
                    json={"client_uuid": "med-1", "input_device": "BUILTIN_MIC",
                          "input_honoured": True},
                    headers=recordist.headers)
        detail = client.get(f"/api/fleet/captures/{capture['id']}",
                            headers=operator.headers).get_json()
        assert detail["media"][0]["input_device"] == "BUILTIN_MIC"


class TestObservationReplay:
    @pytest.fixture
    def capture(self, client, recordist):
        return client.post("/api/captures", json={"client_uuid": "cap-abc"},
                           headers=recordist.headers).get_json()

    def test_a_replayed_observation_returns_the_same_id(self, client, recordist, capture):
        body = {"client_uuid": "obs-1", "body": "Edgar alone on the wire, calling."}
        first = client.post(f"/api/captures/{capture['id']}/observations",
                            json=body, headers=recordist.headers).get_json()
        again = client.post(f"/api/captures/{capture['id']}/observations",
                            json=body, headers=recordist.headers).get_json()
        assert first["id"] == again["id"]

    def test_a_replay_carries_an_edited_body_through(self, client, recordist, capture):
        """An edit made between a failed push and its retry must win."""
        body = {"client_uuid": "obs-1", "body": "Edgar alone on the wire, calling."}
        first = client.post(f"/api/captures/{capture['id']}/observations",
                            json=body, headers=recordist.headers).get_json()
        edited = client.post(f"/api/captures/{capture['id']}/observations",
                             json={**body, "body": "Edgar alone, then two returned."},
                             headers=recordist.headers).get_json()
        assert edited["id"] == first["id"]
        assert edited["body"].endswith("two returned.")

    def test_a_different_uuid_makes_a_second_observation(self, client, recordist, capture):
        first = client.post(f"/api/captures/{capture['id']}/observations",
                            json={"client_uuid": "obs-1", "body": "One."},
                            headers=recordist.headers).get_json()
        second = client.post(f"/api/captures/{capture['id']}/observations",
                             json={"client_uuid": "obs-2", "body": "Two."},
                             headers=recordist.headers).get_json()
        assert second["id"] != first["id"]

    def test_uuidless_observations_are_still_distinct(self, client, recordist, capture):
        first = client.post(f"/api/captures/{capture['id']}/observations",
                            json={"body": "no uuid"}, headers=recordist.headers).get_json()
        second = client.post(f"/api/captures/{capture['id']}/observations",
                             json={"body": "no uuid"}, headers=recordist.headers).get_json()
        assert first["id"] != second["id"]

    def test_an_empty_body_is_not_an_observation(self, client, recordist, capture):
        response = client.post(f"/api/captures/{capture['id']}/observations",
                               json={"body": "   "}, headers=recordist.headers)
        assert response.status_code == 400


class TestFamilyReplay:
    def test_a_replayed_family_create_returns_the_same_id(self, client, recordist):
        body = {"client_uuid": "fam-1", "name": "The Poe Family", "color": "#7cc4ff"}
        first = client.post("/api/families", json=body, headers=recordist.headers).get_json()
        again = client.post("/api/families", json=body, headers=recordist.headers).get_json()
        assert first["id"] == again["id"]

    def test_the_family_keeps_its_colour(self, client, recordist):
        """The glow on the map must not change under you between syncs."""
        created = client.post("/api/families",
                              json={"name": "The Poe Family", "color": "#7cc4ff"},
                              headers=recordist.headers).get_json()
        assert created["color"] == "#7cc4ff"

    def test_a_repushed_edit_updates_the_family(self, client, recordist):
        """The phone owns its families: a re-push with new notes is an edit."""
        body = {"client_uuid": "fam-2", "name": "The Scholars", "color": "#ffd166"}
        first = client.post("/api/families", json=body, headers=recordist.headers).get_json()
        edited = client.post(
            "/api/families",
            json={**body, "notes": "3 so far, looks like kids"},
            headers=recordist.headers).get_json()
        assert edited["id"] == first["id"]
        assert edited["notes"] == "3 so far, looks like kids"

    def test_a_family_with_no_name_is_refused(self, client, recordist):
        response = client.post("/api/families", json={"name": "  "},
                               headers=recordist.headers)
        assert response.status_code == 400

    def test_a_capture_may_have_no_family(self, client, recordist):
        created = client.post("/api/captures", json={"client_uuid": "nofam-1"},
                              headers=recordist.headers).get_json()
        assert created["family_id"] is None


LEGACY_SCHEMA = """
    CREATE TABLE devices (id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_uuid TEXT NOT NULL UNIQUE, contributor_name TEXT,
        token_hash TEXT NOT NULL UNIQUE, locale TEXT, platform TEXT,
        is_operator INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        last_seen_at TEXT);
    CREATE TABLE captures (id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        latitude REAL, longitude REAL, location_name TEXT, recorded_at TEXT,
        duration_sec REAL, notes TEXT, family_id INTEGER, sighting_id INTEGER,
        status TEXT NOT NULL DEFAULT 'recording', created_at TEXT NOT NULL);
    INSERT INTO devices (device_uuid, contributor_name, token_hash, created_at)
        VALUES ('u', 'legacy', 'h', '2026-01-01');
    INSERT INTO captures (device_id, notes, created_at)
        VALUES (1, 'pre-existing', '2026-01-01');
"""


class TestMigrationFromBeforeClientUuid:
    @pytest.fixture
    def legacy_db(self, tmp_path):
        path = tmp_path / "old.db"
        with sqlite3.connect(path) as conn:
            conn.executescript(LEGACY_SCHEMA)
        create_app(path)
        return path

    def test_the_column_is_added(self, legacy_db):
        with sqlite3.connect(legacy_db) as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(captures)")}
        assert "client_uuid" in columns

    def test_the_pre_existing_capture_survives(self, legacy_db):
        with sqlite3.connect(legacy_db) as conn:
            notes = conn.execute("SELECT notes FROM captures").fetchone()[0]
        assert notes == "pre-existing"

    def test_the_migrated_database_enforces_idempotency(self, legacy_db):
        client = create_app(legacy_db).test_client()
        token = client.post("/api/devices/register",
                            json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                  "contributor_name": "New"}).get_json()["device_token"]
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post("/api/captures", json={"client_uuid": "mig-1"},
                            headers=headers).get_json()
        again = client.post("/api/captures", json={"client_uuid": "mig-1"},
                            headers=headers).get_json()
        assert first["id"] == again["id"]


class TestLabelReplay:
    """Field labels push on the next sync, so a retry is routine.

    Without a key a dropped response duplicates the label — and a duplicated
    label is a training example counted twice, which is worse than a duplicated
    capture because nothing downstream can tell.
    """

    @pytest.fixture
    def labelled(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                              headers=recordist.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "med-1"},
                            headers=recordist.headers).get_json()
        client.put(f"/api/media/{media['id']}", data=b"xyz",
                   headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
        return capture

    def post(self, client, recordist, capture, **body):
        return client.post(f"/api/captures/{capture['id']}/labels",
                           json={"client_uuid": "lab-1", "call_type": "rattle",
                                 "start_sec": 4.0, "end_sec": 6.0, **body},
                           headers=recordist.headers)

    def test_a_label_is_recorded(self, client, recordist, labelled):
        label = self.post(client, recordist, labelled).get_json()
        assert label["call_type"] == "rattle"
        assert (label["start_sec"], label["end_sec"]) == (4.0, 6.0)

    def test_the_species_defaults(self, client, recordist, labelled):
        # The fleet records one species today; a tap in the field shouldn't have
        # to restate it.
        label = self.post(client, recordist, labelled).get_json()
        assert label["species"] == "American Crow"

    def test_a_replay_does_not_duplicate(self, client, recordist, labelled):
        first = self.post(client, recordist, labelled).get_json()
        again = self.post(client, recordist, labelled).get_json()
        assert first["id"] == again["id"]
        listed = client.get(f"/api/captures/{labelled['id']}/labels",
                            headers=recordist.headers).get_json()
        assert len(listed) == 1

    def test_a_replay_carries_a_correction(self, client, recordist, labelled):
        # Corrected before the push landed: storing both answers would put two
        # contradictory examples into the manifest.
        self.post(client, recordist, labelled)
        corrected = self.post(client, recordist, labelled, call_type="alarm call").get_json()
        assert corrected["call_type"] == "alarm call"
        listed = client.get(f"/api/captures/{labelled['id']}/labels",
                            headers=recordist.headers).get_json()
        assert len(listed) == 1

    def test_an_unknown_call_type_is_refused(self, client, recordist, labelled):
        # The vocabulary is server-defined; accepting anything would let a stale
        # app write labels no model head knows about.
        response = self.post(client, recordist, labelled, call_type="honk")
        assert response.status_code == 400

    def test_a_label_can_be_retracted(self, client, recordist, labelled):
        label = self.post(client, recordist, labelled).get_json()
        assert client.delete(f"/api/labels/{label['id']}",
                             headers=recordist.headers).status_code == 204
        listed = client.get(f"/api/captures/{labelled['id']}/labels",
                            headers=recordist.headers).get_json()
        assert listed == []

    def test_another_persons_label_cannot_be_retracted(
            self, client, recordist, stranger, labelled):
        label = self.post(client, recordist, labelled).get_json()
        response = client.delete(f"/api/labels/{label['id']}", headers=stranger.headers)
        assert response.status_code == 403

    def test_labelling_needs_uploaded_audio(self, client, recordist):
        # A label names a span of a recording; without one there is nothing for
        # it to point at.
        capture = client.post("/api/captures", json={"client_uuid": "bare"},
                              headers=recordist.headers).get_json()
        response = client.post(f"/api/captures/{capture['id']}/labels",
                               json={"call_type": "call"}, headers=recordist.headers)
        assert response.status_code == 409
