"""The phone's log, pushed to a place it can be read from without a cable.

What these tests are really guarding: a log push must not be the thing that
fails. Every rule here bends toward keeping the line rather than rejecting it,
because the phones sending them are by definition the ones already misbehaving.
"""

import pytest

from fieldserver.stores.logs import KEEP_PER_DEVICE, MAX_MESSAGE, LogStore


@pytest.fixture
def push(client, recordist):
    def _push(*entries, headers=None):
        return client.post("/api/logs", json={"entries": list(entries)},
                           headers={**recordist.headers, **(headers or {})})
    return _push


def line(uuid="l-1", **over):
    return {"client_uuid": uuid, "at": "2026-07-24T10:00:00Z", "level": "error",
            "tag": "recorder", "message": "startListening threw", **over}


class TestPushing:

    def test_a_batch_comes_back_as_the_uuids_now_held(self, push):
        body = push(line("a"), line("b")).get_json()
        assert body["accepted"] == ["a", "b"]

    def test_resending_is_free(self, push, operator, client):
        """The phone marks a line sent only once confirmed, so a dropped
        response means the whole batch arrives again. It must not double."""
        push(line("a"))
        assert push(line("a")).get_json()["accepted"] == ["a"]
        rows = client.get("/api/fleet/logs", headers=operator.headers).get_json()
        assert len(rows) == 1

    def test_a_line_the_database_refuses_is_not_reported_accepted(
            self, db_path, recordist):
        # Every IntegrityError used to read as "already have it", so a line
        # refused by a foreign key came back accepted — and an accepted line
        # is one the phone stops resending. Both ends satisfied, line gone.
        store = LogStore(db_path)
        result = store.record(recordist.device["id"], contributor_id=999999,
                              entries=[line("fk-1")])
        assert result["accepted"] == []
        assert result["rejected"][0]["client_uuid"] == "fk-1"

    def test_a_line_with_no_idempotency_key_is_the_only_refusal(self, push):
        body = push(line("a"), {"message": "no uuid"}).get_json()
        assert body["accepted"] == ["a"]
        assert len(body["rejected"]) == 1

    def test_an_unknown_level_is_kept_as_info_rather_than_refused(self, push, operator,
                                                                 client):
        push(line("a", level="catastrophe"))
        rows = client.get("/api/fleet/logs", headers=operator.headers).get_json()
        assert rows[0]["level"] == "info"

    def test_a_runaway_message_is_clipped_not_dropped(self, push, operator, client):
        push(line("a", message="x" * (MAX_MESSAGE * 3)))
        rows = client.get("/api/fleet/logs", headers=operator.headers).get_json()
        assert len(rows[0]["message"]) == MAX_MESSAGE + 1  # + the ellipsis

    def test_detail_survives_as_json(self, push, operator, client):
        push(line("a", detail={"code": 500, "capture": "uuid-9"}))
        rows = client.get("/api/fleet/logs", headers=operator.headers).get_json()
        assert '"code": 500' in rows[0]["detail"]

    def test_the_build_that_spoke_is_stamped_from_the_header(self, push, operator,
                                                             client):
        # Not from the body: the phone is already telling every request which
        # build it is, and a log line claiming a different one would be worse
        # than none at all.
        push(line("a"), headers={"X-App-Version": "421", "X-App-Commit": "abc1234"})
        rows = client.get("/api/fleet/logs", headers=operator.headers).get_json()
        assert rows[0]["app_version"] == 421
        assert rows[0]["app_commit"] == "abc1234"

    def test_the_phones_clock_and_ours_are_kept_apart(self, push, operator, client):
        # A phone offline for a week uploads week-old lines. Which is which is
        # itself diagnostic, so `at` is never overwritten with arrival time.
        push(line("a", at="2026-07-01T00:00:00Z"))
        row = client.get("/api/fleet/logs", headers=operator.headers).get_json()[0]
        assert row["at"] == "2026-07-01T00:00:00Z"
        assert row["received_at"] != row["at"]


class TestReading:

    @pytest.fixture(autouse=True)
    def some_lines(self, push):
        push(line("a", level="debug", tag="sync", message="chunk 1"),
             line("b", level="info", tag="sync", message="capture 9 sent"),
             line("c", level="warn", tag="recorder", message="mic fell back"),
             line("d", level="error", tag="db", message="prepareAsync threw"))

    def read(self, client, operator, query=""):
        return client.get(f"/api/fleet/logs{query}", headers=operator.headers).get_json()

    def test_newest_first(self, client, operator):
        assert [r["client_uuid"] for r in self.read(client, operator)][0] == "d"

    def test_a_level_filter_includes_everything_worse(self, client, operator):
        # "Show me warnings" that hides errors is a trap, not a filter.
        levels = {r["level"] for r in self.read(client, operator, "?level=warn")}
        assert levels == {"warn", "error"}

    def test_filtering_by_subsystem(self, client, operator):
        assert len(self.read(client, operator, "?tag=sync")) == 2

    def test_searching_the_message(self, client, operator):
        assert len(self.read(client, operator, "?q=prepareAsync")) == 1

    def test_a_searched_underscore_is_a_character_not_a_wildcard(
            self, push, client, operator):
        # "capture_lock" as a search used to match "capture lock", "captureX
        # lock" and anything else one character wide at that position.
        push(line("e", message="capture_lock armed"),
             line("f", message="capturezlock armed"))
        found = self.read(client, operator, "?q=capture_lock")
        assert [r["client_uuid"] for r in found] == ["e"]

    def test_the_device_and_person_come_along(self, client, operator):
        row = self.read(client, operator)[0]
        assert row["device_label"] == "Pixel 10"
        assert row["display_name"] == "Ben"

    def test_summary_counts_by_level(self, client, operator):
        body = client.get("/api/fleet/logs/summary",
                          headers=operator.headers).get_json()
        assert body["counts"]["error"] == 1
        assert set(body["tags"]) == {"sync", "recorder", "db"}

    def test_clearing_is_allowed_because_the_useful_move_is_wipe_and_watch(
            self, client, operator):
        assert client.delete("/api/fleet/logs",
                             headers=operator.headers).get_json()["deleted"] == 4
        assert self.read(client, operator) == []


class TestNotABottomlessPit:

    def test_a_phone_in_a_crash_loop_cannot_fill_the_disk(self, db_path, recordist):
        """Capped per device, newest kept.

        A log table is the one place here where losing rows is acceptable — the
        newest lines are the ones that explain what is happening now.
        """
        store = LogStore(db_path)
        device, contributor = recordist.device["id"], recordist.contributor["id"]
        store.record(device, contributor,
                     [{"client_uuid": f"n-{i}", "message": "loop", "level": "error"}
                      for i in range(KEEP_PER_DEVICE + 200)])
        assert store.counts()["error"] == KEEP_PER_DEVICE
        kept = {r["client_uuid"] for r in store.recent(limit=KEEP_PER_DEVICE)}
        assert f"n-{KEEP_PER_DEVICE + 199}" in kept
        assert "n-0" not in kept


class TestOwnership:

    def test_a_stranger_cannot_read_the_fleets_logs(self, client, stranger, push):
        push(line("a"))
        assert client.get("/api/fleet/logs", headers=stranger.headers).status_code == 403

    def test_pushing_needs_a_device_token(self, client):
        assert client.post("/api/logs", json={"entries": []}).status_code == 401
