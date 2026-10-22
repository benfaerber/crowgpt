"""Finding the crow-tools fork — and refusing to find the wrong one.

Fork resolution used to live in corpus.py, which meant a checkout with the
vendored labels and no fork still failed on `make corpus`. It now lives in
import_crowtools.py, the one script that genuinely needs a fork: re-importing the
labels if upstream ever changes. Nothing else in the project resolves one.

Lives in this suite for the same reason test_core_classes.py does: both modules
are pure stdlib, so they load here without the BirdNET venv, and this is the
suite that actually gets run.

The case worth protecting is the silent one. Searching past a CROW_TOOLS_DIR that
does not resolve would find the fork under ~/Code instead and re-import happily
from a corpus nobody asked for — a run that succeeds against the wrong data,
which is the failure you do not notice.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INGEST = REPO / "pipelines" / "ingest"


@pytest.fixture
def importer():
    """import_crowtools.py, loaded by path — it imports its sibling corpus.py."""
    sys.path.insert(0, str(INGEST))
    try:
        path = INGEST / "import_crowtools.py"
        spec = importlib.util.spec_from_file_location("import_crowtools_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(INGEST))


@pytest.fixture
def no_env_file(tmp_path):
    """Every test names its own .env, so none of them read the developer's.

    A real CROW_TOOLS_DIR line in the repo's .env would otherwise win over the
    search path and fail the discovery tests on one machine only.
    """
    return tmp_path / "absent.env"


def make_fork(root: Path) -> Path:
    """The shape resolve_fork looks for: a fork whose download has run once."""
    (root / ".cache" / "datasets" / "all-public").mkdir(parents=True)
    return root


def write_env(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


class TestDiscovery:
    def test_finds_a_fork_on_the_search_path(self, importer, tmp_path, monkeypatch,
                                             no_env_file):
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        fork = make_fork(tmp_path / "crow-tools")
        monkeypatch.setattr(importer, "SEARCH_PATH", (tmp_path / "nowhere", fork))
        assert importer.resolve_fork(env_file=no_env_file) == fork

    def test_the_first_candidate_wins(self, importer, tmp_path, monkeypatch, no_env_file):
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        first = make_fork(tmp_path / "sibling")
        second = make_fork(tmp_path / "home")
        monkeypatch.setattr(importer, "SEARCH_PATH", (first, second))
        assert importer.resolve_fork(env_file=no_env_file) == first

    def test_a_directory_without_the_cache_is_not_a_fork(self, importer, tmp_path,
                                                         monkeypatch, no_env_file):
        """An empty clone is the common near-miss: present, but never downloaded."""
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        bare = tmp_path / "crow-tools"
        bare.mkdir()
        monkeypatch.setattr(importer, "SEARCH_PATH", (bare,))
        with pytest.raises(FileNotFoundError):
            importer.resolve_fork(env_file=no_env_file)

    def test_the_error_names_everywhere_it_looked(self, importer, tmp_path, monkeypatch,
                                                  no_env_file):
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        candidates = (tmp_path / "a" / "crow-tools", tmp_path / "b" / "crow-tools")
        monkeypatch.setattr(importer, "SEARCH_PATH", candidates)
        with pytest.raises(FileNotFoundError) as e:
            importer.resolve_fork(env_file=no_env_file)
        for candidate in candidates:
            assert str(candidate) in str(e.value)

    def test_the_error_says_only_a_re_import_needs_one(self, importer, tmp_path,
                                                       monkeypatch, no_env_file):
        """Otherwise a missing fork reads as a broken checkout, which it is not."""
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        monkeypatch.setattr(importer, "SEARCH_PATH", (tmp_path / "nowhere",))
        with pytest.raises(FileNotFoundError, match="labels.json"):
            importer.resolve_fork(env_file=no_env_file)


class TestAPathSomeoneNamed:
    """Explicit beats discovery, and a wrong explicit path stops the run."""

    def test_the_env_var_beats_the_search_path(self, importer, tmp_path, monkeypatch,
                                               no_env_file):
        named = make_fork(tmp_path / "elsewhere")
        monkeypatch.setattr(importer, "SEARCH_PATH", (make_fork(tmp_path / "sibling"),))
        monkeypatch.setenv("CROW_TOOLS_DIR", str(named))
        assert importer.resolve_fork(env_file=no_env_file) == named

    def test_the_argument_beats_the_env_var(self, importer, tmp_path, monkeypatch):
        monkeypatch.setenv("CROW_TOOLS_DIR", str(make_fork(tmp_path / "env")))
        explicit = make_fork(tmp_path / "explicit")
        assert importer.resolve_fork(str(explicit)) == explicit

    def test_a_wrong_env_var_does_not_fall_back_to_a_real_fork(self, importer, tmp_path,
                                                               monkeypatch, no_env_file):
        monkeypatch.setattr(importer, "SEARCH_PATH", (make_fork(tmp_path / "real"),))
        monkeypatch.setenv("CROW_TOOLS_DIR", str(tmp_path / "typo"))
        with pytest.raises(FileNotFoundError, match="CROW_TOOLS_DIR"):
            importer.resolve_fork(env_file=no_env_file)

    def test_a_wrong_argument_says_which_knob_was_wrong(self, importer, tmp_path,
                                                        monkeypatch):
        monkeypatch.setenv("CROW_TOOLS_DIR", str(make_fork(tmp_path / "real")))
        with pytest.raises(FileNotFoundError, match=r"--fork"):
            importer.resolve_fork(str(tmp_path / "typo"))

    def test_a_tilde_is_expanded(self, importer, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        make_fork(tmp_path / "Code" / "crow-tools")
        assert importer.resolve_fork("~/Code/crow-tools") == tmp_path / "Code" / "crow-tools"


class TestTheEnvFile:
    """The repo-root .env, read through corpus.env_file_value."""

    def test_a_path_in_the_env_file_is_used(self, importer, tmp_path, monkeypatch):
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        fork = make_fork(tmp_path / "elsewhere")
        env = write_env(tmp_path / ".env", f"CROW_TOOLS_DIR={fork}\n")
        monkeypatch.setattr(importer, "SEARCH_PATH", ())
        assert importer.resolve_fork(env_file=env) == fork

    def test_the_real_env_var_beats_the_file(self, importer, tmp_path, monkeypatch):
        """A one-off `CROW_TOOLS_DIR=... python import_crowtools.py` wins."""
        shell = make_fork(tmp_path / "shell")
        env = write_env(tmp_path / ".env", f"CROW_TOOLS_DIR={make_fork(tmp_path / 'file')}\n")
        monkeypatch.setenv("CROW_TOOLS_DIR", str(shell))
        assert importer.resolve_fork(env_file=env) == shell

    def test_a_wrong_path_in_the_file_names_the_file(self, importer, tmp_path, monkeypatch):
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        monkeypatch.setattr(importer, "SEARCH_PATH", (make_fork(tmp_path / "real"),))
        env = write_env(tmp_path / ".env", f"CROW_TOOLS_DIR={tmp_path / 'typo'}\n")
        with pytest.raises(FileNotFoundError, match=r"CROW_TOOLS_DIR in \.env"):
            importer.resolve_fork(env_file=env)

    def test_the_shipped_example_leaves_discovery_alone(self, importer, tmp_path,
                                                        monkeypatch):
        """.env.example is all comments, so copying it changes nothing.

        It no longer documents CROW_TOOLS_DIR at all — that knob belongs to this
        script's --help, not to a root config file — but a live value appearing
        there later would break every fresh clone that put the fork somewhere
        sensible, so the invariant is still worth pinning.
        """
        monkeypatch.delenv("CROW_TOOLS_DIR", raising=False)
        fork = make_fork(tmp_path / "crow-tools")
        monkeypatch.setattr(importer, "SEARCH_PATH", (fork,))
        assert importer.resolve_fork(env_file=REPO / ".env.example") == fork
