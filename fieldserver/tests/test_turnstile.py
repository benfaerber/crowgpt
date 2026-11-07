import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier, Event
from urllib.parse import parse_qs

import pytest

from fieldserver.app import create_app
from fieldserver.core import turnstile
from fieldserver.core.throttle import Allowance


@pytest.fixture
def guarded(db_path, monkeypatch):
    monkeypatch.setenv("FIELD_TURNSTILE_SITE_KEY", "public-key")
    monkeypatch.setenv("FIELD_TURNSTILE_SECRET", "private-key")
    monkeypatch.setenv("FIELD_DEMO_TURNSTILE_REQUIRED", "1")
    return create_app(db_path)


def response(**changes):
    return BytesIO(json.dumps(dict(success=True, hostname="crowgpt.org",
                                  action="demo-generate", **changes)).encode())


def test_verifies_remotely_before_creating_a_job(guarded, monkeypatch):
    sent = []
    def verify(request, timeout):
        sent.append((parse_qs(request.data.decode()), timeout, request.full_url))
        return response()
    monkeypatch.setattr(turnstile, "urlopen", verify)
    client = guarded.test_client()
    answer = client.post("/api/demo/generate/caw", data={"cf-turnstile-response": "token"},
                         environ_overrides={"REMOTE_ADDR": "198.51.100.7"})
    assert answer.status_code == 202
    assert sent == [({"secret": ["private-key"], "response": ["token"],
                     "remoteip": ["198.51.100.7"]}, 5, turnstile.VERIFY_URL)]
    menu = client.get("/api/demo/menu")
    assert menu.json["turnstile_site_key"] == "public-key"
    assert b"private-key" not in menu.data


@pytest.mark.parametrize("body", [
    {"success": False},
    {"success": True, "hostname": "evil.example", "action": "demo-generate"},
    {"success": True, "hostname": "crowgpt.org", "action": "different-form"},
    {"success": "true", "hostname": "crowgpt.org", "action": "demo-generate"},
])
def test_rejected_tokens_create_no_job(guarded, monkeypatch, body):
    monkeypatch.setattr(turnstile, "urlopen", lambda *a, **k: BytesIO(json.dumps(body).encode()))
    result = guarded.test_client().post("/api/demo/generate/caw", data={"cf-turnstile-response": "bad"})
    assert result.status_code == 403
    assert guarded.test_client().get("/api/demo/generations/1").status_code == 404


@pytest.mark.parametrize("token", ["", "x" * 2049])
def test_missing_or_oversized_token_never_calls_verifier(guarded, monkeypatch, token):
    def unexpected(*a, **k):
        pytest.fail("must not call Siteverify")
    monkeypatch.setattr(turnstile, "urlopen", unexpected)
    assert guarded.test_client().post("/api/demo/generate/caw", data={
        "cf-turnstile-response": token}).status_code == 403


def test_replay_is_rejected_by_siteverify(guarded, monkeypatch):
    replies = iter([{"success": True, "hostname": "crowgpt.org", "action": "demo-generate"},
                    {"success": False, "error-codes": ["timeout-or-duplicate"]}])
    monkeypatch.setattr(turnstile, "urlopen", lambda *a, **k: BytesIO(json.dumps(next(replies)).encode()))
    client = guarded.test_client()
    assert client.post("/api/demo/generate/caw", data={"cf-turnstile-response": "once"}).status_code == 202
    assert client.post("/api/demo/generate/caw", data={"cf-turnstile-response": "once"}).status_code == 403


@pytest.mark.parametrize("failure", [TimeoutError(), OSError(), ValueError()])
def test_verification_outage_fails_closed_but_health_works(guarded, monkeypatch, failure):
    def unavailable(*a, **k):
        raise failure
    monkeypatch.setattr(turnstile, "urlopen", unavailable)
    client = guarded.test_client()
    assert client.post("/api/demo/generate/caw", data={"cf-turnstile-response": "token"}).status_code == 503
    assert client.get("/api/health").status_code == 200
    # The app's enrollment route sees only its own authentication, no challenge.
    assert client.post("/api/devices/register", json={"enroll_token": "wrong"}).status_code == 403


def test_missing_config_hides_menu_and_refuses_generate(db_path, monkeypatch):
    monkeypatch.setenv("FIELD_DEMO_TURNSTILE_REQUIRED", "1")
    monkeypatch.delenv("FIELD_TURNSTILE_SECRET", raising=False)
    client = create_app(db_path).test_client()
    assert client.get("/api/demo/menu").status_code == 503
    assert client.post("/api/demo/generate/caw").status_code == 503
    assert client.get("/preview").status_code == 200


def test_only_two_requests_can_wait_on_siteverify(guarded, monkeypatch):
    entered = Barrier(3)
    release = Event()
    def slow(*a, **k):
        entered.wait(timeout=5)
        assert release.wait(timeout=5)
        return BytesIO(b'{"success": false}')
    monkeypatch.setattr(turnstile, "urlopen", slow)
    def press():
        return guarded.test_client().post("/api/demo/generate/caw", data={"cf-turnstile-response": "token"}).status_code
    with ThreadPoolExecutor(2) as pool:
        pending = [pool.submit(press) for _ in range(2)]
        try:
            entered.wait(timeout=5)
            assert press() == 503
            assert guarded.test_client().get("/api/health").status_code == 200
        finally:
            release.set()
        assert [p.result() for p in pending] == [403, 403]


def test_hourly_allowance_cannot_be_raced():
    allowance = Allowance(30, 3600)
    with ThreadPoolExecutor(40) as pool:
        assert sum(pool.map(lambda _: allowance.spend("same-address"), range(100))) == 30
