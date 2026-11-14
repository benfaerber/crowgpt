"""An invited contributor has a storage allowance; the fleet's own phones do not."""

import pytest

from fieldserver.app import create_app
from fieldserver.stores.quota import StorageQuota


@pytest.fixture
def small(db_path, monkeypatch):
    """A server whose allowance is one megabyte."""
    monkeypatch.setenv("FIELD_INVITED_QUOTA_MB", "1")
    return create_app(db_path).test_client()


def enroll(client, token="dev-enroll", **more):
    body = client.post("/api/devices/register",
                       json={"enroll_token": token, "contributor_name": "R", **more}).get_json()
    return body["contributor"], {"Authorization": f"Bearer {body['device_token']}"}


def invited(client):
    _, operator = enroll(client, is_operator=True, operator_token="dev-operator")
    client.post("/preview/request", data={"email": "guest@example.org"})
    row = client.get("/api/fleet/access-requests", headers=operator).get_json()["requests"][0]
    code = client.post(f"/api/fleet/access-requests/{row['id']}/approve",
                       headers=operator).get_json()["request"]["enroll_code"]
    return enroll(client, token=code)


def send(client, headers, megabytes, kind="video", fmt="mp4"):
    capture = client.post("/api/captures", json={}, headers=headers).get_json()
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"kind": kind, "format": fmt}, headers=headers).get_json()
    return client.put(f"/api/media/{media['id']}", data=b"\0" * int(megabytes * 1024 * 1024),
                      headers=headers)


def test_an_invited_contributor_is_refused_past_the_allowance(small):
    _, guest = invited(small)
    assert send(small, guest, 0.6).status_code == 200
    refused = send(small, guest, 0.6)
    assert refused.status_code == 413
    assert "allowance" in refused.get_data(as_text=True)


def test_the_fleets_own_phones_have_no_allowance(small):
    _, mine = enroll(small)
    assert send(small, mine, 0.6).status_code == 200
    assert send(small, mine, 0.6).status_code == 200


def test_one_guests_uploads_do_not_spend_anothers(small, db_path):
    first, first_headers = invited(small)
    send(small, first_headers, 0.6)
    quota = StorageQuota(db_path)
    assert quota.used(first["id"]) == int(0.6 * 1024 * 1024)
    assert quota.used(first["id"] + 100) == 0
