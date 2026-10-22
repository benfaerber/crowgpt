"""The vendored label corpus loads with no fork anywhere on the machine.

crow-tools is abandonware. Everything Cawtalker took from it splits into audio,
which the corpus tooling (a private repo) can re-fetch by id, and 3,162
hand-reviewed segments, which
nobody can. import_crowtools.py moved the second half into a committed file, and
these are the checks that it is genuinely self-sufficient — the failure they
guard against is a checkout that works only on the one machine where the fork
still happens to exist.

corpus.py no longer knows what a fork is; that lives in import_crowtools.py and
is tested in test_import_crowtools_fork.py.

Lives in this suite because corpus.py is pure stdlib, like manifest.py.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

FLAGS = {"reviewed": True, "mob": True}
SONG = {"reviewed": True, "softSong": True}
UNLABELLED = {"reviewed": True}


@pytest.fixture
def corpus():
    path = REPO / "pipelines" / "ingest" / "corpus.py"
    spec = importlib.util.spec_from_file_location("corpus_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def imported(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({
        "source": "crow-tools all-public",
        "libraries": {"111": "library-1", "222": "library-2"},
        "labels": {"111-0-1": FLAGS, "222-3-4": SONG, "111-9-10": UNLABELLED},
    }))
    return path


@pytest.fixture
def audio(tmp_path, corpus, monkeypatch):
    directory = tmp_path / "audio"
    directory.mkdir()
    for name in ("111", "222"):
        (directory / f"{name}.mp3").write_bytes(b"")
    monkeypatch.setattr(corpus, "LOCAL_AUDIO", directory)
    return directory


class TestTheVendoredCorpus:
    def test_labelled_segments_resolve(self, corpus, imported, audio):
        found = list(corpus.LabelCorpus(imported=imported).labeled_segments())

        assert {s.key for s in found} == {"111-0-1", "222-3-4"}

    def test_a_segment_with_no_core_label_is_dropped(self, corpus, imported, audio):
        found = list(corpus.LabelCorpus(imported=imported).labeled_segments())

        assert "111-9-10" not in {s.key for s in found}

    def test_audio_comes_from_the_local_corpus(self, corpus, imported, audio):
        found = {s.key: s for s in corpus.LabelCorpus(imported=imported).labeled_segments()}

        assert found["111-0-1"].audio_path == audio / "111.mp3"

    def test_the_library_survives_the_import(self, corpus, imported, audio):
        """It is not recoverable from the filename — both archives use bare ids."""
        found = {s.key: s for s in corpus.LabelCorpus(imported=imported).labeled_segments()}

        assert found["111-0-1"].library == "library-1"
        assert found["222-3-4"].library == "library-2"

    def test_a_recording_not_yet_downloaded_is_skipped_not_crashed(self, corpus, imported,
                                                                   audio):
        (audio / "222.mp3").unlink()

        found = list(corpus.LabelCorpus(imported=imported).labeled_segments())

        assert {s.key for s in found} == {"111-0-1"}

    def test_no_audio_at_all_is_reportable_rather_than_fatal(self, corpus, imported,
                                                             tmp_path, monkeypatch):
        """`make corpus` on a fresh clone: labels present, download not yet run."""
        monkeypatch.setattr(corpus, "LOCAL_AUDIO", tmp_path / "never-downloaded")

        store = corpus.LabelCorpus(imported=imported)

        assert list(store.labeled_segments(require_audio=True)) == []
        assert len(list(store.labeled_segments(require_audio=False))) == 2

    def test_absent_labels_name_the_script_that_writes_them(self, corpus, tmp_path):
        store = corpus.LabelCorpus(imported=tmp_path / "gone.json")

        with pytest.raises(FileNotFoundError, match="import_crowtools.py"):
            store.labels()


class TestTheImportedFileItself:
    def test_it_is_committed_and_carries_the_labels(self):
        """If this file goes missing the project loses its only real ground truth."""
        path = REPO / "pipelines" / "ingest" / "crowtools" / "labels.json"
        assert path.exists(), "run pipelines/ingest/import_crowtools.py"

        payload = json.loads(path.read_text())
        assert len(payload["labels"]) > 3000
        assert set(payload["libraries"].values()) <= {"library-1", "library-2"}

    def test_every_labelled_recording_knows_its_library(self):
        """Without it a re-download cannot tell which archive to ask."""
        payload = json.loads(
            (REPO / "pipelines" / "ingest" / "crowtools" / "labels.json").read_text()
        )
        referenced = {key.rsplit("-", 2)[0] for key in payload["labels"]}

        assert referenced - set(payload["libraries"]) == set()

    def test_the_upstream_licence_travels_with_it(self):
        """MIT: redistributing the labels here means shipping their licence."""
        licence = REPO / "pipelines" / "ingest" / "crowtools" / "LICENSE.md"
        assert licence.exists()
        assert "OpenShot Studios" in licence.read_text()


class TestTheEnvFileReader:
    """corpus.env_file_value is generic — tools/backup.py reads BACKUP_DIR with it."""

    @pytest.mark.parametrize("line, expected", [
        ("BACKUP_DIR=/a/b", "/a/b"),
        ("export BACKUP_DIR=/a/b", "/a/b"),
        ('BACKUP_DIR="/a/b"', "/a/b"),
        ("BACKUP_DIR = /a/b", "/a/b"),
        ("#BACKUP_DIR=/a/b", None),
        ("BACKUP_DIR=", None),
        ("OTHER=/a/b", None),
    ])
    def test_it_parses_what_a_person_would_write(self, corpus, tmp_path, line, expected):
        env = tmp_path / ".env"
        env.write_text(line + "\n")

        assert corpus.env_file_value("BACKUP_DIR", env) == expected
