"""The real visitor must own every allowance, on both sides of the DNS flip."""

import pytest
from flask import request

from fieldserver.app import create_app
from fieldserver.api import demo


@pytest.fixture
def proxied(db_path, monkeypatch):
    monkeypatch.setenv("FIELD_TRUST_PROXY", "1")
    monkeypatch.setattr(demo, "PRESSES_PER_HOUR", 1)
    app = create_app(db_path)

    @app.get("/test-address")
    def who():
        return {"ip": request.remote_addr, "url": request.url_root}

    return app.test_client()


def forwarded(visitor, peer="173.245.48.1"):
    # Caddy's observed configuration replaces incoming XFF with its socket peer.
    return {"X-Forwarded-For": peer, "CF-Connecting-IP": visitor,
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": "field.crowgpt.org"}


@pytest.mark.parametrize("visitor", ["198.51.100.20", "2001:db8::5"])
def test_cloudflare_visitor_and_https(proxied, visitor):
    assert proxied.get("/test-address", headers=forwarded(visitor)).json == {
        "ip": visitor, "url": "https://field.crowgpt.org/"}


def test_direct_origin_cannot_spoof_cloudflare_header(proxied):
    assert proxied.get("/test-address", headers=forwarded(
        "1.2.3.4", peer="198.51.100.9")).json["ip"] == "198.51.100.9"


def test_untrusted_socket_cannot_spoof_either_header(proxied):
    response = proxied.get("/test-address", headers=forwarded("1.2.3.4"),
                           environ_overrides={"REMOTE_ADDR": "198.51.100.7"})
    assert response.json["ip"] == "198.51.100.7"


def test_an_invented_earlier_xff_hop_is_ignored(proxied):
    headers = forwarded("198.51.100.8")
    headers["X-Forwarded-For"] = "1.2.3.4, 173.245.48.1"
    assert proxied.get("/test-address", headers=headers).json["ip"] == "198.51.100.8"


@pytest.mark.parametrize("value", ["", "1.2.3.4, 5.6.7.8", "garbage"])
def test_bad_cloudflare_header_does_not_share_an_edge_bucket(proxied, value):
    assert proxied.get("/test-address", headers=forwarded(value)).status_code == 400


def test_demo_allowances_are_independent(proxied):
    path = "/api/demo/generate/caw"
    a, b = forwarded("198.51.100.1"), forwarded("198.51.100.2")
    assert proxied.post(path, headers=a).status_code == 202
    assert proxied.post(path, headers=a).status_code == 429
    assert proxied.post(path, headers=b).status_code == 202


def test_access_submission_allowances_are_independent(proxied):
    for i in range(5):
        assert proxied.post("/preview/request", data={"email": f"a{i}@example.org"},
                            headers=forwarded("198.51.100.1")).status_code == 200
    assert proxied.post("/preview/request", data={"email": "a6@example.org"},
                        headers=forwarded("198.51.100.1")).status_code == 429
    assert proxied.post("/preview/request", data={"email": "b@example.org"},
                        headers=forwarded("198.51.100.2")).status_code == 200


def test_login_failures_do_not_lock_out_another_visitor(proxied):
    for _ in range(10):
        assert proxied.post("/api/operator/session", json={"operator_token": "wrong"},
                            headers=forwarded("198.51.100.1")).status_code == 403
    assert proxied.post("/api/operator/session", json={"operator_token": "wrong"},
                        headers=forwarded("198.51.100.1")).status_code == 429
    assert proxied.post("/api/operator/session", json={"operator_token": "wrong"},
                        headers=forwarded("198.51.100.2")).status_code == 403


@pytest.mark.parametrize("path", ["/api/health", "/api/no-such-route", "/preview", "/preview/invalid"])
def test_private_pages_and_errors_are_not_cacheable(client, path):
    response = client.get(path)
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["CDN-Cache-Control"] == "no-store"
