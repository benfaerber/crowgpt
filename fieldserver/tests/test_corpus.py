"""The corpus browser: read-only, honest about guesses, ranged for playback.

The endpoint reads a database the collection tooling maintains; these tests
write a scratch one. Source names in the fixtures are deliberately made up —
the `source` column is data the tooling defines, not vocabulary this repo
knows.
"""

import sqlite3

import pytest


def build_corpus(path, tmp_path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE recordings (
            id INTEGER PRIMARY KEY, source TEXT, source_ref TEXT, species TEXT,
            recordist TEXT, date TEXT, duration_seconds INTEGER, license TEXT,
            downloaded INTEGER, file_path TEXT, page_url TEXT, location TEXT,
            lat REAL, lng REAL, quality TEXT, analyzed_at TEXT,
            created_at TEXT DEFAULT '2026-08-01');
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY, recording_id INTEGER,
            start_seconds REAL, end_seconds REAL, species TEXT,
            scientific_name TEXT, confidence REAL, candidate INTEGER,
            call_type TEXT, call_type_confidence REAL,
            location_filtered INTEGER, analyzer TEXT, analyzed_at TEXT);
        """
    )
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 400)
    conn.executemany(
        "INSERT INTO recordings (id, source, source_ref, species, recordist, "
        "duration_seconds, downloaded, file_path, analyzed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "archive-a", "A1", "Carrion Crow", "ada", 120, 1, str(audio), "t"),
            (2, "archive-a", "A2", None, "ada", 3600, 1, str(audio), "t"),
            (3, "archive-b", "B1", "Rook", "bob", 60, 1, "/gone/away.wav", "t"),
            (4, "archive-b", "B2", None, "bob", 30, 0, None, None),
        ],
    )
    conn.executemany(
        "INSERT INTO detections (recording_id, start_seconds, end_seconds, "
        "species, confidence, candidate, analyzer, analyzed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'birdnet', 't')",
        [
            (1, 10.0, 14.0, "Carrion Crow", 0.9, 0),
            (1, 20.0, 22.0, "Carrion Crow", 0.4, 1),
            (2, 100.0, 130.0, "Rook", 0.8, 0),
            (3, 5.0, 8.0, "Rook", 0.85, 0),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    path = tmp_path / "corpus.db"
    build_corpus(path, tmp_path)
    monkeypatch.setenv("CORPUS_DB", str(path))
    return path


class TestSummary:
    def test_an_absent_corpus_is_a_normal_answer(self, client, operator, tmp_path, monkeypatch):
        monkeypatch.setenv("CORPUS_DB", str(tmp_path / "nowhere.db"))
        body = client.get("/api/corpus/summary", headers=operator.headers).get_json()
        assert body["available"] is False and body["sources"] == []

    def test_it_needs_an_operator(self, client, recordist, corpus):
        assert client.get("/api/corpus/summary").status_code == 401
        assert client.get("/api/corpus/summary",
                          headers=recordist.headers).status_code == 403

    def test_sources_and_species_roll_up_confident_calls_only(self, client, operator, corpus):
        body = client.get("/api/corpus/summary", headers=operator.headers).get_json()

        by_source = {s["source"]: s for s in body["sources"]}
        assert by_source["archive-a"]["calls"] == 2  # the candidate is not one
        assert body["totals"]["candidates"] == 1
        species = {s["species"]: s for s in body["species"]}
        assert species["Rook"]["calls"] == 2 and species["Rook"]["recordings"] == 2


class TestRecordingsList:
    def test_species_filter_means_the_detector_heard_it(self, client, operator, corpus):
        """Row 2 has no species of its own — the detector's Rook is what
        finds it."""
        body = client.get("/api/corpus/recordings?species=Rook",
                          headers=operator.headers).get_json()

        assert {r["id"] for r in body["recordings"]} == {2, 3}

    def test_with_calls_hides_the_silent(self, client, operator, corpus):
        body = client.get("/api/corpus/recordings?with_calls=1",
                          headers=operator.headers).get_json()

        assert {r["id"] for r in body["recordings"]} == {1, 2, 3}

    def test_the_default_sort_is_caw_seconds(self, client, operator, corpus):
        body = client.get("/api/corpus/recordings",
                          headers=operator.headers).get_json()

        assert body["recordings"][0]["id"] == 2  # 30 s of Rook beats 4 s of crow

    def test_paging_reports_the_real_total(self, client, operator, corpus):
        body = client.get("/api/corpus/recordings?limit=2&offset=0",
                          headers=operator.headers).get_json()

        assert len(body["recordings"]) == 2 and body["total"] == 4


class TestDetail:
    def test_a_recording_carries_its_detections_in_order(self, client, operator, corpus):
        body = client.get("/api/corpus/recordings/1",
                          headers=operator.headers).get_json()

        assert [d["start_seconds"] for d in body["detections"]] == [10.0, 20.0]
        assert body["detections"][1]["candidate"] == 1
        assert body["playable"] is True
        assert "file_path" not in body

    def test_a_missing_file_reads_as_unplayable_not_an_error(self, client, operator, corpus):
        body = client.get("/api/corpus/recordings/3",
                          headers=operator.headers).get_json()

        assert body["playable"] is False

    def test_an_unknown_recording_is_a_404(self, client, operator, corpus):
        assert client.get("/api/corpus/recordings/999",
                          headers=operator.headers).status_code == 404


class TestAudio:
    def test_the_stored_bytes_stream_with_range_support(self, client, operator, corpus):
        response = client.get("/api/corpus/recordings/1/audio",
                              headers=operator.headers)

        assert response.status_code == 200
        assert response.headers.get("Accept-Ranges") == "bytes"
        assert response.data.startswith(b"RIFF")

    def test_a_gone_file_is_a_404(self, client, operator, corpus):
        assert client.get("/api/corpus/recordings/3/audio",
                          headers=operator.headers).status_code == 404

    def test_a_never_downloaded_row_is_a_404(self, client, operator, corpus):
        assert client.get("/api/corpus/recordings/4/audio",
                          headers=operator.headers).status_code == 404
