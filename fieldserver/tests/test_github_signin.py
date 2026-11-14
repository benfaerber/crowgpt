"""Sign in with GitHub: only the listed account gets a dashboard session."""

from urllib.parse import parse_qs, urlparse

import pytest

from fieldserver.api.identity import GITHUB_STATE_COOKIE
from fieldserver.app import DEFAULT_OPERATOR_TOKEN, create_app
from fieldserver.core.github import GitHubRefused, GitHubSignIn

BEN = {"id": 37051697, "login": "benfaerber"}
STRANGER = {"id": 1, "login": "someone-else"}


class FakeGitHub:
    def __init__(self, user=None, refuse=False):
        self.user = user
        self.refuse = refuse

    def identify(self, code, redirect_uri):
        if self.refuse:
            raise GitHubRefused("bad_verification_code")
        return self.user


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("FIELD_GITHUB_CLIENT_ID", "client")
    monkeypatch.setenv("FIELD_GITHUB_CLIENT_SECRET", "shh")
    monkeypatch.setenv("FIELD_GITHUB_OPERATORS", str(BEN["id"]))


def github_client(db_path, monkeypatch, fake):
    monkeypatch.setattr(GitHubSignIn, "identify", fake.identify)
    return create_app(db_path).test_client()


def start(client) -> str:
    response = client.get("/api/operator/github")
    assert response.status_code == 302
    return parse_qs(urlparse(response.location).query)["state"][0]


def token_from(response) -> str:
    assert response.status_code == 302
    prefix = "/#github-token="
    assert response.location.startswith(prefix)
    return response.location[len(prefix):]


class TestUnconfigured:
    def test_it_is_off_without_the_environment(self, client):
        assert client.get("/api/operator/methods").get_json() == {"github": False}
        assert client.get("/api/operator/github").status_code == 404

    def test_an_empty_operator_list_keeps_it_off(self, monkeypatch, db_path):
        monkeypatch.setenv("FIELD_GITHUB_CLIENT_ID", "client")
        monkeypatch.setenv("FIELD_GITHUB_CLIENT_SECRET", "shh")
        monkeypatch.setenv("FIELD_GITHUB_OPERATORS", "")
        client = create_app(db_path).test_client()
        assert client.get("/api/operator/methods").get_json() == {"github": False}


class TestSignIn:
    def test_methods_says_it_is_on(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(BEN))
        assert client.get("/api/operator/methods").get_json() == {"github": True}

    def test_the_start_sends_the_browser_to_github(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(BEN))
        response = client.get("/api/operator/github")
        query = parse_qs(urlparse(response.location).query)
        assert response.location.startswith("https://github.com/login/oauth/authorize")
        assert query["client_id"] == ["client"]
        assert query["redirect_uri"][0].endswith("/api/operator/github/callback")

    def test_the_operator_gets_a_working_fleet_session(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(BEN))
        state = start(client)
        token = token_from(client.get(f"/api/operator/github/callback?state={state}&code=c"))
        summary = client.get("/api/fleet/summary", headers={"Authorization": f"Bearer {token}"})
        assert summary.status_code == 200

    def test_another_github_account_is_refused(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(STRANGER))
        state = start(client)
        response = client.get(f"/api/operator/github/callback?state={state}&code=c")
        assert response.status_code == 403

    def test_a_callback_without_our_state_is_refused(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(BEN))
        start(client)
        response = client.get("/api/operator/github/callback?state=forged&code=c")
        assert response.status_code == 400

    def test_a_callback_never_started_here_is_refused(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(BEN))
        client.delete_cookie(GITHUB_STATE_COOKIE, path="/api/operator/github")
        response = client.get("/api/operator/github/callback?state=x&code=c")
        assert response.status_code == 400

    def test_github_refusing_the_code_is_a_502(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(refuse=True))
        state = start(client)
        response = client.get(f"/api/operator/github/callback?state={state}&code=c")
        assert response.status_code == 502

    def test_it_does_not_evict_the_token_sign_in(self, configured, db_path, monkeypatch):
        client = github_client(db_path, monkeypatch, FakeGitHub(BEN))
        laptop = client.post("/api/operator/session",
                             json={"operator_token": DEFAULT_OPERATOR_TOKEN}).get_json()
        state = start(client)
        token_from(client.get(f"/api/operator/github/callback?state={state}&code=c"))
        summary = client.get("/api/fleet/summary",
                             headers={"Authorization": f"Bearer {laptop['device_token']}"})
        assert summary.status_code == 200
