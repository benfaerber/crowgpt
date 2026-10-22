"""A person, not a handset, owns what they collect.

The bug this layer exists to kill: identity used to be the device row, so a
reinstall minted a new contributor and stranded everything the old one owned. One
recordist ended up as six rows holding a sixth of their own corpus each, and two
phones could not see each other's families.
"""

import sqlite3

import pytest

from fieldserver.app import DEFAULT_ENROLL_TOKEN, DEFAULT_OPERATOR_TOKEN, create_app
from fieldserver.stores.contributors import ContributorStore


class TestEnrollment:
    def test_creates_a_contributor(self, recordist):
        assert recordist.contributor["display_name"] == "Ben"
        assert recordist.contributor["role"] == "contributor"
        assert recordist.contributor["status"] == "active"

    def test_identifies_people_by_uuid_not_row_id(self, recordist):
        """A public dataset quotes this; a sequential id leaks the roster size."""
        assert len(recordist.contributor["public_uuid"]) == 32

    def test_hands_back_a_claim_code_once(self, recordist):
        assert recordist.claim_code

    def test_records_the_device_name(self, recordist):
        assert recordist.device["label"] == "Pixel 10"

    def test_never_exposes_the_claim_code_hash(self, recordist):
        assert "claim_code_hash" not in recordist.contributor


class TestSecondDevice:
    """The two-phone case: one person, two handsets, one corpus."""

    @pytest.fixture
    def pixel8(self, enroll, recordist):
        return enroll(claim_code=recordist.claim_code, label="Pixel 8",
                      platform="android")

    def test_a_claim_code_joins_the_existing_contributor(self, recordist, pixel8):
        assert pixel8.contributor["id"] == recordist.contributor["id"]

    def test_a_joined_device_gets_no_second_claim_code(self, pixel8):
        assert pixel8.claim_code is None

    def test_a_wrong_claim_code_is_refused(self, client):
        response = client.post("/api/devices/register",
                               json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                     "claim_code": "not-a-code"})
        assert response.status_code == 403

    def test_me_lists_every_phone(self, client, pixel8):
        me = client.get("/api/me", headers=pixel8.headers).get_json()
        assert sorted(d["label"] for d in me["devices"]) == ["Pixel 10", "Pixel 8"]

    def test_a_family_made_on_one_phone_is_visible_on_the_other(
            self, client, recordist, pixel8):
        family = client.post("/api/families",
                             json={"name": "The Poe Family", "client_uuid": "fam-1"},
                             headers=recordist.headers).get_json()
        visible = client.get("/api/families", headers=pixel8.headers).get_json()
        assert [f["id"] for f in visible] == [family["id"]]

    def test_either_phone_can_attach_a_capture_to_that_family(
            self, client, recordist, pixel8):
        family = client.post("/api/families", json={"name": "The Poe Family"},
                             headers=recordist.headers).get_json()
        created = client.post("/api/captures",
                              json={"client_uuid": "cap-1", "family_id": family["id"]},
                              headers=pixel8.headers)
        assert created.status_code == 201

    def test_a_capture_taken_on_one_phone_is_listed_on_the_other(
            self, client, recordist, pixel8):
        client.post("/api/captures", json={"client_uuid": "cap-1"},
                    headers=pixel8.headers)
        listed = client.get("/api/captures", headers=recordist.headers).get_json()
        assert [cap["client_uuid"] for cap in listed] == ["cap-1"]

    def test_but_still_records_which_phone_took_it(self, client, recordist, pixel8):
        """Merging ownership must not cost provenance."""
        client.post("/api/captures", json={"client_uuid": "cap-1"},
                    headers=pixel8.headers)
        capture = client.get("/api/captures", headers=recordist.headers).get_json()[0]
        assert capture["device_id"] == pixel8.device["id"]


class TestIsolationBetweenPeople:
    @pytest.fixture
    def family(self, client, recordist):
        return client.post("/api/families", json={"name": "The Poe Family"},
                           headers=recordist.headers).get_json()

    def test_a_stranger_sees_no_families(self, client, family, stranger):
        assert client.get("/api/families", headers=stranger.headers).get_json() == []

    def test_a_stranger_cannot_read_a_capture(self, client, recordist, stranger):
        capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                              headers=recordist.headers).get_json()
        response = client.get(f"/api/captures/{capture['id']}", headers=stranger.headers)
        assert response.status_code == 403

    def test_a_stranger_cannot_attach_to_another_persons_family(
            self, client, family, stranger):
        response = client.post("/api/captures",
                               json={"client_uuid": "x", "family_id": family["id"]},
                               headers=stranger.headers)
        assert response.status_code == 400

    def test_the_same_client_uuid_on_two_people_is_two_rows(
            self, client, recordist, stranger):
        mine = client.post("/api/captures", json={"client_uuid": "cap-1"},
                           headers=recordist.headers).get_json()
        theirs = client.post("/api/captures", json={"client_uuid": "cap-1"},
                             headers=stranger.headers).get_json()
        assert mine["id"] != theirs["id"]


