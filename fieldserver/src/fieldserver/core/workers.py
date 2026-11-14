"""The worker registry: fieldserver/workers.toml, and everything derived from it.

Workers used to be listed by hand in the dev recipe, the stop script, a unit
file each on the hosted box, and the deploy's restart, status and log lines.
A fifth worker meant six edits and the box was the one that got forgotten.
Now the file is the list. Run from fieldserver/:

    python -m fieldserver.core.workers dev            every local worker, until signalled
    python -m fieldserver.core.workers run photo      one worker, in the foreground
    python -m fieldserver.core.workers units          the unit names this machine can run
    python -m fieldserver.core.workers diff           installed units against the registry
    python -m fieldserver.core.workers install        write the units that differ (sudo)
"""

import argparse
import difflib
import getpass
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10, which the hosted venv is
    import tomli as tomllib

REGISTRY_FILE = "workers.toml"
UNIT_DIR = Path("/etc/systemd/system")
SERVER_UNIT = "crowgpt-field"
PATH_VARIABLES = ("PHOTO_ID_MODEL",)


@dataclass(frozen=True)
class Worker:
    name: str
    description: str
    script: str
    venv: str
    hosted_venv: str | None = None
    hosted: bool = True
    environment: dict = field(default_factory=dict)
    memory_max: str | None = None
    requires_server: bool = True
    restart_seconds: int = 10

    @property
    def unit(self) -> str:
        return f"crowgpt-{self.name}"

    def python(self, root: Path, hosted=False) -> Path:
        venv = self.hosted_venv if hosted and self.hosted_venv else self.venv
        return Path(os.path.normpath(root / venv / "bin" / "python"))

    def resolved_environment(self, root: Path) -> dict:
        """Paths in the registry are relative to fieldserver/; a process or a
        unit needs them absolute."""
        return {key: os.path.normpath(root / value) if key in PATH_VARIABLES else value
                for key, value in self.environment.items()}

    def unit_text(self, root: Path, user: str) -> str:
        lines = [
            "[Unit]",
            f"Description={self.description}",
            f"After={SERVER_UNIT}.service",
            *([f"Requires={SERVER_UNIT}.service"] if self.requires_server else []),
            "",
            "[Service]",
            f"User={user}",
            f"WorkingDirectory={root}",
            f"EnvironmentFile={root / 'instance' / 'service.env'}",
            *(f"Environment={key}={value}" for key, value in self.resolved_environment(root).items()),
            f"ExecStart={self.python(root, hosted=True)} {self.script}",
            *([f"MemoryMax={self.memory_max}"] if self.memory_max else []),
            "Restart=on-failure",
            f"RestartSec={self.restart_seconds}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
        ]
        return "\n".join(lines) + "\n"


class Registry:
    def __init__(self, root: Path, workers):
        self.root = root
        self.workers = list(workers)

    @classmethod
    def load(cls, root: Path | None = None):
        root = Path(root or Path.cwd()).resolve()
        path = root / REGISTRY_FILE
        if not path.exists():
            raise SystemExit(f"No {REGISTRY_FILE} in {root}: run this from fieldserver/")
        with open(path, "rb") as handle:
            entries = tomllib.load(handle)
        return cls(root, [Worker(name=name, **entry) for name, entry in entries.items()])

    def get(self, name: str) -> Worker:
        for worker in self.workers:
            if worker.name == name:
                return worker
        raise SystemExit(f"No worker named {name}: {', '.join(w.name for w in self.workers)}")

    def runnable(self, hosted=False):
        """The workers whose venv exists here. The rest are named on stderr,
        because a silently missing worker reads as a page that never answers."""
        found = []
        for worker in self.workers:
            if hosted and not worker.hosted:
                continue
            if worker.python(self.root, hosted).exists():
                found.append(worker)
            else:
                print(f"{worker.name} worker skipped: no {worker.python(self.root, hosted)}", file=sys.stderr)
        return found

    def command(self, worker: Worker):
        return [str(worker.python(self.root)), worker.script]

    def process_environment(self) -> dict:
        """A local worker takes the shell's environment as it is; the
        registry's `environment` is for the hosted unit, which has no shell."""
        return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


class Supervisor:
    """Runs every local worker as a child and takes them down together."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self.children = []

    def run(self):
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        for worker in self.registry.runnable():
            self.children.append(subprocess.Popen(
                self.registry.command(worker), cwd=self.registry.root,
                env=self.registry.process_environment()))
        for child in self.children:
            child.wait()

    def _stop(self, *_):
        for child in self.children:
            if child.poll() is None:
                child.terminate()


class Units:
    """The registry as systemd units on this machine."""

    def __init__(self, registry: Registry, unit_dir: Path = UNIT_DIR, user: str | None = None):
        self.registry = registry
        self.unit_dir = unit_dir
        self.user = user or getpass.getuser()

    def names(self):
        return [worker.unit for worker in self.registry.runnable(hosted=True)]

    def changes(self):
        """(worker, installed text or None, wanted text) for each unit that
        is not what the registry says."""
        pending = []
        for worker in self.registry.runnable(hosted=True):
            path = self.unit_dir / f"{worker.unit}.service"
            installed = path.read_text() if path.exists() else None
            wanted = worker.unit_text(self.registry.root, self.user)
            if installed != wanted:
                pending.append((worker, installed, wanted))
        return pending

    def diff(self) -> str:
        parts = []
        for worker, installed, wanted in self.changes():
            name = f"{worker.unit}.service"
            parts.append("".join(difflib.unified_diff(
                (installed or "").splitlines(keepends=True), wanted.splitlines(keepends=True),
                f"installed/{name}" if installed is not None else "(not installed)", f"registry/{name}")))
        return "\n".join(parts)

    def install(self):
        pending = self.changes()
        for worker, _, wanted in pending:
            with tempfile.NamedTemporaryFile("w", suffix=".service") as staged:
                staged.write(wanted)
                staged.flush()
                target = self.unit_dir / f"{worker.unit}.service"
                subprocess.run(["sudo", "install", "-m", "644", staged.name, str(target)], check=True)
            print(f"wrote {worker.unit}.service")
        if pending:
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", "-q", *(w.unit for w, _, _ in pending)], check=True)
        return pending


def main():
    parser = argparse.ArgumentParser(description="The field server's workers, from workers.toml.")
    parser.add_argument("action", choices=["dev", "run", "list", "units", "diff", "install"])
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    registry = Registry.load()
    if args.action == "dev":
        Supervisor(registry).run()
    elif args.action == "run":
        worker = registry.get(args.name or "")
        os.chdir(registry.root)
        os.execve(registry.command(worker)[0], registry.command(worker), registry.process_environment())
    elif args.action == "list":
        for worker in registry.workers:
            where = "local and hosted" if worker.hosted else "local only"
            print(f"{worker.name:12s} {worker.script:30s} {where}")
    elif args.action == "units":
        print(" ".join(Units(registry).names()))
    elif args.action == "diff":
        print(Units(registry).diff() or "every hosted unit matches the registry")
    elif args.action == "install":
        if not Units(registry).install():
            print("units already match the registry")


if __name__ == "__main__":
    main()
