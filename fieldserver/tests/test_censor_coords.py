"""What is recorded, and separately what is shown.

One three-way setting was carrying two questions. `exact_private` meant
"coordinates recorded and synced, but every screen says the region" — a display
choice wearing a recording choice's clothes, which is why it needed a sentence
to explain itself.

The migration is the part worth testing hardest. Somebody on `exact_private`
asked for coordinates to be kept and never shown, so they must land on exact +
censor ON. Landing them on plain exact would publish a home address on a screen
that had been deliberately hiding it — the one failure this setting exists to
prevent, caused by the change meant to clarify it.
"""

import sqlite3

import pytest

from fieldserver.core import schema
from fieldserver.stores.contributors import LOCATION_PRECISIONS


class TestTheTwoQuestionsAreSeparate:
    def test_the_middle_value_is_gone_from_the_choices(self):
        # `fuzzed` is not it returning: exact_private answered "may they be
        # shown", which is censor_coords's question now. fuzzed answers "how
        # coarsely are they recorded", which is this setting's own.
        assert LOCATION_PRECISIONS == ("exact", "fuzzed", "region")

    def test_coordinates_can_be_recorded_and_hidden(self, client, recordist):
        r = client.patch("/api/me/location-precision",
                         json={"location_precision": "exact", "censor_coords": True},
                         headers=recordist.headers)
        assert r.status_code == 200
        me = r.get_json()
        assert me["location_precision"] == "exact"
        assert me["censor_coords"] == 1

    def test_coordinates_can_be_recorded_and_shown(self, client, recordist):
        me = client.patch("/api/me/location-precision",
                          json={"location_precision": "exact", "censor_coords": False},
                          headers=recordist.headers).get_json()
        assert me["censor_coords"] == 0

    def test_region_only_still_works(self, client, recordist):
        me = client.patch("/api/me/location-precision",
                          json={"location_precision": "region", "region": "Utah"},
                          headers=recordist.headers).get_json()
        assert me["location_precision"] == "region"


class TestAClientThatHasNotBeenUpdated:
    def test_the_pre_split_value_is_refused(self, client, recordist):
        """`exact_private` stopped being accepted 2026-08-09.

        Revision 0013 rewrote every stored row and no build still on a phone
        can send it, so a client that does has genuinely gone wrong. Refusal
        fails closed: the 400 leaves whatever masking was stored exactly as
        it was.
        """
        client.patch("/api/me/location-precision",
                     json={"location_precision": "exact", "censor_coords": True},
                     headers=recordist.headers)
        response = client.patch("/api/me/location-precision",
                                json={"location_precision": "exact_private"},
                                headers=recordist.headers)
        assert response.status_code == 400
        me = client.patch("/api/me/location-precision",
                          json={"location_precision": "exact"},
                          headers=recordist.headers).get_json()
        assert me["censor_coords"] == 1

    def test_omitting_the_field_does_not_clear_masking(self, client, recordist):
        """The dangerous case: an old client writes precision and nothing else.

        If a missing `censor_coords` read as false, any phone that had not been
        updated would silently unmask its owner on the next settings write.
        """
        client.patch("/api/me/location-precision",
                     json={"location_precision": "exact", "censor_coords": True},
                     headers=recordist.headers)
        me = client.patch("/api/me/location-precision",
                          json={"location_precision": "exact"},
                          headers=recordist.headers).get_json()
        assert me["censor_coords"] == 1, "masking was silently turned off"

    def test_an_unknown_precision_is_still_refused(self, client, recordist):
        r = client.patch("/api/me/location-precision",
                         json={"location_precision": "roughly"},
                         headers=recordist.headers)
        assert r.status_code == 400


class TestTheMigration:
    def test_exact_private_becomes_exact_and_censored(self, tmp_path):
        """The whole point of the revision, run against a pre-change database."""
        db = tmp_path / "old.db"
        schema.upgrade_to(db, "0012_capture_merges")
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO contributors (public_uuid, display_name, role, status, "
                "location_precision, created_at) "
                "VALUES ('u-1', 'Private', 'recordist', 'active', "
                "'exact_private', '2026-07-01')")
            conn.execute(
                "INSERT INTO contributors (public_uuid, display_name, role, status, "
                "location_precision, created_at) "
                "VALUES ('u-2', 'Open', 'recordist', 'active', 'exact', '2026-07-01')")
            conn.execute(
                "INSERT INTO contributors (public_uuid, display_name, role, status, "
                "location_precision, created_at) "
                "VALUES ('u-3', 'Vague', 'recordist', 'active', 'region', '2026-07-01')")

        schema.upgrade(db)

        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = {r["public_uuid"]: dict(r) for r in
                    conn.execute("SELECT public_uuid, location_precision, "
                                 "censor_coords FROM contributors")}

        assert rows["u-1"]["location_precision"] == "exact"
        assert rows["u-1"]["censor_coords"] == 1, \
            "somebody who hid their coordinates must stay hidden"
        # Nobody is moved the other way.
        assert rows["u-2"]["censor_coords"] == 0
        assert rows["u-3"]["location_precision"] == "region"
        assert rows["u-3"]["censor_coords"] == 0

    def test_nothing_is_left_on_the_old_value(self, tmp_path):
        db = tmp_path / "old.db"
        schema.upgrade_to(db, "0012_capture_merges")
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO contributors (public_uuid, display_name, role, status, "
                "location_precision, created_at) VALUES "
                "('u-1', 'A', 'recordist', 'active', 'exact_private', '2026-07-01')")
        schema.upgrade(db)
        with sqlite3.connect(db) as conn:
            left = conn.execute(
                "SELECT COUNT(*) FROM contributors "
                "WHERE location_precision = 'exact_private'").fetchone()[0]
        assert left == 0

    def test_the_live_database_agrees_with_the_migrations(self, db_path):
        assert schema.drift(db_path) == []


