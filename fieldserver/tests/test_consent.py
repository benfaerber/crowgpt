"""Accepting the upload policy, and what the answers do to later uploads.

Consent is per account and given during onboarding. Publishing is opt-in; the
generator answer is copied onto each capture at upload so that changing it
later never rewrites what earlier recordings were sent under.
"""

from fieldserver.core.policy import CURRENT_VERSION, UploadPolicy


def consent(client, who, **answers):
    body = {"policy_version": CURRENT_VERSION, "allow_generator": True,
            "allow_publish": False, **answers}
    return client.patch("/api/me/consent", json=body, headers=who.headers)


def capture(client, who, uuid):
    return client.post("/api/captures", json={"client_uuid": uuid},
                       headers=who.headers).get_json()


class TestThePolicy:

    def test_it_is_readable_before_enrolling(self, client):
        answer = client.get("/api/policy")
        assert answer.status_code == 200
        body = answer.get_json()
        assert body["version"] == CURRENT_VERSION
        assert body["title"] and "opt in" in body["text"]

    def test_every_version_up_to_the_current_one_still_has_its_text(self):
        for version in range(1, CURRENT_VERSION + 1):
            assert UploadPolicy.load(version).text


class TestConsenting:

    def test_a_new_account_has_not_consented(self, recordist):
        assert recordist.contributor["policy_version"] is None
        assert recordist.contributor["allow_publish"] is None

    def test_answers_are_recorded_against_the_version(self, client, recordist):
        answer = consent(client, recordist, allow_generator=False, allow_publish=True)
        assert answer.status_code == 200
        me = client.get("/api/me", headers=recordist.headers).get_json()["contributor"]
        assert me["policy_version"] == CURRENT_VERSION
        assert me["policy_accepted_at"]
        assert (me["allow_generator"], me["allow_publish"]) == (0, 1)

    def test_an_old_version_is_refused(self, client, recordist):
        assert consent(client, recordist, policy_version=CURRENT_VERSION - 1).status_code == 409

    def test_a_missing_answer_is_refused_not_guessed(self, client, recordist):
        answer = client.patch("/api/me/consent",
                              json={"policy_version": CURRENT_VERSION,
                                    "allow_generator": True},
                              headers=recordist.headers)
        assert answer.status_code == 400


class TestUploadsCarryTheGeneratorAnswer:

    def test_an_account_never_asked_is_not_excluded(self, client, recordist):
        assert capture(client, recordist, "a")["generator_excluded"] == 0

    def test_saying_no_excludes_what_is_sent_afterwards(self, client, recordist):
        before = capture(client, recordist, "a")
        consent(client, recordist, allow_generator=False)
        after = capture(client, recordist, "b")
        assert after["generator_excluded"] == 1
        reread = client.get(f"/api/captures/{before['id']}",
                            headers=recordist.headers).get_json()
        assert reread["generator_excluded"] == 0

    def test_app_captures_are_app_provenance(self, client, recordist):
        assert capture(client, recordist, "a")["provenance"] == "app"