class TestNaming:
    def test_a_device_can_be_renamed(self, client, recordist):
        renamed = client.patch(f"/api/devices/{recordist.device['id']}",
                               json={"label": "Old Pixel"},
                               headers=recordist.headers).get_json()
        assert renamed["label"] == "Old Pixel"

    def test_but_not_someone_elses(self, client, recordist, stranger):
        response = client.patch(f"/api/devices/{recordist.device['id']}",
                                json={"label": "mine now"}, headers=stranger.headers)
        assert response.status_code == 404

    def test_a_contributor_can_rename_themselves(self, client, recordist):
        renamed = client.patch("/api/me", json={"display_name": "Ben F"},
                               headers=recordist.headers).get_json()
        assert renamed["display_name"] == "Ben F"

    def test_an_empty_display_name_is_refused(self, client, recordist):
        response = client.patch("/api/me", json={"display_name": "   "},
                                headers=recordist.headers)
        assert response.status_code == 400

    def test_a_revoked_device_stops_authenticating(self, client, recordist, enroll):
        """Revoking keeps the row, and the captures it made stay attributed."""
        other = enroll(claim_code=recordist.claim_code, label="Pixel 8")
        client.patch(f"/api/devices/{other.device['id']}", json={"revoked": True},
                     headers=recordist.headers)
        assert client.get("/api/captures", headers=other.headers).status_code == 401


class TestClaimCodeRotation:
    def test_rotating_issues_a_different_code(self, client, recordist):
        rotated = client.post("/api/me/claim-code",
                              headers=recordist.headers).get_json()["claim_code"]
        assert rotated != recordist.claim_code

    def test_rotating_invalidates_the_old_code(self, client, recordist):
        client.post("/api/me/claim-code", headers=recordist.headers)
        response = client.post("/api/devices/register",
                               json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                     "claim_code": recordist.claim_code})
        assert response.status_code == 403

    def test_the_rotated_code_works(self, client, recordist, enroll):
        rotated = client.post("/api/me/claim-code",
                              headers=recordist.headers).get_json()["claim_code"]
        joined = enroll(claim_code=rotated, label="Pixel 8")
        assert joined.contributor["id"] == recordist.contributor["id"]


class TestRoles:
    def test_the_operator_token_mints_an_operator(self, operator):
        assert operator.contributor["role"] == "operator"

    @pytest.mark.parametrize("route", [
        "/api/fleet/summary", "/api/fleet/devices", "/api/fleet/captures",
        "/api/fleet/labels", "/api/fleet/contributors",
    ])
    def test_an_operator_reaches_every_fleet_route(self, client, operator, route):
        assert client.get(route, headers=operator.headers).status_code == 200

    @pytest.mark.parametrize("route", [
        "/api/fleet/summary", "/api/fleet/contributors",
    ])
    def test_a_contributor_reaches_none_of_them(self, client, recordist, route):
        assert client.get(route, headers=recordist.headers).status_code == 403

    def test_an_operator_cannot_change_roles(self, client, operator, stranger):
        """Reading the fleet and administering it are deliberately different."""
        response = client.patch(f"/api/fleet/contributors/{stranger.contributor['id']}",
                                json={"status": "suspended"}, headers=operator.headers)
        assert response.status_code == 403

    def test_an_admin_can_suspend_a_contributor(
            self, client, db_path, operator, stranger):
        ContributorStore(db_path).set_role(operator.contributor["id"], "admin")
        response = client.patch(f"/api/fleet/contributors/{stranger.contributor['id']}",
                                json={"status": "suspended"}, headers=operator.headers)
        assert response.status_code == 200

    def test_a_suspended_contributors_device_stops_authenticating(
            self, client, db_path, operator, stranger):
        ContributorStore(db_path).set_role(operator.contributor["id"], "admin")
        client.patch(f"/api/fleet/contributors/{stranger.contributor['id']}",
                     json={"status": "suspended"}, headers=operator.headers)
        assert client.get("/api/captures", headers=stranger.headers).status_code == 401

    def test_admin_cannot_be_granted_over_the_api(
            self, client, db_path, operator, stranger):
        """No TLS, shared secrets — an admin-minting route gives away the fleet."""
        ContributorStore(db_path).set_role(operator.contributor["id"], "admin")
        response = client.patch(f"/api/fleet/contributors/{stranger.contributor['id']}",
                                json={"role": "admin"}, headers=operator.headers)
        assert response.status_code == 403

    def test_an_unknown_role_is_refused(self, client, db_path, operator, stranger):
        ContributorStore(db_path).set_role(operator.contributor["id"], "admin")
        response = client.patch(f"/api/fleet/contributors/{stranger.contributor['id']}",
                                json={"role": "wizard"}, headers=operator.headers)
        assert response.status_code == 400