class TestTheDashboardIsToldEnoughToMask:
    """Every row that reaches describePlace must carry both halves.

    The dashboard decides masking per query on purpose — its own comment says
    "masking decided per panel is how three of them honour the setting and the
    fourth quietly does not". That is a design that needs a test, and it earned
    one: `family_captures` selected coordinates without any precision at all, so
    it printed them whatever the recordist had chosen.
    """

    BOTH = ("location_precision", "censor_coords")

    @pytest.fixture
    def board(self, db_path):
        from fieldserver.stores.dashboard import DashboardQueries
        return DashboardQueries(db_path)

    @pytest.fixture
    def capture_id(self, client, recordist):
        return client.post("/api/captures", json={"client_uuid": "c-1"},
                           headers=recordist.headers).get_json()["id"]

    def test_the_capture_list_carries_both(self, board, capture_id):
        row = board.captures(limit=50)[0]
        for field in self.BOTH:
            assert field in row, f"the capture list cannot mask without {field}"

    def test_one_capture_carries_both(self, board, capture_id):
        row = board.capture(capture_id)
        for field in self.BOTH:
            assert field in row, f"capture detail cannot mask without {field}"

    def test_family_captures_carry_both(self, board, client, recordist, capture_id):
        family = client.post("/api/families", json={"name": "The Poe Family",
                                                    "client_uuid": "f-1"},
                             headers=recordist.headers).get_json()
        client.patch(f"/api/captures/{capture_id}",
                     json={"family_id": family["id"]}, headers=recordist.headers)
        rows = board.family_captures(family["id"])
        assert rows, "expected the capture to be in the family"
        for field in self.BOTH:
            assert field in rows[0], f"the family panel cannot mask without {field}"


class TestTheServerMasksCoordinatesOnRead:
    """The promise the UI makes is kept by the API, not just the client.

    `censor_coords` means recorded-never-shown. The fleet read endpoints used to
    ship the raw fix and trust the browser to hide it, so a curl with an operator
    token read the coordinate a recordist asked to mask. The coordinates must
    leave the server already blanked; the flag stays so the client can say why.
    """

    @pytest.fixture
    def board(self, db_path):
        from fieldserver.stores.dashboard import DashboardQueries
        return DashboardQueries(db_path)

    @pytest.fixture
    def censored_capture(self, client, recordist):
        client.patch("/api/me/location-precision",
                     json={"location_precision": "exact", "censor_coords": True},
                     headers=recordist.headers)
        return client.post("/api/captures",
                           json={"client_uuid": "c-mask", "latitude": 40.76,
                                 "longitude": -111.89},
                           headers=recordist.headers).get_json()["id"]

    def test_the_capture_list_blanks_the_fix(self, board, censored_capture):
        row = next(r for r in board.captures(limit=50) if r["id"] == censored_capture)
        assert row["censor_coords"] == 1
        assert row["latitude"] is None and row["longitude"] is None, \
            "a censored recordist's exact fix left the server"

    def test_capture_detail_blanks_the_fix(self, board, censored_capture):
        row = board.capture(censored_capture)
        assert row["latitude"] is None and row["longitude"] is None

    def test_an_uncensored_capture_keeps_its_fix(self, client, recordist, board):
        client.patch("/api/me/location-precision",
                     json={"location_precision": "exact", "censor_coords": False},
                     headers=recordist.headers)
        cid = client.post("/api/captures",
                          json={"client_uuid": "c-shown", "latitude": 40.76,
                                "longitude": -111.89},
                          headers=recordist.headers).get_json()["id"]
        row = board.capture(cid)
        assert row["latitude"] == pytest.approx(40.76), \
            "masking must not swallow a fix the recordist chose to show"

    def test_the_family_centroid_is_blanked(self, board, client, recordist, censored_capture):
        family = client.post("/api/families",
                             json={"name": "Masked", "client_uuid": "f-mask"},
                             headers=recordist.headers).get_json()
        client.patch(f"/api/captures/{censored_capture}",
                     json={"family_id": family["id"]}, headers=recordist.headers)
        row = next(r for r in board.families() if r["id"] == family["id"])
        assert row["latitude"] is None, \
            "a one-capture family's centroid is that capture's exact fix"
