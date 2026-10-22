"""What the dose API must refuse, which is the part that protects the measurement.

Three behaviours are pinned harder than the rest, because each one silently
destroys a sitting rather than failing loudly: results before the pre-committed
count, a dose that crosses a block boundary, and an answer on a grade the scale
does not have.
"""

import json

import pytest


@pytest.fixture
def clips(tmp_path):
    """A directory of files standing in for wavs. Contents are never decoded."""
    folder = tmp_path / "pool-clips"
    folder.mkdir()
    for name in ("a.wav", "b.wav", "c.wav", "anchor.wav"):
        (folder / name).write_bytes(b"RIFF....WAVEfmt ")
    return folder


def build(store, clips, *, n=6, dose_size=3, reveal_at=None, name="spread-0052"):
    """A pool of `n` trials in blocks of `dose_size`, arms alternating."""
    trials = []
    for i in range(n):
        first, second = ("alpha", "beta") if i % 2 == 0 else ("beta", "alpha")
        trials.append({
            "block": i // dose_size,
            "kind": "catch" if i == 0 else "compare",
            "anchor_clip": "anchor.wav",
            "first_clip": "a.wav" if first == "alpha" else "b.wav",
            "second_clip": "b.wav" if second == "beta" else "a.wav",
            "first_arm": first,
            "second_arm": second,
            "facts": {"seconds": 2.0},
        })
    return store.create_pool(
        name=name,
        question="Which clip is closer to the reference?",
        clip_dir=clips,
        trials=trials,
        dose_size=dose_size,
        reveal_at=reveal_at,
    )


@pytest.fixture
def pool(app, db_path, clips):
    from fieldserver.stores.listening import ListeningStore

    return build(ListeningStore(db_path), clips)


class TestAuth:
    def test_it_needs_an_operator(self, client, recordist, pool):
        assert client.get("/api/listening/pools").status_code == 401
        assert client.get(
            "/api/listening/pools", headers=recordist.headers).status_code == 403


class TestDose:
    def test_a_bigger_appetite_serves_whole_blocks(self, db_path, clips):
        # Raising dose_size from 10 to 20 on a pool built in blocks of ten hands
        # out two blocks. Two balanced blocks are themselves balanced, so the
        # guarantee that makes doses poolable across days is untouched.
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=9, dose_size=3, name="appetite")
        store.set_pacing(pool["id"], dose_size=6)
        served = store.dose(pool["id"])
        assert len(served) == 6
        assert sorted({t["block"] for t in served}) == [0, 1]

    def test_an_appetite_between_blocks_rounds_down(self, db_path, clips):
        # 4 on blocks of 3 serves 3, not 3-and-a-third. Honest under-serving
        # beats a silent half-block, which would be an unbalanced dose.
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=9, dose_size=3, name="rounds-down")
        store.set_pacing(pool["id"], dose_size=4)
        assert len(store.dose(pool["id"])) == 3

    def test_a_part_graded_block_is_finished_before_the_next_is_started(
            self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=9, dose_size=3, name="resume-big")
        store.answer(store.dose(pool["id"])[0]["id"], 1)
        store.set_pacing(pool["id"], dose_size=6)
        served = store.dose(pool["id"])
        # The two left in block 0, then all of block 1 — never block 2, which
        # would not fit whole.
        assert [t["block"] for t in served] == [0, 0, 1, 1, 1]

    def test_the_appetite_can_exceed_what_is_left(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=6, dose_size=3, name="overshoot")
        store.set_pacing(pool["id"], dose_size=100)
        assert len(store.dose(pool["id"])) == 6

    def test_pacing_changes_leave_the_answers_alone(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=9, dose_size=3, name="pacing-safe")
        store.answer(store.dose(pool["id"])[0]["id"], 2)
        store.set_pacing(pool["id"], dose_size=6, cooldown_minutes=45)
        fresh = store.pool(pool["id"])
        assert fresh["answered"] == 1
        assert fresh["dose_size"] == 6 and fresh["cooldown_minutes"] == 45
        assert store.rows(pool["id"])[0]["grade"] == 2

    def test_a_nonsense_dose_size_is_refused(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, name="bad-size")
        with pytest.raises(ValueError, match="dose_size"):
            store.set_pacing(pool["id"], dose_size=0)

    def test_a_dose_stops_at_the_block_boundary(self, client, operator, pool):
        body = client.get(f"/api/listening/pools/{pool['id']}/dose",
                          headers=operator.headers).get_json()
        assert len(body["trials"]) == 3
        assert {t["block"] for t in body["trials"]} == {0}

    def test_the_dose_never_names_the_arms(self, client, operator, pool):
        body = client.get(f"/api/listening/pools/{pool['id']}/dose",
                          headers=operator.headers).get_json()
        for trial in body["trials"]:
            assert "first_arm" not in trial and "second_arm" not in trial

    def test_answering_advances_to_the_next_block(self, client, operator, pool):
        headers = operator.headers
        first = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=headers).get_json()["trials"]
        for trial in first:
            assert client.post(f"/api/listening/trials/{trial['id']}/answer",
                               json={"grade": 0}, headers=headers).status_code == 201
        second = client.get(f"/api/listening/pools/{pool['id']}/dose",
                            headers=headers).get_json()["trials"]
        assert {t["block"] for t in second} == {1}
        assert not {t["id"] for t in first} & {t["id"] for t in second}

    def test_a_finished_pool_gives_an_empty_dose(self, client, operator, pool, db_path):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        for row in store.dose(pool["id"]) + store.dose(pool["id"]):
            store.answer(row["id"], 0)
        while store.dose(pool["id"]):
            for row in store.dose(pool["id"]):
                store.answer(row["id"], 0)
        body = client.get(f"/api/listening/pools/{pool['id']}/dose",
                          headers=operator.headers).get_json()
        assert body["trials"] == []


