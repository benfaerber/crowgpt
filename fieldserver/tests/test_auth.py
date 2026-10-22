"""Who can read what.

Operator status used to be whatever the registering client said it was, so
anyone who could enroll could read every device's captures. These pin the rule
that replaced it: the role is granted by a second secret, not claimed.
"""

import pytest

import fieldserver.app as appmod
from fieldserver.api.identity import WRONG_GUESSES
from fieldserver.app import (
    DEFAULT_ENROLL_TOKEN,
    DEFAULT_OPERATOR_TOKEN,
    refuse_default_secrets_off_loopback,
)
from fieldserver.core.secrets import presented

# Every fleet route there is, by method. The refusal sweep below runs the
# lot, so a route added without current_operator() fails here instead of
# shipping open — the old list named four of fourteen, and a new route could
# pass the suite without ever being asked who was calling.
FLEET_ROUTES = [
    ("GET", "/api/fleet/summary"),
    ("GET", "/api/fleet/devices"),
    ("GET", "/api/fleet/contributors"),
    ("PATCH", "/api/fleet/contributors/1"),
    ("GET", "/api/fleet/relabel-queue"),
    ("GET", "/api/fleet/logs"),
    ("GET", "/api/fleet/logs/summary"),
    ("DELETE", "/api/fleet/logs"),
    ("GET", "/api/fleet/captures"),
    ("GET", "/api/fleet/captures/1"),
    ("GET", "/api/fleet/labels"),
    ("GET", "/api/fleet/semantics"),
    ("GET", "/api/fleet/families"),
    ("GET", "/api/fleet/families/1"),
]

# The subset that answers 200 on an empty fleet. The detail routes 404 and
# the contributor patch 400s once past the gate — which is exactly what the
# refusal sweep is there to prove they never reach.
FLEET_LIST_ROUTES = [route for method, route in FLEET_ROUTES
                     if method == "GET" and not route.endswith("/1")]


class TestEnrollment:
    def test_a_wrong_enrollment_token_is_refused(self, client):
        response = client.post("/api/devices/register",
                               json={"enroll_token": "nope",
                                     "contributor_name": "Nobody"})
        assert response.status_code == 403

    def test_a_plain_enrollment_succeeds(self, recordist):
        assert recordist.token

    def test_and_is_not_an_operator(self, recordist):
        assert recordist.device["is_operator"] is False

    def test_claiming_operator_without_the_secret_is_refused(self, client):
        response = client.post("/api/devices/register",
                               json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                     "contributor_name": "Sneaky", "is_operator": True})
        assert response.status_code == 403

    def test_a_wrong_operator_token_is_refused(self, client):
        response = client.post("/api/devices/register",
                               json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                     "contributor_name": "Ben", "is_operator": True,
                                     "operator_token": "guess"})
        assert response.status_code == 403

    def test_the_right_operator_token_mints_an_operator(self, operator):
        assert operator.device["is_operator"] is True


