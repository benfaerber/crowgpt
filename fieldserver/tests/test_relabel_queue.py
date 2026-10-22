"""Which vocabulary a label was chosen from, and what to do when it moves.

A label records a decision; the meaning of that decision lives in the list the
labeller was shown. Retire a tag or bring one back meaning something else, and
every label made under the old version is ambiguous — with nothing to say which.

The tempting substitute is arithmetic on `created_at` against
`config_versions.published_at`, and these tests exist partly to make the reason
it fails concrete: the phone caches the vocabulary and labels offline, so a
label made this afternoon may have been chosen from a list three versions old.
Only the client knows, so the client sends it.
"""

import pytest


@pytest.fixture
def capture(client, recordist):
    return client.post("/api/captures", json={"client_uuid": "cap-1"},
                       headers=recordist.headers).get_json()


@pytest.fixture
def media(client, recordist, capture):
    return client.post(f"/api/captures/{capture['id']}/media",
                       json={"client_uuid": "m-1", "kind": "audio"},
                       headers=recordist.headers).get_json()


@pytest.fixture
def label(client, recordist, capture, media):
    def _label(**body):
        return client.post(f"/api/captures/{capture['id']}/labels",
                           json={"media_id": media["id"], "call_type": "alarm call",
                                 "start_sec": 1, "end_sec": 2, **body},
                           headers=recordist.headers)
    return _label


def queue(client, operator):
    return client.get("/api/fleet/relabel-queue", headers=operator.headers).get_json()


class TestRecordingIt:

    def test_a_label_remembers_the_vocabulary_it_came_from(self, label):
        row = label(client_uuid="l-1", config_version=12).get_json()
        assert row["config_version"] == 12

    def test_it_is_taken_from_the_client_not_from_this_server(self, client, label,
                                                             recordist):
        # The whole point. A phone that has been in a field for a week labels
        # against the vocabulary it last fetched, and the server's idea of
        # "current" says nothing about what the labeller was looking at.
        row = label(client_uuid="l-2", config_version=3).get_json()
        assert row["config_version"] == 3

    def test_a_label_from_a_client_too_old_to_say_records_nothing(self, label):
        # Rather than a guess. Every label that predates the stamp is in this
        # position and inventing a version for one would write a guess into the
        # corpus as a fact.
        assert label(client_uuid="l-3").get_json()["config_version"] is None

    def test_context_events_carry_it_too(self, client, recordist, capture, label):
        made = label(client_uuid="l-4", config_version=9).get_json()
        event = client.post(f"/api/captures/{capture['id']}/context",
                            json={"label_id": made["id"], "key": "dog_visible",
                                  "client_uuid": "c-1", "config_version": 9},
                            headers=recordist.headers).get_json()
        assert event["config_version"] == 9


class TestTheQueue:

    def test_a_label_whose_vocabulary_has_not_moved_is_not_in_it(self, client,
                                                                 operator, label):
        label(client_uuid="l-5", config_version=99)
        assert queue(client, operator) == []

    def test_a_label_with_no_version_is_left_alone(self, client, operator, label,
                                                   app, db_path):
        # Excluded rather than assumed stale: there is no honest way to place it.
        import sqlite3
        label(client_uuid="l-6")
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET active = 0, version_retired = 5 "
                         "WHERE key = 'alarm call'")
        assert queue(client, operator) == []

    def test_a_retired_call_type_puts_its_labels_in_the_queue(self, client, operator,
                                                              label, db_path):
        import sqlite3
        label(client_uuid="l-7", config_version=4)
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET active = 0, version_retired = 9 "
                         "WHERE key = 'alarm call'")

        rows = queue(client, operator)

        assert len(rows) == 1
        assert rows[0]["why"] == "the call type was retired"

    def test_a_label_made_after_the_retirement_is_not_flagged(self, client, operator,
                                                              label, db_path):
        # It was made knowing the tag was going; the earlier ones were not.
        import sqlite3
        label(client_uuid="l-8", config_version=20)
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET active = 0, version_retired = 9 "
                         "WHERE key = 'alarm call'")
        assert queue(client, operator) == []

    def test_a_key_brought_back_with_a_new_meaning_flags_the_old_labels(
            self, client, operator, label, db_path):
        # The dangerous case. The tag reads the same and means something else,
        # so nothing about the label itself looks wrong.
        import sqlite3
        label(client_uuid="l-9", config_version=4)
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET active = 1, version_introduced = 12, "
                         "version_retired = 9 WHERE key = 'alarm call'")

        rows = queue(client, operator)

        assert len(rows) == 1
        assert "reintroduced" in rows[0]["why"]

    def test_the_queue_says_enough_to_act_on(self, client, operator, label, db_path):
        import sqlite3
        label(client_uuid="l-10", config_version=4)
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET active = 0, version_retired = 9 "
                         "WHERE key = 'alarm call'")

        row = queue(client, operator)[0]

        assert row["capture_id"] and row["call_type"] == "alarm call"
        assert row["contributor_name"] == "Ben"
        assert row["config_version"] == 4