class TestAnswers:
    def test_a_grade_off_the_scale_is_refused(self, client, operator, pool):
        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=operator.headers).get_json()["trials"][0]
        response = client.post(f"/api/listening/trials/{trial['id']}/answer",
                               json={"grade": 3}, headers=operator.headers)
        assert response.status_code == 400

    def test_an_unknown_defect_tag_is_refused(self, client, operator, pool):
        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=operator.headers).get_json()["trials"][0]
        response = client.post(
            f"/api/listening/trials/{trial['id']}/answer",
            json={"grade": 1, "defects": ["sounds-bad"]}, headers=operator.headers)
        assert response.status_code == 400

    def test_re_answering_replaces_rather_than_double_counts(
            self, client, operator, pool, db_path):
        from fieldserver.stores.listening import ListeningStore

        headers = operator.headers
        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=headers).get_json()["trials"][0]
        for grade in (2, -1):
            client.post(f"/api/listening/trials/{trial['id']}/answer",
                        json={"grade": grade}, headers=headers)
        rows = ListeningStore(db_path).rows(pool["id"])
        assert len(rows) == 1
        assert rows[0]["grade"] == -1

    def test_grade_zero_is_a_real_answer(self, client, operator, pool, db_path):
        from fieldserver.stores.listening import ListeningStore

        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=operator.headers).get_json()["trials"][0]
        assert client.post(f"/api/listening/trials/{trial['id']}/answer",
                           json={"grade": 0},
                           headers=operator.headers).status_code == 201
        row = ListeningStore(db_path).rows(pool["id"])[0]
        assert row["preferred_arm"] is None and row["margin"] == 0


