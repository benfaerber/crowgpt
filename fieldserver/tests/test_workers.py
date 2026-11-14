"""The worker registry: workers.toml is the one list of workers, and the dev
recipe, the stop script and the hosted units are all read from it."""

import re
from pathlib import Path

import pytest

from fieldserver.core.workers import Registry, Units, Worker

FIELDSERVER = Path(__file__).resolve().parents[1]
BOX = Path("/home/ubuntu/crowgpt/fieldserver")


@pytest.fixture
def registry():
    return Registry.load(FIELDSERVER)


class TestRegistryFile:
    def test_every_worker_script_is_registered(self, registry):
        on_disk = {f"worker/{path.name}" for path in (FIELDSERVER / "worker").glob("*.py")}
        assert {worker.script for worker in registry.workers} == on_disk

    def test_the_stop_script_reads_the_same_scripts(self, registry):
        text = (FIELDSERVER / "workers.toml").read_text()
        assert re.findall(r'^script = "(.*)"$', text, flags=re.M) == [w.script for w in registry.workers]

    def test_an_unknown_worker_names_the_real_ones(self, registry):
        with pytest.raises(SystemExit, match="photo"):
            registry.get("nonesuch")

    def test_a_directory_without_a_registry_says_where_to_run(self, tmp_path):
        with pytest.raises(SystemExit, match="fieldserver/"):
            Registry.load(tmp_path)


class TestUnitText:
    def test_a_plain_worker_is_the_unit_already_on_the_box(self, registry):
        assert registry.get("generate").unit_text(BOX, "ubuntu") == (
            "[Unit]\n"
            "Description=CrowGPT generate worker\n"
            "After=crowgpt-field.service\n"
            "Requires=crowgpt-field.service\n"
            "\n"
            "[Service]\n"
            "User=ubuntu\n"
            "WorkingDirectory=/home/ubuntu/crowgpt/fieldserver\n"
            "EnvironmentFile=/home/ubuntu/crowgpt/fieldserver/instance/service.env\n"
            "ExecStart=/home/ubuntu/crowgpt/crowgpt/.venv/bin/python worker/generate_worker.py\n"
            "Restart=on-failure\n"
            "RestartSec=10\n"
            "\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

    def test_the_photo_worker_carries_its_cap_and_an_absolute_model_path(self, registry):
        unit = registry.get("photo").unit_text(BOX, "ubuntu")
        assert "MemoryMax=2600M\n" in unit
        assert "Environment=PHOTO_ID_MODEL=/home/ubuntu/crowgpt/data/photos/models/photo-id\n" in unit
        assert "ExecStart=/home/ubuntu/crowgpt/analyzer/photo/.venv/bin/python worker/photo_worker.py\n" in unit

    def test_the_box_runs_birdnet_from_its_one_torch_venv(self, registry):
        analyze = registry.get("analyze")
        assert analyze.python(BOX, hosted=True) == Path("/home/ubuntu/crowgpt/crowgpt/.venv/bin/python")
        assert analyze.python(BOX) != analyze.python(BOX, hosted=True)


class TestUnits:
    def make(self, tmp_path, *workers):
        root = tmp_path / "fieldserver"
        for worker in workers:
            python = worker.python(root, hosted=True)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.touch()
        unit_dir = tmp_path / "units"
        unit_dir.mkdir()
        return Units(Registry(root, workers), unit_dir, user="ubuntu")

    def test_a_local_only_worker_gets_no_unit(self, tmp_path):
        units = self.make(tmp_path, Worker("a", "A", "worker/a.py", ".venv"),
                          Worker("b", "B", "worker/b.py", ".venv", hosted=False))
        assert units.names() == ["crowgpt-a"]

    def test_a_worker_without_its_venv_is_skipped_and_named(self, tmp_path, capsys):
        units = self.make(tmp_path, Worker("a", "A", "worker/a.py", ".venv"))
        units.registry.workers.append(Worker("heavy", "H", "worker/h.py", "../heavy/.venv"))
        assert units.names() == ["crowgpt-a"]
        assert "heavy worker skipped" in capsys.readouterr().err

    def test_a_missing_unit_and_a_stale_unit_are_both_changes(self, tmp_path):
        a = Worker("a", "A", "worker/a.py", ".venv")
        b = Worker("b", "B", "worker/b.py", ".venv")
        units = self.make(tmp_path, a, b)
        (units.unit_dir / "crowgpt-b.service").write_text("[Unit]\nDescription=old\n")
        assert [worker.name for worker, _, _ in units.changes()] == ["a", "b"]
        assert "(not installed)" in units.diff() and "-Description=old" in units.diff()

    def test_an_installed_unit_that_matches_is_left_alone(self, tmp_path):
        a = Worker("a", "A", "worker/a.py", ".venv")
        units = self.make(tmp_path, a)
        (units.unit_dir / "crowgpt-a.service").write_text(a.unit_text(units.registry.root, "ubuntu"))
        assert units.changes() == [] and units.diff() == ""
