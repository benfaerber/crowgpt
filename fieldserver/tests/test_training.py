"""The dashboard's window onto the long-running jobs.

Nothing here talks to a GPU. The endpoint's whole job is to list files other
processes wrote and be honest about what it found, so the tests write files.
One file per run is the point — a scan and a finetune once shared a single
PROGRESS.json and overwrote each other, which is the failure this shape ends.
"""

import json
import time

import pytest

from fieldserver.api import training


def run_payload(title, finished=False, **extra):
    return {"title": title, "slug": training.Path(title).stem.lower().replace(" ", "-"),
            "finished": finished, "failed": False,
            "stages": [{"name": "train", "status": "done" if finished else "running",
                        "note": "3000/40000", "done": 3000, "total": 40000,
                        "eta_seconds": 7920, "extra": "", "took_seconds": None}],
            "notes": [], **extra}


@pytest.fixture
def progress(tmp_path, monkeypatch):
    """A scratch progress dir, pointed at."""
    folder = tmp_path / "progress"
    folder.mkdir()
    monkeypatch.setenv("PROGRESS_DIR", str(folder))
    return folder


def write_run(folder, slug, title, finished=False, age=0.0):
    path = folder / f"{slug}.json"
    path.write_text(json.dumps({**run_payload(title, finished), "slug": slug}))
    if age:
        past = time.time() - age
        import os
        os.utime(path, (past, past))
    return path


class TestNoRun:
    def test_absent_files_are_a_normal_answer_not_an_error(self, client, operator, progress):
        """Most of the week nothing is training, and that is not a failure."""
        body = client.get("/api/training", headers=operator.headers).get_json()
        assert body["runs"] == []

    def test_it_needs_an_operator(self, client, recordist, progress):
        assert client.get("/api/training").status_code == 401
        assert client.get("/api/training", headers=recordist.headers).status_code == 403


class TestManyRuns:
    def test_two_runs_report_side_by_side(self, client, operator, progress):
        """The reason this endpoint returns a list at all."""
        write_run(progress, "finetune", "DECODER FINETUNE")
        write_run(progress, "scan", "CORPUS SCAN")

        body = client.get("/api/training", headers=operator.headers).get_json()

        assert {r["slug"] for r in body["runs"]} == {"finetune", "scan"}
        assert all(r["run"]["stages"][0]["done"] == 3000 for r in body["runs"])

    def test_active_runs_come_before_finished_ones(self, client, operator, progress):
        write_run(progress, "old", "OLD RUN", finished=True)
        write_run(progress, "live", "LIVE RUN")

        body = client.get("/api/training", headers=operator.headers).get_json()

        assert [r["slug"] for r in body["runs"]] == ["live", "old"]
        assert body["runs"][0]["active"] and not body["runs"][1]["active"]

    def test_two_files_claiming_one_slug_render_one_card(self, client, operator, progress):
        """Freshest wins — the rule Run itself applies when a restarted run
        replaces its own card rather than growing a second one."""
        write_run(progress, "scan", "CORPUS SCAN", age=300)
        (progress / "scan-copy.json").write_text(
            json.dumps({**run_payload("CORPUS SCAN"), "slug": "scan"}))

        body = client.get("/api/training", headers=operator.headers).get_json()

        assert [r["slug"] for r in body["runs"]] == ["scan"]
        assert body["runs"][0]["age_seconds"] < 300

    def test_a_half_written_file_is_skipped_not_fatal(self, client, operator, progress):
        """Rewritten on every update, so a read can land mid-write; the run
        reappears intact on the next poll."""
        (progress / "torn.json").write_text("{ truncated")
        write_run(progress, "whole", "WHOLE RUN")

        body = client.get("/api/training", headers=operator.headers).get_json()

        assert [r["slug"] for r in body["runs"]] == ["whole"]


class TestStaleness:
    def test_a_silent_run_is_stale_and_not_active(self, client, operator, progress):
        """The file outlives the process, so 'is it moving' is a clock question."""
        write_run(progress, "hung", "HUNG RUN", age=training.STALE_AFTER + 60)

        run = client.get("/api/training", headers=operator.headers).get_json()["runs"][0]

        assert run["stale"] and not run["active"]

    def test_a_fresh_run_is_not_stale(self, client, operator, progress):
        write_run(progress, "live", "LIVE RUN")

        run = client.get("/api/training", headers=operator.headers).get_json()["runs"][0]

        assert not run["stale"] and run["active"]
