"""The promo's generate buttons: a shelf, a queue behind it, and the bounds.

The worker is stood in for at the same seam test_generations.py uses: rows
are claimed and completed the way generate_worker.py does. What matters here
is what a stranger can and cannot make the box do.
"""

import pytest

from fieldserver.api import demo as demo_api
from fieldserver.app import create_app
from fieldserver.stores.demo import MAX_WAITING, MENU, SHELF_DEPTH, DemoPool
from fieldserver.stores.generations import GenerationStore


@pytest.fixture
def generations(db_path):
    # The clip directory create_app derives, so the routes serve what the
    # stand-in worker below writes.
    return GenerationStore(db_path, db_path.parent / "generated")


@pytest.fixture
def pool(generations):
    return DemoPool(generations)


def finish(generations, limit=None):
    """Play the worker: complete every queued job, most urgent first."""
    done = 0
    while limit is None or done < limit:
        job = generations.claim_next()
        if job is None:
            break
        ref = generations.allocate_ref()
        generations.path({"storage_ref": ref}).write_bytes(b"RIFF demo")
        generations.complete(job["id"], ref, 3.0, job["model"], 1.0, 200)
        done += 1
    return done


class TestShelf:

    def test_restock_queues_depth_per_item_at_low_priority(self, pool, generations):
        assert pool.restock() == SHELF_DEPTH * len(MENU)
        assert pool.restock() == 0
        job = generations.claim_next()
        assert job["source"] == "demo"
        assert job["priority"] == 0

    def test_a_press_takes_a_finished_clip_and_restocks(self, pool, generations):
        pool.restock()
        finish(generations)
        assert pool.shelf()["alarm-call"] == SHELF_DEPTH
        row = pool.take("alarm-call")
        assert row["state"] == "done"
        assert row["served_at"] is not None
        assert row["call_type"] == "alarm call"
        assert pool.shelf()["alarm-call"] == SHELF_DEPTH - 1
        assert pool.restock() == 1

    def test_a_bare_shelf_promotes_the_refill_in_flight(self, pool, generations):
        pool.restock()
        row = pool.take("song")
        assert row["state"] == "queued"
        assert row["priority"] == 1
        assert row["served_at"] is not None
        assert pool.restock() == 1
        # The visitor's job goes before every refill.
        assert generations.claim_next()["id"] == row["id"]

    def test_nothing_in_flight_queues_a_live_job(self, pool, generations):
        row = pool.take("caw")
        assert row["state"] == "queued"
        assert row["model"] == "crowgpt2"
        assert row["call_type"] is None
        assert row["priority"] == 1

    def test_ahead_counts_running_and_more_urgent_queued(self, pool, generations):
        pool.restock()
        generations.claim_next()  # a refill, running
        first = pool.take("call")
        second = pool.take("call")
        assert pool.ahead_of(first) == 1
        assert pool.ahead_of(second) == 2

    def test_chat_does_not_see_demo_rows(self, pool, generations):
        pool.restock()
        generations.request("alarm call")
        assert [r["source"] for r in generations.recent()] == ["chat"]

    def test_prune_drops_served_rows_past_the_window_only(self, pool, generations):
        pool.restock()
        finish(generations)
        taken = pool.take("begging")
        assert pool.prune() == 0
        assert pool.prune(keep_hours=0) == 1
        assert pool.get(taken["id"]) is None
        assert not pool.path(taken).exists()


class TestRoutes:

    def test_the_menu_is_open_and_stocks_the_shelf(self, client, pool):
        response = client.get("/api/demo/menu")
        assert response.status_code == 200
        body = response.get_json()
        assert [i["key"] for i in body["items"]] == list(MENU)
        assert body["shelf"] == {key: 0 for key in MENU}
        assert pool.restock() == 0

    def test_a_press_answers_from_the_shelf(self, client, pool, generations):
        pool.restock()
        finish(generations)
        response = client.post("/api/demo/generate/alarm-call")
        assert response.status_code == 200
        body = response.get_json()
        assert body["state"] == "done"
        assert body["clip"] == f"/api/demo/clips/{body['id']}"
        assert isinstance(body["seed"], int)
        clip = client.get(body["clip"])
        assert clip.status_code == 200
        assert clip.mimetype == "audio/wav"
        assert clip.data == b"RIFF demo"

    def test_a_press_on_a_bare_shelf_is_accepted_and_pollable(self, client, generations):
        response = client.post("/api/demo/generate/caw")
        assert response.status_code == 202
        body = response.get_json()
        assert body["state"] == "queued"
        assert body["ahead"] == 0
        polled = client.get(f"/api/demo/generations/{body['id']}")
        assert polled.get_json()["state"] == "queued"
        assert client.get(f"/api/demo/clips/{body['id']}").status_code == 409
        finish(generations)
        polled = client.get(f"/api/demo/generations/{body['id']}").get_json()
        assert polled["state"] == "done"
        assert client.get(polled["clip"]).status_code == 200

    def test_a_failed_job_says_so(self, client, generations):
        body = client.post("/api/demo/generate/caw").get_json()
        generations.fail(generations.claim_next()["id"], "no checkpoint")
        polled = client.get(f"/api/demo/generations/{body['id']}").get_json()
        assert polled["state"] == "failed"
        assert polled["error"] == "generation failed"

    def test_off_menu_is_404(self, client):
        assert client.post("/api/demo/generate/screech").status_code == 404

    def test_unserved_shelf_rows_are_not_addressable(self, client, pool, generations):
        pool.restock()
        finish(generations)
        unserved = [r for r in _all(generations) if r["served_at"] is None][0]
        assert client.get(f"/api/demo/generations/{unserved['id']}").status_code == 404
        assert client.get(f"/api/demo/clips/{unserved['id']}").status_code == 404

    def test_chat_rows_are_not_addressable(self, client, generations):
        row = generations.request("alarm call")
        assert client.get(f"/api/demo/generations/{row['id']}").status_code == 404

    def test_presses_are_rationed_per_address(self, db_path, monkeypatch):
        monkeypatch.setattr(demo_api, "PRESSES_PER_HOUR", 2)
        fresh = create_app(db_path).test_client()
        assert fresh.post("/api/demo/generate/caw").status_code == 202
        assert fresh.post("/api/demo/generate/caw").status_code == 202
        assert fresh.post("/api/demo/generate/caw").status_code == 429

    def test_too_many_live_jobs_is_503_until_a_shelf_has_clips(self, client, generations):
        for _ in range(MAX_WAITING):
            assert client.post("/api/demo/generate/caw").status_code == 202
        assert client.post("/api/demo/generate/caw").status_code == 503
        finish(generations, limit=MAX_WAITING + SHELF_DEPTH)
        # The caw shelf has clips again; the first live jobs are done too.
        assert client.post("/api/demo/generate/caw").status_code in (200, 202)

    def test_cors_names_the_promo_origins_only(self, client):
        allowed = client.get("/api/demo/menu", headers={"Origin": "https://crowgpt.org"})
        assert allowed.headers["Access-Control-Allow-Origin"] == "https://crowgpt.org"
        other = client.get("/api/demo/menu", headers={"Origin": "https://evil.example"})
        assert "Access-Control-Allow-Origin" not in other.headers
        health = client.get("/api/health", headers={"Origin": "https://crowgpt.org"})
        assert "Access-Control-Allow-Origin" not in health.headers
        preflight = client.options("/api/demo/generate/caw",
                                   headers={"Origin": "https://crowgpt.org"})
        assert preflight.status_code in (200, 204)
        assert "POST" in preflight.headers["Access-Control-Allow-Methods"]


def _all(generations):
    with generations._connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM generations")]