class TestReveal:
    def test_results_are_withheld_until_the_committed_count(
            self, client, operator, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=6, dose_size=3, reveal_at=6, name="withheld")
        headers = operator.headers

        for row in store.dose(pool["id"]):
            store.answer(row["id"], 1)
        response = client.get(f"/api/listening/pools/{pool['id']}/results",
                              headers=headers)
        assert response.status_code == 409
        assert response.get_json()["remaining"] == 3

        while store.dose(pool["id"]):
            for row in store.dose(pool["id"]):
                store.answer(row["id"], 1)
        assert client.get(f"/api/listening/pools/{pool['id']}/results",
                          headers=headers).status_code == 200

    def test_progress_carries_no_score(self, client, operator, pool):
        body = client.get(f"/api/listening/pools/{pool['id']}",
                          headers=operator.headers).get_json()
        assert set(body) >= {"answered", "remaining", "trials", "can_reveal"}
        assert not {k for k in body if "grade" in k or "score" in k}

    def test_results_undo_the_presentation_order(self, client, operator, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=2, dose_size=2, reveal_at=2, name="unrandomise")
        trials = store.dose(pool["id"])
        # Trial 0 is alpha-first, trial 1 is beta-first. Grading +2 both times
        # means "the first clip", so the preferred arm must differ between them.
        for row in trials:
            store.answer(row["id"], 2)
        rows = client.get(f"/api/listening/pools/{pool['id']}/results",
                          headers=operator.headers).get_json()["rows"]
        assert [r["preferred_arm"] for r in rows] == ["alpha", "beta"]


class TestClips:
    def test_a_clip_is_served_from_the_pool_directory(self, client, operator, pool):
        response = client.get(
            f"/api/listening/pools/{pool['id']}/clips/a.wav", headers=operator.headers)
        assert response.status_code == 200
        assert response.mimetype == "audio/wav"

    def test_traversal_out_of_the_pool_directory_is_refused(
            self, client, operator, pool):
        response = client.get(
            f"/api/listening/pools/{pool['id']}/clips/../../field.db",
            headers=operator.headers)
        assert response.status_code in (403, 404)


class TestPage:
    def test_the_page_is_served_without_a_token(self, client):
        # The HTML is a shell; every byte of data behind it needs the operator
        # token. Gating the shell too would only mean a blank page and a prompt
        # that cannot be answered.
        assert client.get("/listen/").status_code in (200, 503)

    def test_the_bare_path_redirects_to_the_canonical_one(self, client):
        response = client.get("/listen")
        assert response.status_code == 308
        assert response.headers["Location"].endswith("/listen/")


class TestTimings:
    """`decision_ms` is tab-open time and `engaged_ms` is the real one.

    The first dose of churn-spread-0053 reported a 121 s median decision time and
    it was read as evidence the graded response made him listen harder. It was a
    walk away — "i musta just forgot. Its not real. I prolly spent like 5-10 per."
    Both fields are stored, and the distinction has to survive in the export or
    the same wrong conclusion is one query away.
    """

    def test_both_times_are_stored_and_returned(self, client, operator, pool, db_path):
        from fieldserver.stores.listening import ListeningStore

        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=operator.headers).get_json()["trials"][0]
        response = client.post(
            f"/api/listening/trials/{trial['id']}/answer",
            json={"grade": 1, "decision_ms": 121_000, "engaged_ms": 7_400},
            headers=operator.headers)
        assert response.status_code == 201
        assert response.get_json()["engaged_ms"] == 7_400
        row = ListeningStore(db_path).rows(pool["id"])[0]
        assert row["decision_ms"] == 121_000 and row["engaged_ms"] == 7_400

    def test_an_answer_without_an_engaged_time_is_still_accepted(
            self, client, operator, pool, db_path):
        # The 20 trials graded before the column existed have it NULL, which is
        # correct: nobody measured it. They must not become an error to read.
        from fieldserver.stores.listening import ListeningStore

        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=operator.headers).get_json()["trials"][0]
        client.post(f"/api/listening/trials/{trial['id']}/answer",
                    json={"grade": 0, "decision_ms": 4_000},
                    headers=operator.headers)
        assert ListeningStore(db_path).rows(pool["id"])[0]["engaged_ms"] is None

    def test_re_answering_replaces_the_engaged_time_too(
            self, client, operator, pool, db_path):
        from fieldserver.stores.listening import ListeningStore

        trial = client.get(f"/api/listening/pools/{pool['id']}/dose",
                           headers=operator.headers).get_json()["trials"][0]
        for engaged in (1_000, 9_000):
            client.post(f"/api/listening/trials/{trial['id']}/answer",
                        json={"grade": 1, "engaged_ms": engaged},
                        headers=operator.headers)
        rows = ListeningStore(db_path).rows(pool["id"])
        assert len(rows) == 1 and rows[0]["engaged_ms"] == 9_000


