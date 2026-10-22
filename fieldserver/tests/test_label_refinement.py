"""Re-answering a label, without losing the answer it used to hold.

A second push with the same `client_uuid` used to run `UPDATE labels SET
call_type = ?` over the first answer. That was written for a labeller fixing a
mistake before the push lands — storing both would put both into the training
manifest — and it silently doubled as the only path for a *refinement*. "I
mistapped" and "I listened again and that alarm was a mob" arrived as the same
request, and the first answer was gone either way.

Splitting alarm into mobbing and alerting means exactly that re-hearing, in bulk.
The question nobody can answer afterwards is whether the finer vocabulary
actually changed anybody's mind, and it needs both answers and the versions they
were chosen from — so the previous values move to `label_revisions` rather than
being overwritten into nothing.
"""

import sqlite3

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
    """Push a label. The same `client_uuid` twice is the path under test."""

    def _label(**body):
        response = client.post(
            f"/api/captures/{capture['id']}/labels",
            json={"media_id": media["id"], "call_type": "alarm call",
                  "client_uuid": "l-1", "start_sec": 1, "end_sec": 2, **body},
            headers=recordist.headers)
        assert response.status_code == 201, response.get_data(as_text=True)
        return response.get_json()

    return _label


@pytest.fixture
def revisions(db_path):
    def _revisions(label_id):
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM label_revisions WHERE label_id = ? ORDER BY id",
                (label_id,))]

    return _revisions


class TestRefiningALabel:

    def test_the_answer_it_used_to_hold_is_kept(self, label, revisions):
        first = label(config_version=45)
        refined = label(call_type="mobbing", config_version=60)

        assert refined["call_type"] == "mobbing"
        assert [r["call_type"] for r in revisions(first["id"])] == ["alarm call"]

    def test_the_superseded_answer_keeps_the_vocabulary_it_came_from(self, label,
                                                                    revisions):
        # The measurement this exists for: "did the finer list change anybody's
        # mind" is a comparison between two answers *and* the two lists they were
        # chosen from. One without the other says nothing.
        first = label(config_version=45)
        label(call_type="mobbing", config_version=60)

        assert revisions(first["id"])[0]["config_version"] == 45

    def test_the_current_answer_carries_the_current_vocabulary(self, label):
        # config_version describes the answer in the row. Leaving 45 on a
        # judgement made from version 60's list would attribute a new answer to
        # a list it was not chosen from.
        label(config_version=45)
        assert label(call_type="mobbing", config_version=60)["config_version"] == 60

    def test_each_refinement_adds_to_the_history(self, label, revisions):
        first = label(config_version=45)
        label(call_type="mobbing", config_version=60)
        label(call_type="scold", config_version=61)

        assert [r["call_type"] for r in revisions(first["id"])] == [
            "alarm call", "mobbing"]

    def test_replaying_the_same_answer_is_not_a_refinement(self, label, revisions):
        # Push retries and duplicate syncs land here constantly. A resend of an
        # unchanged answer is the mechanism working, not a change of mind, and
        # recording it would bury the real ones in noise.
        first = label(config_version=45)
        label(config_version=45)

        assert revisions(first["id"]) == []


class TestWhatMustNotMove:

    def test_the_label_id_stays_the_same(self, label):
        # Not cosmetic. See the context test below — and every id already handed
        # out to a phone that labelled offline.
        assert label(config_version=45)["id"] == label(call_type="mobbing")["id"]

    def test_its_witnessed_context_stays_attached(self, client, recordist, capture,
                                                  label):
        # context_events.label_id references labels(id), so a refinement that
        # minted a new row would leave the dog that was barking hanging off the
        # answer nobody stands behind any more. This is why the previous *values*
        # move rather than the row being superseded by a new one.
        made = label(config_version=45)
        client.post(f"/api/captures/{capture['id']}/context",
                    json={"label_id": made["id"], "key": "dog_visible",
                          "client_uuid": "c-1", "config_version": 45},
                    headers=recordist.headers)

        label(call_type="mobbing", config_version=60)

        events = client.get(f"/api/captures/{capture['id']}/context",
                            headers=recordist.headers).get_json()
        assert [e["label_id"] for e in events] == [made["id"]]

    def test_there_is_still_one_row_per_judgement(self, client, operator, label):
        # The reason the history lives in its own table. `labels` is counted in
        # a dozen places, eight of them on the dashboard, and a second row per
        # refinement would inflate every one of them silently.
        label(config_version=45)
        label(call_type="mobbing", config_version=60)

        totals = client.get("/api/fleet/labels", headers=operator.headers).get_json()
        by_type = {row["call_type"]: row["n"] for row in totals}
        assert by_type == {"mobbing": 1}


class TestTheAwkwardCases:

    def test_a_refinement_from_a_client_that_cannot_stamp_leaves_it_unstamped(
            self, label, revisions):
        # An older phone sends no config_version. The row then honestly says "I
        # do not know which list this answer came from" rather than inheriting
        # the previous answer's 45, which would be a stamp transplanted onto a
        # judgement that was never made from it. Nothing is lost: 45 is in the
        # revision, describing the answer it actually belongs to.
        first = label(config_version=45)
        refined = label(call_type="mobbing")

        assert refined["config_version"] is None
        assert revisions(first["id"])[0]["config_version"] == 45

    def test_retracting_a_label_takes_its_history_with_it(self, client, recordist,
                                                          label, revisions):
        # Retraction is already the deliberate act, and the drafts of a judgement
        # that has been withdrawn are opinions with no owner.
        first = label(config_version=45)
        label(call_type="mobbing", config_version=60)

        client.delete(f"/api/labels/{first['id']}", headers=recordist.headers)

        assert revisions(first["id"]) == []

    def test_a_label_pushed_without_a_client_uuid_is_untouched(self, client,
                                                              recordist, capture,
                                                              media, revisions):
        # No uuid means no way to recognise a resend, so each push is its own
        # judgement and nothing is being replaced.
        made = client.post(f"/api/captures/{capture['id']}/labels",
                           json={"media_id": media["id"], "call_type": "alarm call"},
                           headers=recordist.headers).get_json()
        assert revisions(made["id"]) == []


class TestItLeavesTheRelabelQueue:

    def test_a_re_answered_label_is_no_longer_waiting(self, client, operator, label,
                                                     db_path):
        # The queue asks whether the vocabulary moved since the labeller chose
        # from it. Re-answering is the act it was asking for, so the new
        # config_version is what takes the label back off the list — and the old
        # answer it was flagged for is still on file.
        label(config_version=4)
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE label_defs SET active = 0, version_retired = 9 "
                         "WHERE key = 'alarm call'")

        assert len(client.get("/api/fleet/relabel-queue",
                              headers=operator.headers).get_json()) == 1

        label(call_type="mobbing", config_version=12)

        assert client.get("/api/fleet/relabel-queue",
                          headers=operator.headers).get_json() == []
