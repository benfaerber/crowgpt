"""Asking for the app, and being handed it.

The invite unlocks the shared enrollment token, so the things worth pinning
are the ones that would widen who learns it: a pending or declined request
must open nothing, the link must be unguessable and minted once, and only an
operator may approve. The mailer is optional, and its absence must read as
"here is the link" rather than as a failure.
"""

import pytest

from fieldserver.api import access
from fieldserver.core.secrets import DEFAULT_ENROLL_TOKEN


@pytest.fixture
def build(db_path):
    apk_dir = db_path.parent / "apk"
    apk_dir.mkdir()
    apk = apk_dir / "crowgpt-field-test.apk"
    apk.write_bytes(b"apk bytes")
    return apk


def ask(client, email="someone@example.org", **rest):
    return client.post("/preview/request", data={"email": email, **rest})


class TestAsking:

    def test_the_form_is_open_to_anyone(self, client):
        response = client.get("/preview")
        assert response.status_code == 200
        assert b"Request access" in response.data

    def test_a_request_lands_pending(self, client, operator):
        assert ask(client, name="Ana", note="Rooks, Norfolk").status_code == 200
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        assert [(r["email"], r["status"], r["name"]) for r in rows["requests"]] == [
            ("someone@example.org", "pending", "Ana")]

    def test_the_address_is_normalised_and_checked(self, client, operator):
        assert ask(client, email="not-an-email").status_code == 400
        assert ask(client, email="  Someone@Example.org ").status_code == 200
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        assert rows["requests"][0]["email"] == "someone@example.org"

    def test_asking_twice_keeps_one_open_request(self, client, operator):
        ask(client)
        ask(client)
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        assert len(rows["requests"]) == 1

    def test_a_flood_from_one_address_is_cut_off(self, client):
        for i in range(access.SUBMISSIONS_PER_HOUR):
            assert ask(client, email=f"p{i}@example.org").status_code == 200
        assert ask(client, email="late@example.org").status_code == 429

    def test_the_queue_is_for_operators(self, client, recordist):
        assert client.get("/api/fleet/access-requests").status_code == 401
        assert client.get("/api/fleet/access-requests",
                          headers=recordist.headers).status_code == 403


class TestDeciding:

    def _pending_id(self, client, operator):
        ask(client)
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        return rows["requests"][0]["id"]

    def test_approving_mints_one_link_and_reports_no_email(self, client, operator):
        request_id = self._pending_id(client, operator)
        first = client.post(f"/api/fleet/access-requests/{request_id}/approve",
                            headers=operator.headers).get_json()
        again = client.post(f"/api/fleet/access-requests/{request_id}/approve",
                            headers=operator.headers).get_json()
        assert first["request"]["status"] == "approved"
        assert first["emailed"] is False  # no RESEND_API_KEY in tests
        assert first["request"]["invite_url"].startswith("http://localhost/preview/")
        assert again["request"]["invite_url"] == first["request"]["invite_url"]

    def test_declining_opens_nothing(self, client, operator):
        request_id = self._pending_id(client, operator)
        row = client.post(f"/api/fleet/access-requests/{request_id}/decline",
                          headers=operator.headers).get_json()["request"]
        assert row["status"] == "declined"
        assert row["invite_url"] is None

    def test_only_operators_decide(self, client, operator, recordist):
        request_id = self._pending_id(client, operator)
        assert client.post(f"/api/fleet/access-requests/{request_id}/approve",
                           headers=recordist.headers).status_code == 403

    def test_an_email_failure_is_written_on_the_row_not_raised(self, db_path, monkeypatch):
        class BrokenMailer:
            def send(self, *args):
                raise RuntimeError("mail provider refused (403): bad key")

        # The section takes its mailer at register time, so build an app after
        # swapping the factory — that is also how a bad key would reach it.
        monkeypatch.setattr(access.Mailer, "from_env", classmethod(lambda cls: BrokenMailer()))
        from fieldserver.app import create_app
        client = create_app(db_path).test_client()
        op = client.post("/api/devices/register", json={
            "enroll_token": DEFAULT_ENROLL_TOKEN, "contributor_name": "Op",
            "is_operator": True, "operator_token": "dev-operator"}).get_json()
        headers = {"Authorization": f"Bearer {op['device_token']}"}
        ask(client)
        request_id = client.get("/api/fleet/access-requests",
                                headers=headers).get_json()["requests"][0]["id"]
        result = client.post(f"/api/fleet/access-requests/{request_id}/approve",
                             headers=headers).get_json()
        assert result["emailed"] is False
        assert "bad key" in result["request"]["email_error"]
        assert result["request"]["status"] == "approved"


class TestTheInvite:

    def _approved_url(self, client, operator):
        ask(client)
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        request_id = rows["requests"][0]["id"]
        row = client.post(f"/api/fleet/access-requests/{request_id}/approve",
                          headers=operator.headers).get_json()["request"]
        return row["invite_url"].replace("http://localhost", ""), row["invite_token"]

    def test_the_link_shows_the_token_and_the_build(self, client, operator, build):
        path, _ = self._approved_url(client, operator)
        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert DEFAULT_ENROLL_TOKEN in body
        assert "crowgpt-field-test.apk" in body

    def test_the_link_downloads_the_newest_build_and_counts_it(self, client, operator, build):
        path, token = self._approved_url(client, operator)
        response = client.post(f"{path}/apk")
        assert response.status_code == 200
        assert response.mimetype == access.APK_TYPE
        assert response.data == b"apk bytes"
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        assert rows["requests"][0]["downloads"] == 1

    def test_a_pending_or_unknown_token_opens_nothing(self, client, operator, build):
        ask(client)
        assert client.get("/preview/nope").status_code == 404
        assert client.post("/preview/nope/apk").status_code == 404
        body = client.get("/preview/nope").get_data(as_text=True)
        assert DEFAULT_ENROLL_TOKEN not in body

    def test_a_declined_request_opens_nothing(self, client, operator):
        path, token = self._approved_url(client, operator)
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        client.post(f"/api/fleet/access-requests/{rows['requests'][0]['id']}/decline",
                    headers=operator.headers)
        assert client.get(path).status_code == 404

    def test_no_build_yet_is_said_not_crashed(self, client, operator):
        path, _ = self._approved_url(client, operator)
        assert b"No build has been published yet" in client.get(path).data
        assert client.post(f"{path}/apk").status_code == 404