class TestOperatorSession:
    def test_signing_in_repeatedly_reuses_one_device(self, client, operator):
        """It used to mint a device per sign-in, each holding a live token forever."""
        before = len(client.get("/api/fleet/devices", headers=operator.headers).get_json())
        for _ in range(3):
            client.post("/api/operator/session",
                        json={"operator_token": DEFAULT_OPERATOR_TOKEN})
        after = client.get("/api/fleet/devices", headers=operator.headers).get_json()
        assert len(after) == before + 1

    def test_the_session_token_reads_the_fleet(self, client):
        token = client.post("/api/operator/session",
                            json={"operator_token": DEFAULT_OPERATOR_TOKEN},
                            ).get_json()["device_token"]
        response = client.get("/api/fleet/summary",
                              headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_rotation_invalidates_the_previous_session(self, client):
        first = client.post("/api/operator/session",
                            json={"operator_token": DEFAULT_OPERATOR_TOKEN},
                            ).get_json()["device_token"]
        client.post("/api/operator/session",
                    json={"operator_token": DEFAULT_OPERATOR_TOKEN})
        response = client.get("/api/fleet/summary",
                              headers={"Authorization": f"Bearer {first}"})
        assert response.status_code == 401

    def test_a_wrong_operator_token_mints_nothing(self, client):
        assert client.post("/api/operator/session",
                           json={"operator_token": "nope"}).status_code == 403


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
    INSERT INTO devices (device_uuid, contributor_name, token_hash, is_operator, created_at)
        VALUES ('u1', 'Unnamed recordist', 'h1', 0, '2026-01-01'),
               ('u2', 'Unnamed recordist', 'h2', 0, '2026-01-02'),
               ('u3', 'inspector', 'h3', 1, '2026-01-03');
    INSERT INTO captures (device_id, notes, created_at)
        VALUES (1, 'first', '2026-01-01'), (1, 'second', '2026-01-01'),
               (2, 'third', '2026-01-02');
"""


class TestMigration:
    """Three device rows that predate contributors entirely."""

    @pytest.fixture
    def legacy_db(self, tmp_path):
        path = tmp_path / "legacy.db"
        with sqlite3.connect(path) as conn:
            conn.executescript(LEGACY_SCHEMA)
        create_app(path)  # constructing the app runs the migration
        return path

    @pytest.fixture
    def rows(self, legacy_db):
        with sqlite3.connect(legacy_db) as conn:
            conn.row_factory = sqlite3.Row
            return {
                "people": [dict(r) for r in conn.execute(
                    "SELECT * FROM contributors ORDER BY id")],
                "owners": [r[0] for r in conn.execute(
                    "SELECT contributor_id FROM captures ORDER BY id")],
            }

    def test_every_legacy_device_gets_a_contributor(self, rows):
        assert len(rows["people"]) == 3

    def test_it_does_not_merge_people_it_cannot_know_are_the_same(self, rows):
        """Unattended migration cannot tell two phones from two humans, so it
        preserves the existing boundary and leaves merging to a deliberate act."""
        assert len(set(rows["owners"])) == 2

    def test_captures_follow_their_devices_new_owner(self, rows):
        assert rows["owners"] == [1, 1, 2]

    def test_an_operator_device_migrates_to_the_operator_role(self, rows):
        assert [p["role"] for p in rows["people"]] == [
            "contributor", "contributor", "operator"]

    def test_names_carry_over(self, rows):
        assert rows["people"][2]["display_name"] == "inspector"

    def test_the_columns_it_replaced_are_dropped(self, legacy_db):
        """Ownership and role live on the contributor now.

        Leaving `is_operator` on the device would be worse than untidy: it stays
        settable while meaning nothing, so a future reader could grant an
        operator flag that never takes effect.
        """
        with sqlite3.connect(legacy_db) as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(devices)")}
        assert "is_operator" not in columns
        assert "contributor_name" not in columns

    def test_sighting_id_is_dropped(self, legacy_db):
        with sqlite3.connect(legacy_db) as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(captures)")}
        assert "sighting_id" not in columns

    def test_migrating_twice_is_safe(self, legacy_db):
        """The second start has neither column to read or drop.

        Naming a missing column is an error even in a query that matches no
        rows, so the backfill has to look before it selects.
        """
        create_app(legacy_db)
        with sqlite3.connect(legacy_db) as conn:
            people = conn.execute("SELECT COUNT(*) FROM contributors").fetchone()[0]
        assert people == 3

    def test_a_migrated_database_still_enforces_idempotency(self, legacy_db):
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


class TestMerge:
    """The deliberate act that reunites a person fragmented across installs."""

    @pytest.fixture
    def legacy_db(self, tmp_path):
        path = tmp_path / "legacy.db"
        with sqlite3.connect(path) as conn:
            conn.executescript(LEGACY_SCHEMA)
        create_app(path)
        return path

    @pytest.fixture
    def merged(self, legacy_db):
        return ContributorStore(legacy_db).merge(keep_id=1, absorb_ids=[2, 3])

    def test_one_person_remains(self, legacy_db, merged):
        with sqlite3.connect(legacy_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM contributors").fetchone()[0] == 1

    def test_holding_every_capture(self, legacy_db, merged):
        with sqlite3.connect(legacy_db) as conn:
            owned = conn.execute(
                "SELECT COUNT(*) FROM captures WHERE contributor_id = 1").fetchone()[0]
        assert owned == 3

    def test_and_keeping_every_phone_they_recorded_on(self, legacy_db, merged):
        with sqlite3.connect(legacy_db) as conn:
            kept = conn.execute(
                "SELECT COUNT(*) FROM devices WHERE contributor_id = 1").fetchone()[0]
        assert kept == 3

    def test_it_reports_what_it_moved(self, merged):
        assert merged["moved"]["captures"] == 1
        assert merged["absorbed"] == [2, 3]

    def test_merging_into_an_unknown_contributor_is_refused(self, legacy_db):
        with pytest.raises(ValueError, match="no contributor"):
            ContributorStore(legacy_db).merge(keep_id=99, absorb_ids=[2])

    def test_merging_nothing_changes_nothing(self, legacy_db):
        result = ContributorStore(legacy_db).merge(keep_id=1, absorb_ids=[1])
        assert result["absorbed"] == []


class TestMergeMovesEveryReference:
    """Merging deletes the absorbed row, so every table pointing at it must
    move first. With foreign keys enforced, a table left behind does not
    orphan its rows — it aborts the DELETE and rolls the whole merge back.
    Three were left behind: context_events, sightings, and device_logs, whose
    contributor_id is NOT NULL — so anyone who had ever synced a log line
    could not be merged at all.
    """

    @pytest.fixture
    def keeper(self, enroll):
        return enroll(contributor_name="Ben, before the reinstall")

    @pytest.fixture
    def everything(self, client, recordist):
        """A row in each of the tables merge() used to leave behind."""
        capture = client.post("/api/captures", json={"client_uuid": "mrg-cap"},
                              headers=recordist.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "mrg-med"},
                            headers=recordist.headers).get_json()
        client.put(f"/api/media/{media['id']}", data=b"xyz",
                   headers={**recordist.headers, "Content-Range": "bytes 0-2/3"})
        label = client.post(f"/api/captures/{capture['id']}/labels",
                            json={"client_uuid": "mrg-lab", "call_type": "alarm call",
                                  "start_sec": 1.0, "end_sec": 2.0},
                            headers=recordist.headers).get_json()
        for response in (
            client.post(f"/api/captures/{capture['id']}/context",
                        json={"client_uuid": "mrg-ctx", "key": "dog_visible",
                              "label_id": label["id"]},
                        headers=recordist.headers),
            client.post(f"/api/captures/{capture['id']}/sightings",
                        json={"client_uuid": "mrg-sgt", "key": "raptor_overhead",
                              "offset_sec": 300},
                        headers=recordist.headers),
            client.post("/api/logs",
                        json={"entries": [{"client_uuid": "mrg-log",
                                           "at": "2026-07-30T10:00:00Z",
                                           "level": "error", "tag": "recorder",
                                           "message": "merge fodder"}]},
                        headers=recordist.headers),
        ):
            assert response.status_code < 300, response.get_data(as_text=True)
        return capture

    @pytest.fixture
    def merged(self, db_path, recordist, keeper, everything):
        return ContributorStore(db_path).merge(
            keep_id=keeper.contributor["id"],
            absorb_ids=[recordist.contributor["id"]])

    def test_the_merge_survives_them(self, merged, recordist):
        assert merged["absorbed"] == [recordist.contributor["id"]]

    def test_and_reports_each_one_moved(self, merged):
        assert merged["moved"]["context_events"] == 1
        assert merged["moved"]["sightings"] == 1
        assert merged["moved"]["device_logs"] == 1

    def test_nothing_is_left_pointing_at_the_deleted_row(
            self, db_path, merged, recordist):
        gone = recordist.contributor["id"]
        with sqlite3.connect(db_path) as conn:
            for table in ContributorStore.REFERENCING_TABLES:
                left = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE contributor_id = ?",
                    (gone,)).fetchone()[0]
                assert left == 0, table
