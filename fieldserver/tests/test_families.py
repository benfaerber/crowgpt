"""Families as something you can examine, not just attach a capture to.

A family is the unit that makes a corpus more than a pile of clips: the same
birds, the same territory, across months. The phone only knows the families it
created, so the questions worth asking — which family do we have most of, which
has gone quiet, what is this one heard saying — are fleet-shaped and live here.
"""

import sqlite3

import pytest

from fieldserver.stores.contributors import ContributorStore


@pytest.fixture
def admin(client, db_path, operator):
    ContributorStore(db_path).set_role(operator.contributor["id"], "admin")
    return operator


@pytest.fixture
def family(client, recordist):
    return client.post("/api/families",
                       json={"name": "The Poe Family", "color": "#8b5cf6",
                             "client_uuid": "fam-1", "notes": "corner of the block"},
                       headers=recordist.headers).get_json()


def add_capture(client, recordist, family_id, **fields):
    body = {"family_id": family_id, **fields}
    return client.post("/api/captures", json=body, headers=recordist.headers).get_json()


class TestFamilyRoster:
    def test_an_operator_can_list_families(self, client, family, operator):
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert [f["name"] for f in rows] == ["The Poe Family"]

    def test_a_plain_contributor_cannot(self, client, family, recordist):
        assert client.get("/api/fleet/families",
                          headers=recordist.headers).status_code == 403

    def test_the_roster_names_who_follows_the_family(self, client, family, operator):
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["contributor_name"] == "Ben"

    def test_it_keeps_the_colour_chosen_on_the_phone(self, client, family, operator):
        # The same colour the map glows with in the field app; recognising a
        # family at a glance is the whole job of that colour.
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["color"] == "#8b5cf6"

    def test_a_family_with_no_captures_still_appears(self, client, family, operator):
        # A LEFT JOIN, not an inner one: a family created in the field before
        # anything was recorded must not vanish from the roster.
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["capture_count"] == 0

    def test_it_counts_captures(self, client, recordist, family, operator):
        add_capture(client, recordist, family["id"], client_uuid="c1")
        add_capture(client, recordist, family["id"], client_uuid="c2")
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["capture_count"] == 2

    def test_it_reports_where_the_family_lives(self, client, recordist, family, operator):
        """The centroid is what turns a family into a place."""
        add_capture(client, recordist, family["id"], client_uuid="c1",
                    latitude=40.0, longitude=-111.0)
        add_capture(client, recordist, family["id"], client_uuid="c2",
                    latitude=41.0, longitude=-113.0)
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["latitude"] == pytest.approx(40.5)
        assert rows[0]["longitude"] == pytest.approx(-112.0)

    def test_it_reports_when_the_family_was_last_heard(
            self, client, recordist, family, operator):
        add_capture(client, recordist, family["id"], client_uuid="c1",
                    recorded_at="2026-03-01T10:00:00Z")
        add_capture(client, recordist, family["id"], client_uuid="c2",
                    recorded_at="2026-07-01T10:00:00Z")
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["first_heard"].startswith("2026-03")
        assert rows[0]["last_heard"].startswith("2026-07")

    def test_captures_from_two_people_do_not_merge(
            self, client, recordist, stranger, family, operator):
        """Two recordists watching "the pair on the corner" mean different birds."""
        theirs = client.post("/api/families", json={"name": "The Poe Family"},
                             headers=stranger.headers).get_json()
        add_capture(client, recordist, family["id"], client_uuid="mine")
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        by_id = {f["id"]: f for f in rows}
        assert by_id[family["id"]]["capture_count"] == 1
        assert by_id[theirs["id"]]["capture_count"] == 0