class TestWhenADefinitionArrived:
    """`version_introduced`, which the queue above compares against.

    It decides whether a coarse answer carries an opinion about a finer word. An
    `alarm call` label made before `mobbing` was on the menu says nothing about
    mobbing; one made after says something weak. Get this column wrong and the
    first reads as the second — a considered rejection of a word nobody was
    offered — which is the shape of mistake experiments/0012 found in crow-tools,
    whose `scold` column was never put to a human on 1,405 of its segments.
    """

    def test_a_label_added_to_a_running_fleet_records_the_version_it_arrived_at(
            self, app, db_path):
        # The bug this replaces: the insert omitted the column, so a label whose
        # whole reason for existing is that it arrived *after* the first fleets
        # claimed to have been there since the seed.
        import sqlite3

        from fieldserver.stores.config_store import ConfigStore

        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM label_defs WHERE key = 'not_a_crow'")
            before = conn.execute(
                "SELECT MAX(version) FROM config_versions").fetchone()[0]

        ConfigStore(db_path)

        with sqlite3.connect(db_path) as conn:
            introduced = conn.execute(
                "SELECT version_introduced FROM label_defs WHERE key = 'not_a_crow'"
            ).fetchone()[0]
        assert introduced > before

    def test_a_fleet_that_already_recorded_a_1_is_corrected_from_the_receipt(
            self, app, db_path):
        # Two definitions on every existing fleet were inserted by the old path.
        # Publishing left a receipt — config_versions.notes says "add label
        # not_a_crow" against the version that did it — so this is recoverable
        # exactly, without the timestamp arithmetic that does not work.
        import sqlite3

        from fieldserver.stores.config_store import ConfigStore

        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET version_introduced = 1 "
                         "WHERE key = 'not_a_crow'")
            version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM config_versions").fetchone()[0]
            conn.execute(
                "INSERT INTO config_versions (version, published_at, notes) "
                "VALUES (?, '2026-07-26T05:12:10+00:00', 'add label not_a_crow')",
                (version,))

        ConfigStore(db_path)

        with sqlite3.connect(db_path) as conn:
            assert conn.execute(
                "SELECT version_introduced FROM label_defs WHERE key = 'not_a_crow'"
            ).fetchone()[0] == version

    def test_a_definition_that_already_knows_when_it_arrived_is_left_alone(
            self, app, db_path):
        # Only ever moves a default forward. A real version is not second-guessed
        # by a string match on a note.
        import sqlite3

        from fieldserver.stores.config_store import ConfigStore

        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET version_introduced = 4 "
                         "WHERE key = 'not_a_crow'")
            conn.execute(
                "INSERT INTO config_versions (version, published_at, notes) "
                "VALUES (99, '2026-07-26T05:12:10+00:00', 'add label not_a_crow')")

        ConfigStore(db_path)

        with sqlite3.connect(db_path) as conn:
            assert conn.execute(
                "SELECT version_introduced FROM label_defs WHERE key = 'not_a_crow'"
            ).fetchone()[0] == 4

    def test_a_brand_new_fleet_says_1_and_means_it(self, app, db_path):
        # Nothing to correct here: on a fresh database the seed *is* version 1,
        # so every word in it genuinely has been on the menu from the start.
        import sqlite3

        with sqlite3.connect(db_path) as conn:
            versions = {r[0] for r in conn.execute(
                "SELECT version_introduced FROM label_defs")}
        assert versions == {1}


class TestRetirementRecordsWhen:

    def test_retiring_a_context_stamps_the_version_it_happened_at(self, app, db_path):
        # Definitions already recorded when they arrived. Without the other end,
        # a queue cannot tell "made before the tag went" from "made after".
        import sqlite3
        from fieldserver.stores.config_store import ConfigStore

        store = ConfigStore(db_path)
        version = store.retire_context("dog_visible")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT active, version_retired FROM context_defs "
                               "WHERE key = 'dog_visible'").fetchone()
        assert row == (0, version)