class TestFleetRoutes:
    @pytest.mark.parametrize("method,route", FLEET_ROUTES)
    def test_a_contributor_is_refused(self, client, recordist, method, route):
        response = client.open(route, method=method, headers=recordist.headers)
        assert response.status_code == 403

    @pytest.mark.parametrize("method,route", FLEET_ROUTES)
    def test_an_unauthenticated_caller_is_refused(self, client, method, route):
        assert client.open(route, method=method).status_code == 401

    @pytest.mark.parametrize("route", FLEET_LIST_ROUTES)
    def test_an_operator_is_allowed(self, client, operator, route):
        assert client.get(route, headers=operator.headers).status_code == 200

    def test_an_invalid_bearer_token_is_refused(self, client):
        response = client.post("/api/captures", json={"latitude": 40.76},
                               headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


class TestCaptureVisibility:
    @pytest.fixture
    def capture(self, client, recordist):
        return client.post("/api/captures", json={"client_uuid": "cap-1"},
                           headers=recordist.headers).get_json()

    def test_an_operator_may_read_someone_elses_capture(
            self, client, capture, operator):
        """That is the point of the role, not a leak."""
        response = client.get(f"/api/captures/{capture['id']}", headers=operator.headers)
        assert response.status_code == 200

    def test_another_contributor_may_not(self, client, capture, stranger):
        response = client.get(f"/api/captures/{capture['id']}", headers=stranger.headers)
        assert response.status_code == 403


class TestGuessing:
    """The secrets are strings somebody types into a phone.

    Without a limit, how guessable one is comes down to how fast a laptop can
    post — which on a home network is thousands a second, and turns a token
    short enough to type into one short enough to find.
    """

    def wrong_enrollment(self, client):
        return client.post("/api/devices/register",
                           json={"enroll_token": "nope", "contributor_name": "x"})

    def test_a_run_of_wrong_guesses_stops_being_answered(self, client):
        for _ in range(WRONG_GUESSES):
            assert self.wrong_enrollment(client).status_code == 403
        assert self.wrong_enrollment(client).status_code == 429

    def test_a_wrong_operator_token_counts_too(self, client):
        for _ in range(WRONG_GUESSES):
            client.post("/api/operator/session", json={"operator_token": "nope"})
        assert client.post("/api/operator/session",
                           json={"operator_token": "nope"}).status_code == 429

    def test_a_wrong_claim_code_counts_too(self, client):
        # It joins a handset to somebody else's corpus, so it is a secret on
        # the same footing as the other two.
        for _ in range(WRONG_GUESSES):
            client.post("/api/devices/register",
                        json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                              "claim_code": "guess"})
        assert client.post("/api/devices/register",
                           json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                 "claim_code": "guess"}).status_code == 429

    def test_the_block_covers_the_right_answer_as_well(self, client):
        # Otherwise it is not a limit, it is a delay: a script would simply keep
        # going and the correct guess would still be accepted when it arrived.
        for _ in range(WRONG_GUESSES):
            self.wrong_enrollment(client)
        blocked = client.post("/api/devices/register",
                              json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                    "contributor_name": "Ben"})
        assert blocked.status_code == 429

    def test_getting_it_right_is_never_throttled(self, client):
        # A recordist enrolling several handsets in a row, or an operator
        # reloading the dashboard, must not be able to lock themselves out.
        for i in range(WRONG_GUESSES + 5):
            answer = client.post("/api/devices/register",
                                 json={"enroll_token": DEFAULT_ENROLL_TOKEN,
                                       "contributor_name": f"phone {i}"})
            assert answer.status_code == 201


class TestDefaultSecrets:
    """Off loopback the built-in dev secrets are the same as no secrets at all."""

    def test_loopback_tolerates_them(self):
        assert refuse_default_secrets_off_loopback("127.0.0.1") is None

    def test_binding_the_network_with_them_is_refused(self):
        with pytest.raises(SystemExit) as excinfo:
            refuse_default_secrets_off_loopback("0.0.0.0")
        assert "FIELD_ENROLL_TOKEN" in str(excinfo.value)
        assert "FIELD_OPERATOR_TOKEN" in str(excinfo.value)

    def test_the_defaults_are_still_the_documented_ones(self):
        assert (DEFAULT_ENROLL_TOKEN, DEFAULT_OPERATOR_TOKEN) == (
            "dev-enroll", "dev-operator")


class TestAnEmptySecretIsNotASecret:
    """An exported-but-empty token is no secret at all, not a secret of "".

    Without the guard, compare_digest("", "") is True, so a request that simply
    omits the field authenticates — an empty FIELD_ENROLL_TOKEN (a blank line in
    a sourced env file, a truncated secrets.env) turns enrolment, and with it
    operator status and the whole corpus, wide open while still looking guarded.
    """

    def test_presented_refuses_an_empty_configured_secret(self):
        assert presented({}, "enroll_token", "") is False
        assert presented({"enroll_token": ""}, "enroll_token", "") is False
        assert presented({"enroll_token": "anything"}, "enroll_token", "") is False

    def test_a_real_secret_still_matches(self):
        assert presented({"enroll_token": "s3cret"}, "enroll_token", "s3cret") is True

    def test_an_empty_secret_is_refused_off_loopback(self, monkeypatch):
        # The weakness sweep must count empty as weak, or the refusal that guards
        # the network bind steps aside for the most open state of all.
        monkeypatch.setattr(appmod, "ENROLL_SECRET", "")
        monkeypatch.setattr(appmod, "OPERATOR_SECRET", "")
        with pytest.raises(SystemExit) as excinfo:
            refuse_default_secrets_off_loopback("0.0.0.0")
        assert "FIELD_ENROLL_TOKEN" in str(excinfo.value)