class TestTaggingAfterUpload:
    """Assigning a family to a capture the server already has.

    The common case, and the one that was broken: a family is chosen back at the
    desk, long after the audio landed. The create call was the only place
    `family_id` was ever sent, so a capture tagged afterwards re-synced forever
    and stayed unassigned — while the client's revision bookkeeping recorded the
    edit as delivered.
    """

    def test_a_family_can_be_attached_after_the_fact(
            self, client, recordist, family):
        capture = client.post("/api/captures", json={"client_uuid": "c1"},
                              headers=recordist.headers).get_json()
        assert capture["family_id"] is None

        updated = client.patch(f"/api/captures/{capture['id']}",
                               json={"family_id": family["id"]},
                               headers=recordist.headers).get_json()
        assert updated["family_id"] == family["id"]

    def test_the_family_roster_then_counts_it(
            self, client, recordist, family, operator):
        capture = client.post("/api/captures", json={"client_uuid": "c1"},
                              headers=recordist.headers).get_json()
        client.patch(f"/api/captures/{capture['id']}", json={"family_id": family["id"]},
                     headers=recordist.headers)
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["capture_count"] == 1

    def test_a_capture_can_be_named_at_creation(self, client, recordist):
        capture = client.post("/api/captures",
                              json={"client_uuid": "c1", "name": "Edgar on the wire"},
                              headers=recordist.headers).get_json()
        assert capture["name"] == "Edgar on the wire"

    def test_a_capture_can_be_named_afterwards(self, client, recordist):
        # The usual case — naming happens at the desk, not while recording.
        capture = client.post("/api/captures", json={"client_uuid": "c1"},
                              headers=recordist.headers).get_json()
        assert capture["name"] is None
        renamed = client.patch(f"/api/captures/{capture['id']}",
                               json={"name": "the mobbing"},
                               headers=recordist.headers).get_json()
        assert renamed["name"] == "the mobbing"

    def test_notes_and_location_can_be_corrected(self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "c1"},
                              headers=recordist.headers).get_json()
        updated = client.patch(f"/api/captures/{capture['id']}",
                               json={"notes": "two returned four minutes later",
                                     "location_name": "Liberty Park"},
                               headers=recordist.headers).get_json()
        assert updated["notes"] == "two returned four minutes later"
        assert updated["location_name"] == "Liberty Park"

    def test_the_recording_itself_cannot_be_rewritten(self, client, recordist):
        # recorded_at and duration describe the audio; a client that could
        # rewrite them could rewrite history.
        capture = client.post("/api/captures",
                              json={"client_uuid": "c1", "duration_sec": 12.5,
                                    "recorded_at": "2026-07-01T10:00:00Z"},
                              headers=recordist.headers).get_json()
        updated = client.patch(f"/api/captures/{capture['id']}",
                               json={"duration_sec": 999, "recorded_at": "2020-01-01"},
                               headers=recordist.headers).get_json()
        assert updated["duration_sec"] == 12.5
        assert updated["recorded_at"] == "2026-07-01T10:00:00Z"

    def test_another_persons_family_is_refused(
            self, client, recordist, stranger, family):
        theirs = client.post("/api/captures", json={"client_uuid": "c1"},
                             headers=stranger.headers).get_json()
        response = client.patch(f"/api/captures/{theirs['id']}",
                                json={"family_id": family["id"]},
                                headers=stranger.headers)
        assert response.status_code == 400

    def test_another_persons_capture_is_refused(
            self, client, recordist, stranger, family):
        mine = client.post("/api/captures", json={"client_uuid": "c1"},
                           headers=recordist.headers).get_json()
        response = client.patch(f"/api/captures/{mine['id']}",
                                json={"notes": "not yours"},
                                headers=stranger.headers)
        assert response.status_code == 403

    def test_an_empty_patch_changes_nothing(self, client, recordist, family):
        capture = client.post("/api/captures",
                              json={"client_uuid": "c1", "notes": "kept"},
                              headers=recordist.headers).get_json()
        updated = client.patch(f"/api/captures/{capture['id']}", json={},
                               headers=recordist.headers).get_json()
        assert updated["notes"] == "kept"


class TestFamilyDetail:
    def test_an_unknown_family_is_404(self, client, operator):
        assert client.get("/api/fleet/families/999",
                          headers=operator.headers).status_code == 404

    def test_it_lists_the_family_captures(self, client, recordist, family, operator):
        add_capture(client, recordist, family["id"], client_uuid="c1")
        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        assert len(detail["captures"]) == 1

    def test_it_excludes_captures_of_other_families(
            self, client, recordist, family, operator):
        other = client.post("/api/families", json={"name": "The Ravens"},
                            headers=recordist.headers).get_json()
        mine = add_capture(client, recordist, family["id"], client_uuid="mine")
        add_capture(client, recordist, other["id"], client_uuid="theirs")
        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        assert [c["id"] for c in detail["captures"]] == [mine["id"]]

    def test_it_carries_the_notes(self, client, family, operator):
        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        assert detail["family"]["notes"] == "corner of the block"

    def test_a_contributor_cannot_read_it(self, client, family, recordist):
        assert client.get(f"/api/fleet/families/{family['id']}",
                          headers=recordist.headers).status_code == 403


