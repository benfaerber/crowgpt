"""What version is running, on the server and on each phone.

Not cosmetic. A fix committed and never installed looks exactly like a fix that
didn't work, and an afternoon went to that once already: the dashboard showed a
phone that had been syncing happily for hours and said nothing about it running
last week's bundle.
"""

import pytest

from fieldserver.core.build_info import WIRE_VERSION, resolve


class TestServerBuild:

    def test_health_says_what_it_is_running(self, client):
        build = client.get("/api/health").get_json()["build"]
        assert set(build) == {
            "version", "commit", "committed_at", "dirty", "branch", "wire"}

    def test_the_wire_version_is_what_clients_actually_check(self, client):
        # Separate from the commit count on purpose. A server three tooling
        # commits behind stores exactly the same fields, and warning about it
        # teaches people to click past the warning that matters.
        build = client.get("/api/health").get_json()["build"]
        assert build["wire"] == WIRE_VERSION
        assert build["wire"] != build["version"]

    def test_the_version_counts_commits(self, client):
        # The first commit is v1, the hundredth is v100 — two integers compare at
        # a glance, and two hashes don't compare at all.
        build = client.get("/api/health").get_json()["build"]
        assert build["version"] > 0
        assert build["commit"] != "unknown"

    def test_it_is_resolved_once_not_per_request(self, client):
        first = client.get("/api/health").get_json()["build"]
        second = client.get("/api/health").get_json()["build"]
        assert first == second

    def test_a_tree_without_git_admits_it(self, monkeypatch, tmp_path):
        # A tarball export or a build box without git. A version that says
        # "unversioned" is honest; one that invents a number is not.
        monkeypatch.setattr("fieldserver.core.build_info.PROJECT_ROOT", tmp_path)
        build = resolve()
        assert build["version"] == 0
        assert build["commit"] == "unknown"
        assert build["committed_at"] is None


class TestCaptureAppVersion:
    """Which build *recorded* a capture — not which one uploaded it."""

    def test_the_recording_build_is_kept_with_the_capture(self, client, recordist):
        capture = client.post("/api/captures", json={
            "client_uuid": "cap-1", "app_version": 118, "app_commit": "aaaaaaa",
        }, headers={**recordist.headers, "X-App-Version": "123"}).get_json()
        # 118 recorded it; 123 is merely the build that happened to sync it,
        # days and several releases later. The stamp wins.
        assert capture["app_version"] == 118
        assert capture["app_commit"] == "aaaaaaa"

    def test_it_does_not_move_when_the_phone_updates(self, client, recordist):
        client.post("/api/captures", json={"client_uuid": "cap-1", "app_version": 118},
                    headers=recordist.headers)
        client.get("/api/captures", headers={**recordist.headers, "X-App-Version": "123"})
        capture = client.get("/api/captures", headers=recordist.headers).get_json()[0]
        assert capture["app_version"] == 118

    def test_an_unstamped_capture_falls_back_to_the_uploading_build(
            self, client, recordist):
        # A client too old to stamp itself. The uploading build is a bound on
        # the recording build, which beats knowing nothing.
        client.get("/api/captures", headers={**recordist.headers, "X-App-Version": "123"})
        capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                              headers={**recordist.headers, "X-App-Version": "123"}).get_json()
        assert capture["app_version"] == 123

    def test_a_capture_from_a_silent_client_admits_it_knows_nothing(
            self, client, recordist):
        capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                              headers=recordist.headers).get_json()
        assert capture["app_version"] is None


class TestDeviceAppVersion:
    """Which build each handset last called in with."""

    def test_a_phone_reports_its_build_on_any_request(self, client, recordist):
        client.get("/api/captures", headers={
            **recordist.headers, "X-App-Version": "121", "X-App-Commit": "512e11e",
        })
        device = client.get("/api/me", headers=recordist.headers).get_json()["device"]
        assert device["app_version"] == 121
        assert device["app_commit"] == "512e11e"

    def test_it_follows_the_phone_forward(self, client, recordist):
        # Stamped on every request rather than at enrollment, or it would freeze
        # at whatever was installed the day the phone joined the fleet.
        for version in ("113", "121"):
            client.get("/api/captures", headers={
                **recordist.headers, "X-App-Version": version,
            })
        device = client.get("/api/me", headers=recordist.headers).get_json()["device"]
        assert device["app_version"] == 121

    def test_a_client_that_says_nothing_keeps_the_last_known_build(
            self, client, recordist):
        # "Unknown" would erase a real answer with the absence of one. An older
        # app that doesn't send the header is exactly the app worth knowing about.
        client.get("/api/captures", headers={
            **recordist.headers, "X-App-Version": "121",
        })
        client.get("/api/captures", headers=recordist.headers)
        device = client.get("/api/me", headers=recordist.headers).get_json()["device"]
        assert device["app_version"] == 121

    def test_a_junk_header_does_not_break_the_request(self, client, recordist):
        response = client.get("/api/captures", headers={
            **recordist.headers, "X-App-Version": "not-a-number",
        })
        assert response.status_code == 200
        device = client.get("/api/me", headers=recordist.headers).get_json()["device"]
        assert device["app_version"] is None

    def test_the_fleet_view_shows_it(self, client, operator, recordist):
        client.get("/api/captures", headers={
            **recordist.headers, "X-App-Version": "121", "X-App-Commit": "512e11e",
        })
        devices = client.get("/api/fleet/devices", headers=operator.headers).get_json()
        pixel = next(d for d in devices if d["id"] == recordist.device["id"])
        assert pixel["app_version"] == 121
        assert pixel["app_commit"] == "512e11e"

    def test_a_phone_that_never_reported_reads_as_unknown(
            self, client, operator, recordist):
        devices = client.get("/api/fleet/devices", headers=operator.headers).get_json()
        pixel = next(d for d in devices if d["id"] == recordist.device["id"])
        assert pixel["app_version"] is None