class TestCooldown:
    """Only ten every thirty minutes, and enforced here rather than in the page.

    A timer in JavaScript survives neither a reload nor a second browser, and the
    same pool is graded from a phone and a laptop.
    """

    def cooled(self, db_path, clips, minutes=30, **kwargs):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, name=kwargs.pop("name", "cooled"), **kwargs)
        store.set_pacing(pool["id"], cooldown_minutes=minutes)
        return store, store.pool(pool["id"])

    def test_a_fresh_pool_is_open(self, db_path, clips):
        _, pool = self.cooled(db_path, clips)
        assert pool["locked_for"] == 0

    def test_finishing_a_block_starts_the_clock(self, db_path, clips):
        store, pool = self.cooled(db_path, clips)
        for row in store.dose(pool["id"]):
            store.answer(row["id"], 0)
        assert store.pool(pool["id"])["locked_for"] > 0

    def test_a_locked_pool_hands_out_no_dose(self, client, operator, db_path, clips):
        store, pool = self.cooled(db_path, clips)
        for row in store.dose(pool["id"]):
            store.answer(row["id"], 0)
        assert store.dose(pool["id"]) == []
        response = client.get(f"/api/listening/pools/{pool['id']}/dose",
                              headers=operator.headers)
        assert response.status_code == 429
        body = response.get_json()
        assert body["locked_for"] > 0 and body["cooldown_minutes"] == 30

    def test_a_part_graded_block_stays_reachable(self, db_path, clips):
        # The failure this prevents: answer three of ten, reload, and the rest of
        # the dose is locked away for half an hour.
        store, pool = self.cooled(db_path, clips)
        first = store.dose(pool["id"])
        store.answer(first[0]["id"], 1)
        assert store.pool(pool["id"])["locked_for"] == 0
        assert len(store.dose(pool["id"])) == len(first) - 1

    def test_the_clock_runs_out(self, db_path, clips):
        store, pool = self.cooled(db_path, clips, minutes=1)
        for row in store.dose(pool["id"]):
            store.answer(row["id"], 0)
        assert store.pool(pool["id"])["locked_for"] > 0
        # Rewrite the stored answer time to an hour ago rather than sleeping.
        import sqlite3
        from datetime import datetime, timedelta, timezone

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE listening_answers SET answered_at = ?", (past,))
        conn.commit()
        assert store.pool(pool["id"])["locked_for"] == 0
        assert len(store.dose(pool["id"])) == 3

    def test_a_finished_pool_is_never_locked(self, db_path, clips):
        store, pool = self.cooled(db_path, clips)
        while True:
            batch = store.dose(pool["id"])
            if not batch:
                break
            for row in batch:
                store.answer(row["id"], 0)
            store.set_pacing(pool["id"], cooldown_minutes=None)
        store.set_pacing(pool["id"], cooldown_minutes=30)
        fresh = store.pool(pool["id"])
        assert fresh["remaining"] == 0 and fresh["locked_for"] == 0

    def test_no_cooldown_means_no_lock(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, name="uncooled")
        for row in store.dose(pool["id"]):
            store.answer(row["id"], 0)
        assert store.pool(pool["id"])["locked_for"] == 0

    def test_the_cooldown_can_be_changed_mid_pool(self, db_path, clips):
        store, pool = self.cooled(db_path, clips)
        store.answer(store.dose(pool["id"])[0]["id"], 1)
        assert store.set_pacing(pool["id"], cooldown_minutes=5)["cooldown_minutes"] == 5
        assert store.set_pacing(pool["id"], cooldown_minutes=None)["cooldown_minutes"] is None
        # The answer survived a pacing change.
        assert store.pool(pool["id"])["answered"] == 1

    def test_a_nonsense_cooldown_is_refused(self, db_path, clips):
        store, pool = self.cooled(db_path, clips)
        with pytest.raises(ValueError, match="at least 1"):
            store.set_pacing(pool["id"], cooldown_minutes=0)