class TestVocalProfile:
    """What a family is heard saying — the first view whose subject is a family."""

    def analyze(self, db_path, capture_id, calls, media_id=1):
        """Write a finished analysis directly; the worker is not under test here."""
        with sqlite3.connect(db_path) as conn:
            job = conn.execute(
                "INSERT INTO analysis_jobs (capture_id, media_id, state, created_at) "
                "VALUES (?, ?, 'done', '2026-07-01T00:00:00Z')",
                (capture_id, media_id))
            result = conn.execute(
                "INSERT INTO analysis_results (job_id, capture_id, model_version, "
                "created_at) VALUES (?, ?, 'test', '2026-07-01T00:00:00Z')",
                (job.lastrowid, capture_id))
            for species, call_type, confidence in calls:
                conn.execute(
                    "INSERT INTO detected_calls (analysis_id, start_sec, end_sec, "
                    "species, call_type, confidence) VALUES (?, 0, 1, ?, ?, ?)",
                    (result.lastrowid, species, call_type, confidence))

    def test_it_groups_by_species_and_call_type(
            self, client, db_path, recordist, family, operator):
        capture = add_capture(client, recordist, family["id"], client_uuid="c1")
        self.analyze(db_path, capture["id"], [
            ("American Crow", "caw", 0.9),
            ("American Crow", "caw", 0.7),
            ("American Crow", "rattle", 0.6),
        ])
        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        profile = {t["call_type"]: t for t in detail["call_types"]}
        assert profile["caw"]["n"] == 2
        assert profile["caw"]["mean_confidence"] == pytest.approx(0.8)
        assert profile["rattle"]["n"] == 1

    def test_a_reanalyzed_capture_is_not_counted_twice(
            self, client, db_path, recordist, family, operator):
        """Only the latest analysis per capture counts.

        A capture reprocessed after a model update would otherwise contribute
        twice, quietly making whichever clips were reprocessed look like the
        family's favourite call.
        """
        capture = add_capture(client, recordist, family["id"], client_uuid="c1")
        self.analyze(db_path, capture["id"], [("American Crow", "caw", 0.5)])
        self.analyze(db_path, capture["id"], [("American Crow", "caw", 0.9)])

        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        assert [t["n"] for t in detail["call_types"]] == [1]
        assert detail["call_types"][0]["mean_confidence"] == pytest.approx(0.9)

    def test_calls_from_another_family_are_excluded(
            self, client, db_path, recordist, family, operator):
        other = client.post("/api/families", json={"name": "The Ravens"},
                            headers=recordist.headers).get_json()
        mine = add_capture(client, recordist, family["id"], client_uuid="c1")
        theirs = add_capture(client, recordist, other["id"], client_uuid="c2")
        self.analyze(db_path, mine["id"], [("American Crow", "caw", 0.9)])
        self.analyze(db_path, theirs["id"], [("American Crow", "growl", 0.9)])

        detail = client.get(f"/api/fleet/families/{family['id']}",
                            headers=operator.headers).get_json()
        assert [t["call_type"] for t in detail["call_types"]] == ["caw"]

    def test_the_roster_call_count_matches(
            self, client, db_path, recordist, family, operator):
        capture = add_capture(client, recordist, family["id"], client_uuid="c1")
        self.analyze(db_path, capture["id"], [
            ("American Crow", "caw", 0.9), ("American Crow", "rattle", 0.6),
        ])
        rows = client.get("/api/fleet/families", headers=operator.headers).get_json()
        assert rows[0]["call_count"] == 2


class TestServedCallColors:
    """One colour per core class, served rather than hardcoded by each client.

    A rattle that is amber on the phone and blue in the dashboard is a real bug
    in a labelling tool, and nothing but a shared source prevents it. Colouring
    the *core* rather than the key also means a label added by a config push
    gets a sensible colour without anyone choosing one.
    """

    def test_the_config_serves_a_colour_per_core_class(self, client):
        config = client.get("/api/config?locale=en").get_json()
        assert set(config["core_colors"]) == set(config["core_classes"])

    def test_every_trainable_label_resolves_to_a_colour_through_its_core(self, client):
        config = client.get("/api/config?locale=en").get_json()
        for label in config["labels"]:
            if not label["trains"]:
                continue  # "not a crow" is not a call type and has no core colour
            assert label["core"] in config["core_colors"], label["key"]

    def test_a_judgement_has_no_core_colour_to_borrow(self, client):
        # Colouring it like a call type would imply a classification we are
        # explicitly declining to make.
        config = client.get("/api/config?locale=en").get_json()
        rejection = next(l for l in config["labels"] if l["key"] == "not_a_crow")
        assert rejection["core"] not in config["core_colors"]

