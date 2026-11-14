"""The worker registry: workers.toml is the one list of workers, and the dev
recipe, the stop script and the hosted units are all read from it."""

import re
from pathlib import Path

import pytest

from fieldserver.core.workers import (
    Registry, Sandbox, Units, Worker, server_unit_text, worker_environment,
)

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
    def test_a_plain_worker_runs_from_the_secret_free_environment(self, registry):
        unit = registry.get("generate").unit_text(BOX, "ubuntu")
        assert unit.startswith(
            "[Unit]\n"
            "Description=CrowGPT generate worker\n"
            "After=crowgpt-field.service\n"
            "Requires=crowgpt-field.service\n"
            "\n"
            "[Service]\n"
            "User=ubuntu\n"
            "WorkingDirectory=/home/ubuntu/crowgpt/fieldserver\n"
            "EnvironmentFile=/home/ubuntu/crowgpt/fieldserver/instance/worker.env\n"
            "ExecStart=/home/ubuntu/crowgpt/crowgpt/.venv/bin/python worker/generate_worker.py\n"
            "MemoryMax=1600M\n"
            "Restart=on-failure\n"
            "RestartSec=10\n"
            "NoNewPrivileges=yes\n"
        )
        assert unit.endswith("\n[Install]\nWantedBy=multi-user.target\n")

    @pytest.mark.parametrize("name", ["analyze", "generate", "photo"])
    def test_a_worker_that_reads_uploads_is_confined(self, registry, name):
        """These decode files strangers send. None may gain privileges, reach
        the network, open the secrets, see the server's process or write
        outside instance/ and data/."""
        lines = registry.get(name).unit_text(BOX, "ubuntu").splitlines()
        instance = "/home/ubuntu/crowgpt/fieldserver/instance"
        for wanted in (
            "NoNewPrivileges=yes", "PrivateNetwork=yes", "PrivatePIDs=yes", "KillSignal=SIGINT",
            "ProtectSystem=strict", "ProtectHome=tmpfs", "CapabilityBoundingSet=",
            f"InaccessiblePaths=-{instance}/service.env -{instance}/secrets.env",
            f"ReadWritePaths={instance} -/home/ubuntu/crowgpt/data",
            f"EnvironmentFile={instance}/worker.env",
        ):
            assert wanted in lines, wanted
        bound = next(line for line in lines if line.startswith("BindReadOnlyPaths="))
        assert bound.split("=", 1)[1].split()[0] == "/home/ubuntu/crowgpt"
        assert "/home/ubuntu/.ssh" not in bound

    def test_the_scout_scheduler_keeps_its_network_and_disk_but_not_sudo_or_the_servers_secrets(
            self, registry):
        lines = registry.get("scout").unit_text(BOX, "ubuntu").splitlines()
        assert "NoNewPrivileges=yes" in lines
        assert "PrivateNetwork=yes" not in lines and "ProtectHome=tmpfs" not in lines
        assert "EnvironmentFile=/home/ubuntu/crowgpt/fieldserver/instance/worker.env" in lines

    def test_the_server_is_confined_but_keeps_its_network_and_environment(self):
        lines = server_unit_text(BOX, "ubuntu").splitlines()
        assert "ExecStart=/home/ubuntu/crowgpt/fieldserver/.venv/bin/fieldserver" in lines
        assert "EnvironmentFile=/home/ubuntu/crowgpt/fieldserver/instance/service.env" in lines
        assert "NoNewPrivileges=yes" in lines and "ProtectHome=tmpfs" in lines
        assert "PrivateNetwork=yes" not in lines
        assert not any(line.startswith("InaccessiblePaths=") for line in lines)

    def test_every_sandbox_line_is_one_directive(self):
        for line in Sandbox(BOX).worker("crowgpt-x", network=False):
            assert re.fullmatch(r"[A-Za-z]+=\S*( \S+)*", line), line


class TestWorkerEnvironment:
    def test_settings_pass_and_every_secret_stays_behind(self):
        server = (
            "PATH=/usr/bin\nFIELD_LAT=40.7\nFIELD_LON=-111.9\nFIELD_REGION=Utah\n"
            "FIELD_ENROLL_TOKEN=aaa\nFIELD_OPERATOR_TOKEN=bbb\nFIELD_TURNSTILE_SECRET=ccc\n"
            "FIELD_GITHUB_CLIENT_SECRET=ddd\nRESEND_API_KEY=eee\nCLOUDFLARE_API_TOKEN=fff\n"
            "EBIRD_API_KEY=ggg\nFIELD_PREVIEW_PASSWORD=hhh\nFIELD_TRUST_PROXY=1\n"
            "WORKER_POLL=2\nPHOTO_ID_IDLE_MINUTES=10\nANALYZER_API_KEY=iii\n# a comment\n\n"
        )
        assert worker_environment(server) == (
            "PATH=/usr/bin\nFIELD_LAT=40.7\nFIELD_LON=-111.9\nFIELD_REGION=Utah\n"
            "WORKER_POLL=2\nPHOTO_ID_IDLE_MINUTES=10\n")

    def test_install_writes_it_private_beside_the_servers(self, tmp_path):
        units = Units(Registry(tmp_path, []), tmp_path / "units")
        instance = tmp_path / "instance"
        instance.mkdir()
        (instance / "service.env").write_text("FIELD_REGION=Utah\nFIELD_OPERATOR_TOKEN=bbb\n")
        assert units.write_worker_environment()
        written = instance / "worker.env"
        assert written.read_text() == "FIELD_REGION=Utah\n"
        assert written.stat().st_mode & 0o777 == 0o600

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
        assert [unit for unit, _, _ in units.changes()] == ["crowgpt-field", "crowgpt-a", "crowgpt-b"]
        assert "(not installed)" in units.diff() and "-Description=old" in units.diff()

    def test_an_installed_unit_that_matches_is_left_alone(self, tmp_path):
        a = Worker("a", "A", "worker/a.py", ".venv")
        units = self.make(tmp_path, a)
        (units.unit_dir / "crowgpt-a.service").write_text(a.unit_text(units.registry.root, "ubuntu"))
        (units.unit_dir / "crowgpt-field.service").write_text(
            server_unit_text(units.registry.root, "ubuntu"))
        assert units.changes() == [] and units.diff() == ""