class TestDeletePool:
    """Replacing an unanswered pool is fine; discarding a measurement is not.

    0053's first build had to be thrown away — 121 of its 132 reference bouts
    turned out to have been played already — so replacing an unheard pool has to
    be possible. The guard is that "unheard" is checked rather than assumed.
    """

    def test_an_unanswered_pool_can_be_dropped(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, name="throwaway")
        assert store.delete_pool(pool["id"]) == 6
        assert store.pool_by_name("throwaway") is None

    def test_a_graded_pool_is_refused(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, name="measured")
        store.answer(store.dose(pool["id"])[0]["id"], 1)
        with pytest.raises(ValueError, match="answered"):
            store.delete_pool(pool["id"])
        assert store.pool_by_name("measured") is not None

    def test_deleting_takes_the_trials_and_answers_with_it(self, db_path, clips):
        import sqlite3

        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, name="cascade")
        store.delete_pool(pool["id"])
        conn = sqlite3.connect(db_path)
        left = conn.execute("SELECT COUNT(*) FROM listening_trials WHERE pool_id = ?",
                            (pool["id"],)).fetchone()[0]
        assert left == 0


class TestRegisterOverHttp:
    """The POST route exists for a caller that already holds a session.

    Experiments register through `tools/register_pool.py` instead, so this is the
    path nothing in the repo currently takes — which is exactly why it is pinned.
    """

    def body(self, clips, name="over-http"):
        return {
            "name": name,
            "question": "Which is closer to the reference?",
            "clip_dir": str(clips),
            "dose_size": 2,
            "trials": [
                {"block": 0, "kind": "compare", "anchor_clip": "anchor.wav",
                 "first_clip": "a.wav", "second_clip": "b.wav",
                 "first_arm": "alpha", "second_arm": "beta"},
                {"block": 0, "kind": "compare", "anchor_clip": "anchor.wav",
                 "first_clip": "b.wav", "second_clip": "a.wav",
                 "first_arm": "beta", "second_arm": "alpha"},
            ],
        }

    def test_it_needs_an_operator(self, client, recordist, clips):
        assert client.post("/api/listening/pools",
                           json=self.body(clips)).status_code == 401
        assert client.post("/api/listening/pools", json=self.body(clips),
                           headers=recordist.headers).status_code == 403

    def test_a_pool_can_be_registered_and_then_dosed(self, client, operator, clips):
        response = client.post("/api/listening/pools", json=self.body(clips),
                               headers=operator.headers)
        assert response.status_code == 201, response.get_data(as_text=True)
        pool = response.get_json()
        assert pool["trials"] == 2 and pool["reveal_at"] == 2
        dose = client.get(f"/api/listening/pools/{pool['id']}/dose",
                          headers=operator.headers).get_json()
        assert len(dose["trials"]) == 2

    def test_a_missing_field_is_a_400(self, client, operator, clips):
        for field in ("name", "question", "clip_dir", "trials"):
            body = self.body(clips)
            del body[field]
            assert client.post("/api/listening/pools", json=body,
                               headers=operator.headers).status_code == 400

    def test_a_trial_missing_a_clip_is_a_400_not_a_500(self, client, operator, clips):
        body = self.body(clips)
        del body["trials"][0]["first_clip"]
        assert client.post("/api/listening/pools", json=body,
                           headers=operator.headers).status_code == 400


class TestPoolValidation:
    def test_a_pool_needs_a_question_written_first(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        with pytest.raises(ValueError, match="question"):
            ListeningStore(db_path).create_pool(
                name="no-question", question="", clip_dir=clips,
                trials=[{"first_clip": "a.wav", "second_clip": "b.wav",
                         "first_arm": "x", "second_arm": "y"}])

    def test_two_pools_cannot_share_a_name(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        build(store, clips, name="twice")
        with pytest.raises(ValueError, match="already exists"):
            build(store, clips, name="twice")

    def test_facts_survive_the_round_trip(self, db_path, clips):
        from fieldserver.stores.listening import ListeningStore

        store = ListeningStore(db_path)
        pool = build(store, clips, n=2, dose_size=2, reveal_at=2, name="facts")
        store.answer(store.dose(pool["id"])[0]["id"], 1)
        assert store.rows(pool["id"])[0]["facts"] == {"seconds": 2.0}
        assert json.loads(json.dumps(store.pool(pool["id"])["spec"] or {})) == {}
