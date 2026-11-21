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

    def _code(self, client, operator):
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        return rows["requests"][0]["enroll_code"]

    def _enroll(self, client, token, **more):
        return client.post("/api/devices/register",
                           json={"enroll_token": token, "contributor_name": "Invited", **more})

    def test_the_invites_code_enrolls_a_phone_and_marks_who_invited_it(self, client, operator):
        self._approved_url(client, operator)
        enrolled = self._enroll(client, self._code(client, operator))
        assert enrolled.status_code == 201
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        assert enrolled.get_json()["contributor"]["access_request_id"] == rows["requests"][0]["id"]
        assert enrolled.get_json()["contributor"]["role"] == "contributor"
        assert rows["requests"][0]["enrollments"] == 1

    def test_a_declined_invites_code_stops_working_and_the_fleet_token_does_not(self, client, operator):
        self._approved_url(client, operator)
        code = self._code(client, operator)
        request_id = client.get("/api/fleet/access-requests",
                                headers=operator.headers).get_json()["requests"][0]["id"]
        client.post(f"/api/fleet/access-requests/{request_id}/decline", headers=operator.headers)
        assert self._enroll(client, code).status_code == 403
        assert self._enroll(client, DEFAULT_ENROLL_TOKEN).status_code == 201

    def test_one_invite_enrolls_only_so_many_phones(self, client, operator):
        from fieldserver.stores.access_requests import MAX_ENROLLMENTS

        self._approved_url(client, operator)
        code = self._code(client, operator)
        statuses = [self._enroll(client, code).status_code for _ in range(MAX_ENROLLMENTS + 1)]
        assert statuses == [201] * MAX_ENROLLMENTS + [403]

    def test_a_wrong_claim_code_does_not_use_up_the_invite(self, client, operator):
        self._approved_url(client, operator)
        code = self._code(client, operator)
        assert self._enroll(client, code, claim_code="nope").status_code == 403
        rows = client.get("/api/fleet/access-requests", headers=operator.headers).get_json()
        assert rows["requests"][0]["enrollments"] == 0

    def test_an_invite_cannot_make_an_operator(self, client, operator):
        self._approved_url(client, operator)
        assert self._enroll(client, self._code(client, operator), is_operator=True).status_code == 403

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
        assert DEFAULT_ENROLL_TOKEN not in body
        assert self._code(client, operator) in body
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


class TestBanning:

    SPAMMER = {"REMOTE_ADDR": "203.0.113.9"}

    def flood(self, client, count=3):
        for i in range(count):
            client.post("/preview/request", data={"email": f"victim{i}@example.org"},
                        environ_base=self.SPAMMER)

    def queue(self, client, operator):
        return client.get("/api/fleet/access-requests", headers=operator.headers).get_json()

    def ban(self, client, operator, ip="203.0.113.9"):
        return client.post("/api/fleet/banned-addresses", json={"ip": ip},
                           headers=operator.headers)

    def test_a_ban_declines_what_the_address_had_pending_and_nobody_elses(self, client, operator):
        self.flood(client)
        ask(client, email="real@example.org", note="Rooks, Norfolk")
        assert self.ban(client, operator).get_json() == {"ip": "203.0.113.9", "declined": 3}
        rows = self.queue(client, operator)
        assert {r["email"]: r["status"] for r in rows["requests"]}["real@example.org"] == "pending"
        assert [r["status"] for r in rows["requests"]
                if r["requester_ip"] == "203.0.113.9"] == ["declined"] * 3
        assert [(b["ip"], b["requests"]) for b in rows["banned"]] == [("203.0.113.9", 3)]

    def test_a_ban_leaves_an_invite_already_given(self, client, operator):
        self.flood(client, count=1)
        first = self.queue(client, operator)["requests"][0]
        client.post(f"/api/fleet/access-requests/{first['id']}/approve", headers=operator.headers)
        assert self.ban(client, operator).get_json()["declined"] == 0
        assert self.queue(client, operator)["requests"][0]["status"] == "approved"

    def test_a_banned_address_is_thanked_and_nothing_is_stored(self, client, operator):
        self.ban(client, operator)
        response = client.post("/preview/request", data={"email": "victim@example.org"},
                               environ_base=self.SPAMMER)
        assert response.status_code == 200 and b"Thanks" in response.data
        assert self.queue(client, operator)["requests"] == []

    def test_lifting_a_ban_lets_the_address_ask_again(self, client, operator):
        self.ban(client, operator)
        assert client.delete("/api/fleet/banned-addresses/203.0.113.9",
                             headers=operator.headers).status_code == 204
        self.flood(client, count=1)
        assert len(self.queue(client, operator)["requests"]) == 1
        assert client.delete("/api/fleet/banned-addresses/203.0.113.9",
                             headers=operator.headers).status_code == 404

    def test_only_an_operator_bans_and_only_an_address(self, client, operator, recordist):
        assert self.ban(client, recordist).status_code == 403
        assert self.ban(client, operator, ip="not an address").status_code == 400

    def test_a_banned_address_cannot_scan(self, client, operator):
        self.ban(client, operator)
        response = client.post("/api/demo/scan", data={}, environ_base=self.SPAMMER,
                               content_type="multipart/form-data")
        assert response.status_code == 403
