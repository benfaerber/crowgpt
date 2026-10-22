"""A re-fetch must not take the field labels down with it.

data/species/<slug>/manifest.json is written from two ends: the corpus tooling
(a private repo since 2026-08-05, carrying a vendored copy of manifest.py)
re-fetches a whole species query, export_manifest.py appends human-labelled
captures out of the field DB. The two writers sit either side of a repo
boundary and this is the only thing left holding them to one format. The
tooling used to write the file whole, so re-fetching a species you had already
exported into silently dropped every field label — the training set shrank and
the only symptom was a head that scored slightly worse than it should have.

Field labels are the scarce half of this corpus (14 rows against ~2,500 seeded
segments), and they are the only human ground truth in it. Lives in this suite
because manifest.py is pure stdlib, like corpus.py — see test_corpus_fork.py.

Stamps here are opaque: the tooling writes its own values, and this side only
cares that a run replaces its own stamp and nothing else, so the fixtures use
placeholder archives A and B.
"""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIO = "/data/species/american-crow/audio"
MEDIA = "/fieldserver/instance/media"

ARCHIVE_A = "archive-a"
ARCHIVE_B = "archive-b"


@pytest.fixture
def manifest():
    path = REPO / "pipelines" / "ingest" / "manifest.py"
    spec = importlib.util.spec_from_file_location("manifest_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archived(name, stamped=True):
    rec = {"id": name, "path": f"{AUDIO}/{name}.mp3", "type": "call"}
    return {**rec, "source": ARCHIVE_A} if stamped else rec


def exported(name, stamped=True):
    rec = {"path": f"{MEDIA}/{name}.wav", "type": "begging"}
    return {**rec, "source": "field"} if stamped else rec


class TestARefetch:
    def test_field_records_survive(self, manifest):
        existing = [archived("A1"), archived("A2"), exported("cap69")]
        records, kept = manifest.merge_archive(existing, [archived("A9")], AUDIO,
                                               stamp=ARCHIVE_A)
        assert kept == [exported("cap69")]
        assert exported("cap69") in records

    def test_the_previous_run_is_replaced_not_appended(self, manifest):
        """The run is a re-fetch of the same query, not a second corpus."""
        existing = [archived("A1"), archived("A2")]
        records, _ = manifest.merge_archive(existing, [archived("A1")], AUDIO,
                                            stamp=ARCHIVE_A)
        assert [r["id"] for r in records] == ["A1"]

    def test_a_run_that_returns_nothing_keeps_the_field_labels(self, manifest):
        """A failed or empty re-fetch must not be a way to empty the manifest."""
        existing = [archived("A1"), exported("cap69")]
        records, kept = manifest.merge_archive(existing, [], AUDIO, stamp=ARCHIVE_A)
        assert records == [exported("cap69")]
        assert len(kept) == 1

    def test_a_first_run_writes_cleanly(self, manifest):
        records, kept = manifest.merge_archive([], [archived("A1")], AUDIO,
                                               stamp=ARCHIVE_A)
        assert records == [archived("A1")]
        assert kept == []

    def test_a_field_record_is_not_duplicated_by_a_colliding_path(self, manifest):
        existing = [exported("cap69")]
        collision = {"id": "A1", "path": f"{MEDIA}/cap69.wav", "source": ARCHIVE_A}
        records, _ = manifest.merge_archive(existing, [collision], AUDIO,
                                            stamp=ARCHIVE_A)
        assert len(records) == 1


class TestManifestsWrittenBeforeTheStamp:
    """The five species already on disk have no `source` on any record."""

    def test_audio_under_the_species_dir_reads_as_archive(self, manifest):
        assert manifest.source_of(archived("A1", stamped=False), AUDIO) == manifest.ARCHIVE

    def test_anything_else_reads_as_field(self, manifest):
        assert manifest.source_of(exported("cap69", stamped=False), AUDIO) == "field"

    def test_an_unstamped_field_record_still_survives_a_refetch(self, manifest):
        """The case that matters: an old manifest, exported into, then re-fetched."""
        existing = [archived("A1", stamped=False), exported("cap69", stamped=False)]
        records, kept = manifest.merge_archive(existing, [archived("A9")], AUDIO,
                                               stamp=manifest.ARCHIVE)
        assert kept == [exported("cap69", stamped=False)]
        assert len(records) == 2

    def test_a_stamp_beats_the_path_guess(self, manifest):
        """Where the two disagree, what the writer said wins."""
        odd = {"path": f"{AUDIO}/A1.mp3", "source": "field"}
        assert manifest.source_of(odd, AUDIO) == "field"


class TestOnDisk:
    def test_load_of_a_missing_manifest_is_empty(self, manifest, tmp_path):
        assert manifest.load(tmp_path / "nope.json") == {}

    def test_write_then_load_round_trips(self, manifest, tmp_path):
        path = tmp_path / "species" / "american-crow" / "manifest.json"
        manifest.write(path, [archived("A1")], slug="american-crow", query="gen:Corvus")
        loaded = manifest.load(path)
        assert loaded["slug"] == "american-crow"
        assert loaded["query"] == "gen:Corvus"
        assert loaded["recordings"] == [archived("A1")]


def from_archive_b(name):
    return {"id": name, "path": f"{AUDIO}/{name}.mp3", "type": "call",
            "source": ARCHIVE_B, "recordist": "Jim", "date": "2018-06-14"}


class TestTwoArchivesFeedingOneSpecies:
    """Two archives write the same manifest from opposite ends.

    Before the stamp was a parameter, a run replaced everything it recognised
    as archive-written — so whichever archive ran last was the only one left,
    and a species that had been fed by both silently halved.
    """

    def test_a_b_run_leaves_a_alone(self, manifest):
        existing = [archived("A1"), from_archive_b("B1")]
        records, kept = manifest.merge_archive(
            existing, [from_archive_b("B2")], AUDIO, stamp=ARCHIVE_B
        )

        assert {r["id"] for r in records} == {"B2", "A1"}
        assert [r["id"] for r in kept] == ["A1"]

    def test_an_a_run_leaves_b_alone(self, manifest):
        existing = [archived("A1"), from_archive_b("B1")]
        records, kept = manifest.merge_archive(existing, [archived("A2")], AUDIO,
                                               stamp=ARCHIVE_A)

        assert {r["id"] for r in records} == {"A2", "B1"}
        assert [r["id"] for r in kept] == ["B1"]

    def test_field_records_survive_either_archive(self, manifest):
        existing = [exported("cap88"), archived("A1"), from_archive_b("B1")]
        for stamp in (ARCHIVE_A, ARCHIVE_B):
            records, _ = manifest.merge_archive(existing, [], AUDIO, stamp=stamp)
            assert any(r.get("source") == "field" for r in records)


class TestARecordCarriesItsProvenance:
    def test_recordist_and_date_are_kept_for_grouping(self, manifest):
        row = manifest.record("B9", "/a/B9.mp3", ARCHIVE_B,
                              recordist="Jim", date="2018-06-14", locality="U Street")

        assert row["recordist"] == "Jim" and row["date"] == "2018-06-14"
        assert row["source"] == ARCHIVE_B

    def test_absent_metadata_is_omitted_rather_than_null(self, manifest):
        """The oldest manifests predate these fields; absent must not read as empty."""
        row = manifest.record("A9", "/a/A9.mp3", ARCHIVE_A)

        assert "recordist" not in row and "date" not in row


class TestWritingWhileSomethingElseReads:
    """The tooling rewrites this every few hundred downloads; training reads it.

    Those overlap on purpose — the download is meant to keep running overnight —
    so a reader must never catch the file half-written.
    """

    def test_a_reader_never_sees_a_partial_manifest(self, manifest, tmp_path):
        import json
        import threading

        path = tmp_path / "manifest.json"
        big = [archived(f"A{i}") for i in range(4000)]
        manifest.write(path, big, slug="american-crow")

        seen, stop = [], threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    seen.append(len(json.loads(path.read_text())["recordings"]))
                except (ValueError, FileNotFoundError) as exc:
                    seen.append(exc)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        for n in range(4000, 4600, 100):
            manifest.write(path, [archived(f"A{i}") for i in range(n)], slug="american-crow")
        stop.set()
        thread.join(timeout=5)

        broken = [s for s in seen if not isinstance(s, int)]
        assert not broken, f"reader saw {len(broken)} partial writes, e.g. {broken[0]!r}"
        assert seen, "the reader never got a look in"

    def test_no_staging_file_is_left_behind(self, manifest, tmp_path):
        path = tmp_path / "manifest.json"
        manifest.write(path, [archived("A1")], slug="rook")

        assert list(tmp_path.iterdir()) == [path]
