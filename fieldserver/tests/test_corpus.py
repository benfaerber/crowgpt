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
            call_type TEXT, raw TEXT,
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
        assert response.data.startswith(b"RIFF")
        # Werkzeug need not advertise Accept-Ranges on a full 200 response.
        # Exercise seeking itself, including with private/no-store responses.
        partial = client.get("/api/corpus/recordings/1/audio",
                             headers={**operator.headers, "Range": "bytes=0-3"})
        assert partial.status_code == 206
        assert partial.headers["Accept-Ranges"] == "bytes"
        assert partial.headers["Content-Range"].startswith("bytes 0-3/")
        assert partial.data == b"RIFF"

    def test_a_gone_file_is_a_404(self, client, operator, corpus):
        assert client.get("/api/corpus/recordings/3/audio",
                          headers=operator.headers).status_code == 404

    def test_a_never_downloaded_row_is_a_404(self, client, operator, corpus):
        assert client.get("/api/corpus/recordings/4/audio",
                          headers=operator.headers).status_code == 404


def add_documentation(path):
    """Four shapes a source might use: letter grade with a remark and
    background species, numeric rating with notes, review state with nothing
    written, and an ungraded row with timed annotations."""
    conn = sqlite3.connect(path)
    conn.executemany(
        "UPDATE recordings SET quality = ?, call_type = ?, raw = ? WHERE id = ?",
        [
            ("A", "alarm call", '{"rmk": "two birds mobbing a hawk", "also": ["Robin"],'
                                ' "animal-seen": "yes"}', 1),
            ("4.50", None, '{"mediaNotes": "adult calling near feeders", "ratingCount": 12}', 2),
            ("needs_id", "uncertain", '{"rmk": ""}', 3),
            (None, None, '{"events": [{"tags": ["Rook"], "start_time_seconds": 2.0,'
                         ' "end_time_seconds": 4.5}]}', 4),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def documented(corpus):
    add_documentation(corpus)
    return corpus


class TestQuality:
    def test_grades_of_every_shape_land_in_one_tier_scale(self, client, operator, documented):
        body = client.get("/api/corpus/recordings", headers=operator.headers).get_json()

        tiers = {r["id"]: r["tier"] for r in body["recordings"]}
        assert tiers == {1: "high", 2: "high", 3: "mid", 4: "unrated"}

    def test_a_remark_is_whichever_text_field_the_row_carries(self, client, operator, documented):
        body = client.get("/api/corpus/recordings?has_remark=1",
                          headers=operator.headers).get_json()

        assert {r["id"] for r in body["recordings"]} == {1, 2}

    def test_uncertain_is_not_a_label(self, client, operator, documented):
        body = client.get("/api/corpus/recordings?labelled=1",
                          headers=operator.headers).get_json()

        assert {r["id"] for r in body["recordings"]} == {1}

    def test_search_reaches_the_remark(self, client, operator, documented):
        body = client.get("/api/corpus/recordings?q=hawk",
                          headers=operator.headers).get_json()

        assert {r["id"] for r in body["recordings"]} == {1}

    def test_clean_hides_rows_with_other_species_named(self, client, operator, documented):
        body = client.get("/api/corpus/recordings?clean=1",
                          headers=operator.headers).get_json()

        assert 1 not in {r["id"] for r in body["recordings"]}

    def test_the_summary_counts_each_signal_per_source(self, client, operator, documented):
        body = client.get("/api/corpus/summary", headers=operator.headers).get_json()

        by_source = {q["source"]: q for q in body["quality"]}
        assert by_source["archive-a"]["with_remark"] == 2
        assert by_source["archive-b"]["annotated"] == 1
        assert body["quality_totals"]["tier_high"] == 2

    def test_the_detail_carries_what_the_source_said(self, client, operator, documented):
        one = client.get("/api/corpus/recordings/1", headers=operator.headers).get_json()
        four = client.get("/api/corpus/recordings/4", headers=operator.headers).get_json()

        assert one["tier"] == "high"
        assert one["notes"]["remark"] == "two birds mobbing a hawk"
        assert one["notes"]["background"] == ["Robin"]
        assert one["notes"]["flags"]["animal seen"] == "yes"
        assert four["notes"]["annotations"][0]["label"] == "Rook"
        assert "raw" not in one

    def test_html_in_a_remark_reads_as_text(self, client, operator, corpus):
        conn = sqlite3.connect(corpus)
        conn.execute("UPDATE recordings SET raw = ? WHERE id = 1",
                     ('{"rmk": "<p style=\\"x\\">Crows &amp; a hawk</p><p>later</p>"}',))
        conn.commit()
        conn.close()

        detail = client.get("/api/corpus/recordings/1", headers=operator.headers).get_json()
        listed = client.get("/api/corpus/recordings?q=hawk", headers=operator.headers).get_json()

        assert detail["notes"]["remark"] == "Crows & a hawk\nlater"
        assert listed["recordings"][0]["remark_preview"] == "Crows & a hawk later"

    def test_a_row_without_raw_still_reads(self, client, operator, corpus):
        body = client.get("/api/corpus/recordings/1", headers=operator.headers).get_json()

        assert body["notes"]["remark"] is None
