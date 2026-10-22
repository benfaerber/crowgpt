"""The export carries the word a human chose, not only the class it folds into.

Here for the reason test_corpus_fork.py gives: export_manifest.py is stdlib plus
this server's database, so it imports without the BirdNET venv, and this is the
suite that gets run.

`mobbing` and `alarm call` both map to the CORE class "alarm call", so a manifest
that recorded only the CORE class could not tell them apart — and a head trained
on a finer class would have to treat every coarse label as *not* mobbing to make
up the difference. That is the failure experiments/0012 measured in crow-tools:
its `scold` column was only ever put to a human on 1,089 of 2,494 segments, and
read as though the other 1,405 had answered no it scored 0.581 against a 0.947
control.

So the rule: a label supplies positives for what it says, and nothing at all
about what it does not say. These tests are what stops that being re-derived by
whoever next adds a class.
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INGEST = REPO / "pipelines" / "ingest"


@pytest.fixture
def export():
    """export_manifest's main(), loaded from the file rather than installed.

    `manifest` is imported by it as a sibling script rather than a package, so
    the ingest directory goes on the path first.
    """
    sys.path.insert(0, str(INGEST))
    try:
        path = INGEST / "export_manifest.py"
        spec = importlib.util.spec_from_file_location("export_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(INGEST))


@pytest.fixture
def labelled(client, recordist, db_path):
    """Label one capture's audio, with whatever call types the test names.

    The media file has to exist on disk: the export drops records whose audio is
    missing, which is right — a manifest pointing at nothing trains nothing — and
    would otherwise make every assertion here vacuously true.
    """
    def _labelled(*call_types):
        capture = client.post("/api/captures", json={"client_uuid": "cap-1"},
                              headers=recordist.headers).get_json()
        media = client.post(f"/api/captures/{capture['id']}/media",
                            json={"client_uuid": "m-1", "kind": "audio"},
                            headers=recordist.headers).get_json()
        with sqlite3.connect(db_path) as conn:
            ref = conn.execute("SELECT storage_ref FROM media WHERE id = ?",
                               (media["id"],)).fetchone()[0]
        audio = db_path.parent / "media" / ref
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"not really a flac")
        for i, call_type in enumerate(call_types):
            client.post(f"/api/captures/{capture['id']}/labels",
                        json={"media_id": media["id"], "call_type": call_type,
                              "client_uuid": f"l-{i}", "config_version": 60},
                        headers=recordist.headers)
        return ref

    return _labelled


def run(export, db_path, tmp_path):
    export.main(["--slug", "american-crow", "--field-db", str(db_path),
                 "--data-dir", str(tmp_path / "data")])
    manifest = tmp_path / "data" / "species" / "american-crow" / "manifest.json"
    return json.loads(manifest.read_text())["recordings"]


class TestTheWordSurvivesTheExport:

    def test_a_fine_label_is_distinguishable_from_the_coarse_one(self, export,
                                                                labelled, db_path,
                                                                tmp_path):
        labelled("mobbing")
        record = run(export, db_path, tmp_path)[0]

        # Both, and they are not the same fact. `type` is what it trains as
        # today; `labels` is what somebody actually said.
        assert record["type"] == "alarm call"
        assert record["labels"] == "mobbing"

    def test_a_coarse_label_says_only_the_coarse_thing(self, export, labelled,
                                                       db_path, tmp_path):
        # The row a finer head must leave out rather than count against mobbing.
        # Nothing here can be read as "not mobbing".
        labelled("alarm call")
        record = run(export, db_path, tmp_path)[0]

        assert record["type"] == "alarm call"
        assert record["labels"] == "alarm call"

    def test_selecting_on_the_fine_word_finds_only_the_rows_that_said_it(
            self, export, labelled, db_path, tmp_path):
        # What a second-stage head would actually do, and the whole point: the
        # coarse row is absent from the selection instead of sitting in it as a
        # negative.
        labelled("mobbing", "alarm call")
        record = run(export, db_path, tmp_path)[0]

        said = set(record["labels"].split(","))
        assert "mobbing" in said and "alarm call" in said
        assert record["type"] == "alarm call"

    def test_a_file_with_two_core_classes_keeps_both_words(self, export, labelled,
                                                          db_path, tmp_path):
        labelled("mobbing", "rattle")
        record = run(export, db_path, tmp_path)[0]

        assert record["type"] == "alarm call,call"
        assert record["labels"] == "mobbing,rattle"


class TestWhatStillDoesNotTrain:

    def test_a_judgement_about_the_detection_is_not_exported_at_all(self, export,
                                                                   labelled,
                                                                   db_path,
                                                                   tmp_path):
        # "Not a crow" is a real, storable answer that maps to no training class.
        # It must not arrive as a word in `labels` either, or the next head to
        # select on that column picks it up as one.
        labelled("not_a_crow")
        assert run(export, db_path, tmp_path) == []

    def test_a_refined_label_exports_its_current_answer_only(self, client, recordist,
                                                             export, labelled,
                                                             db_path, tmp_path):
        # The superseded answer lives in label_revisions and has no business in a
        # training manifest — it is what somebody stopped believing.
        labelled("alarm call")
        capture_id = client.get("/api/captures",
                                headers=recordist.headers).get_json()[0]["id"]
        media_id = client.get(f"/api/captures/{capture_id}/labels",
                              headers=recordist.headers).get_json()[0]["media_id"]
        client.post(f"/api/captures/{capture_id}/labels",
                    json={"media_id": media_id, "call_type": "mobbing",
                          "client_uuid": "l-0", "config_version": 61},
                    headers=recordist.headers)

        record = run(export, db_path, tmp_path)[0]

        assert record["labels"] == "mobbing"
