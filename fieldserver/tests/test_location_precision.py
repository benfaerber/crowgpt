"""How precisely a contributor is willing to say where they were.

A crow corpus is a map of where one person walks: forty captures with fixes
describe a home, a commute and a routine. Coordinates are also genuinely needed
— BirdNET's species filter takes lat/lon — so this is a choice rather than a
policy, and these tests are about the choice being honoured.

Enforcement lives on the phone, which is the only place it can be enforced.
This end refuses coordinates from a region-only contributor anyway: a promise
kept in two places is worth more than one kept in either.
"""

import math

import pytest

from fieldserver.core.coords import fuzz_coords


def capture(client, who, **body):
    return client.post("/api/captures",
                       json={"client_uuid": "cap-1", **body},
                       headers=who.headers).get_json()


def miles_between(a, b):
    """Haversine, in miles — how far the snap actually moved a point."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 3958.8 * math.asin(math.sqrt(h))


class TestChoosing:

    def test_a_new_contributor_starts_exact(self, recordist):
        # Every row that already exists was recorded under that understanding,
        # and defaulting the other way would relabel data rather than protect
        # anybody.
        assert recordist.contributor["location_precision"] == "exact"

    def test_setting_it_from_your_own_phone(self, client, recordist):
        answer = client.patch("/api/me/location-precision",
                              json={"location_precision": "region",
                                    "region": "Utah, US"},
                              headers=recordist.headers)
        assert answer.status_code == 200
        assert answer.get_json()["location_precision"] == "region"
        assert answer.get_json()["region"] == "Utah, US"

    def test_an_unknown_precision_is_refused(self, client, recordist):
        answer = client.patch("/api/me/location-precision",
                              json={"location_precision": "vague"},
                              headers=recordist.headers)
        assert answer.status_code == 400

    def test_the_region_survives_a_later_change_of_precision(self, client, recordist):
        client.patch("/api/me/location-precision",
                     json={"location_precision": "region", "region": "Utah, US"},
                     headers=recordist.headers)
        answer = client.patch("/api/me/location-precision",
                              json={"location_precision": "exact"},
                              headers=recordist.headers)
        assert answer.get_json()["region"] == "Utah, US"


class TestWhatGetsStored:

    def test_exact_keeps_the_coordinates(self, client, recordist):
        row = capture(client, recordist, latitude=40.7460, longitude=-111.8747)
        assert row["latitude"] == pytest.approx(40.7460)

    def test_region_only_refuses_them_even_when_sent(self, client, recordist):
        # The phone should never send these. If one does — an old build, a bug,
        # a client someone else wrote — the contributor's choice still holds.
        client.patch("/api/me/location-precision",
                     json={"location_precision": "region", "region": "Utah, US"},
                     headers=recordist.headers)

        row = capture(client, recordist, latitude=40.7460, longitude=-111.8747)

        assert row["latitude"] is None
        assert row["longitude"] is None
        assert row["region"] == "Utah, US"

    def test_censored_exact_still_stores_them(self, client, recordist):
        # The distinction is about showing, not about keeping: these captures
        # are still wanted for territory work, they are simply not for display.
        client.patch("/api/me/location-precision",
                     json={"location_precision": "exact", "censor_coords": True,
                           "region": "Utah, US"},
                     headers=recordist.headers)

        row = capture(client, recordist, latitude=40.7460, longitude=-111.8747)

        assert row["latitude"] == pytest.approx(40.7460)
        assert row["region"] == "Utah, US"

    def test_a_capture_says_where_it_was_when_it_differs_from_home(
            self, client, recordist):
        # A recordist in Utah on a trip to Idaho: the capture's own region wins,
        # or the corpus quietly claims every recording happened at home.
        client.patch("/api/me/location-precision",
                     json={"location_precision": "region", "region": "Utah, US"},
                     headers=recordist.headers)

        row = capture(client, recordist, region="Idaho, US")

        assert row["region"] == "Idaho, US"

    def test_what_was_already_sent_stays_sent(self, client, recordist):
        """Tightening the setting is not retroactive, on purpose.

        There is no scrub route and there should not be one: a corpus where any
        contributor can reach back and empty fields out of rows other people
        have already analysed is one where no result can be reproduced. The
        setting governs what is sent next, and a genuine deletion request is an
        operator action, out of band, not an API anyone can call.
        """
        row = capture(client, recordist, latitude=40.7460, longitude=-111.8747)

        client.patch("/api/me/location-precision",
                     json={"location_precision": "region", "region": "Utah, US"},
                     headers=recordist.headers)

        after = client.get(f"/api/captures/{row['id']}",
                           headers=recordist.headers).get_json()
        assert after["latitude"] == pytest.approx(40.7460)


class TestEditingAfterwards:
    """The backstop has to hold on the edit path too.

    Enforcing it only on create honoured the setting exactly until somebody
    tapped twice: coordinates were refused on the way in, then accepted by a
    PATCH a moment later.
    """

    @pytest.fixture
    def region_only(self, client, recordist):
        client.patch("/api/me/location-precision",
                     json={"location_precision": "region", "region": "Utah, US"},
                     headers=recordist.headers)
        return capture(client, recordist)

    def test_a_patch_cannot_put_coordinates_back(self, client, recordist,
                                                 region_only):
        answer = client.patch(f"/api/captures/{region_only['id']}",
                              json={"latitude": 40.7460, "longitude": -111.8747},
                              headers=recordist.headers)

        assert answer.status_code == 200
        assert answer.get_json()["latitude"] is None
        assert answer.get_json()["longitude"] is None

    def test_and_it_is_not_stored_either(self, client, recordist, region_only):
        client.patch(f"/api/captures/{region_only['id']}",
                     json={"latitude": 40.7460, "longitude": -111.8747},
                     headers=recordist.headers)

        after = client.get(f"/api/captures/{region_only['id']}",
                           headers=recordist.headers).get_json()
        assert after["latitude"] is None

    def test_the_rest_of_the_edit_still_lands(self, client, recordist, region_only):
        # Refusing the coordinates must not refuse the note they arrived with:
        # the setting is about place, and dropping the edit would cost a real
        # correction to make a point.
        answer = client.patch(f"/api/captures/{region_only['id']}",
                              json={"latitude": 40.7460, "notes": "two fledglings"},
                              headers=recordist.headers)

        assert answer.get_json()["notes"] == "two fledglings"
        assert answer.get_json()["latitude"] is None

    def test_an_exact_contributor_may_still_edit_theirs(self, client, recordist):
        row = capture(client, recordist)
        answer = client.patch(f"/api/captures/{row['id']}",
                              json={"latitude": 40.7460, "longitude": -111.8747},
                              headers=recordist.headers)

        assert answer.get_json()["latitude"] == pytest.approx(40.7460)


class TestSnapping:
    """The grid itself, before any route touches it.

    A grid rather than jitter, because jitter fails exactly the person it
    protects: fifty captures at home, each displaced independently, average
    straight back to the house.
    """

    HOME = (40.7460, -111.8747)

    def test_the_point_moves_but_stays_within_the_radius(self):
        snapped = fuzz_coords(*self.HOME, miles=5)
        assert snapped != self.HOME
        assert miles_between(self.HOME, snapped) <= 5

    def test_snapping_is_idempotent(self):
        # What lets the server re-snap whatever arrives: coordinates the phone
        # already snapped pass through unmoved.
        once = fuzz_coords(*self.HOME, miles=5)
        assert fuzz_coords(*once, miles=5) == once

    def test_neighbours_land_on_the_same_point(self):
        # The anti-averaging property. Two fixes a garden apart must publish
        # the same point, or repetition narrows the search square by square.
        here = fuzz_coords(*self.HOME, miles=5)
        there = fuzz_coords(self.HOME[0] + 0.001, self.HOME[1] + 0.001, miles=5)
        assert here == there

    def test_a_tighter_radius_is_a_finer_grid(self):
        assert miles_between(self.HOME, fuzz_coords(*self.HOME, miles=1)) <= 1


class TestFuzzed:
    """The middle setting: coordinates within N miles, and never finer."""

    @pytest.fixture
    def fuzzed(self, client, recordist):
        client.patch("/api/me/location-precision",
                     json={"location_precision": "fuzzed", "fuzz_miles": 5,
                           "region": "Utah, US"},
                     headers=recordist.headers)
        return recordist

    def test_choosing_it_keeps_the_radius(self, client, recordist):
        answer = client.patch("/api/me/location-precision",
                              json={"location_precision": "fuzzed",
                                    "fuzz_miles": 10},
                              headers=recordist.headers)
        assert answer.status_code == 200
        assert answer.get_json()["location_precision"] == "fuzzed"
        assert answer.get_json()["fuzz_miles"] == 10

    def test_a_radius_that_is_not_a_radius_is_refused(self, client, recordist):
        for bad in (0, -3, 500, "five"):
            answer = client.patch("/api/me/location-precision",
                                  json={"location_precision": "fuzzed",
                                        "fuzz_miles": bad},
                                  headers=recordist.headers)
            assert answer.status_code == 400, bad

    def test_exact_coordinates_are_snapped_on_arrival(self, client, fuzzed):
        # The phone should never send these raw. If one does — an old build, a
        # client someone else wrote — the backstop snaps them here.
        sent = (40.7460, -111.8747)
        row = capture(client, fuzzed, latitude=sent[0], longitude=sent[1])

        stored = (row["latitude"], row["longitude"])
        assert stored != sent
        assert miles_between(sent, stored) <= 5
        assert stored == fuzz_coords(*sent, miles=5)

    def test_already_snapped_coordinates_pass_through_unmoved(self, client, fuzzed):
        snapped = fuzz_coords(40.7460, -111.8747, miles=5)
        row = capture(client, fuzzed, latitude=snapped[0], longitude=snapped[1],
                      coord_fuzz_miles=5)
        assert (row["latitude"], row["longitude"]) == snapped

    def test_the_row_is_marked_as_coarse(self, client, fuzzed):
        # The mark matters as much as the snap: snapped coordinates stored
        # without it would read as exact fixes forever.
        row = capture(client, fuzzed, latitude=40.7460, longitude=-111.8747)
        assert row["coord_fuzz_miles"] == 5

    def test_the_clients_own_mark_is_trusted_first(self, client, recordist):
        # A capture can arrive before the setting that shaped it — the two are
        # separate requests and nothing orders them. The phone says what it did.
        row = capture(client, recordist, latitude=40.7460, longitude=-111.8747,
                      coord_fuzz_miles=5)
        assert row["coord_fuzz_miles"] == 5

    def test_an_edit_cannot_sharpen_the_coordinates(self, client, fuzzed):
        # The same backstop, on the same second door the region setting has.
        row = capture(client, fuzzed)
        sent = (40.7460, -111.8747)

        answer = client.patch(f"/api/captures/{row['id']}",
                              json={"latitude": sent[0], "longitude": sent[1]},
                              headers=fuzzed.headers)

        stored = (answer.get_json()["latitude"], answer.get_json()["longitude"])
        assert stored == fuzz_coords(*sent, miles=5)

    def test_a_fuzzed_contributor_without_a_radius_gets_the_default(
            self, client, recordist):
        # The PATCH carrying the radius can lose the race with the capture push.
        client.patch("/api/me/location-precision",
                     json={"location_precision": "fuzzed", "region": "Utah, US"},
                     headers=recordist.headers)

        row = capture(client, recordist, latitude=40.7460, longitude=-111.8747)

        assert row["coord_fuzz_miles"] == 5
        assert miles_between((40.7460, -111.8747),
                             (row["latitude"], row["longitude"])) <= 5


class TestWhoDecides:

    def test_an_operator_cannot_set_it_for_somebody_else(self, client, operator,
                                                         recordist):
        # There is no route for it, which is the point: this is a setting, not
        # a policy an operator applies to contributors.
        answer = client.patch(f"/api/fleet/contributors/{recordist.contributor['id']}",
                              json={"location_precision": "region"},
                              headers=operator.headers)

        assert answer.status_code >= 400
        unchanged = client.get("/api/me", headers=recordist.headers).get_json()
        assert unchanged["contributor"]["location_precision"] == "exact"
