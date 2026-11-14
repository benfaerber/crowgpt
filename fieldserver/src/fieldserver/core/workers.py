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

THE UNITS ARE SANDBOXES. The analyze and photo workers decode files that
strangers upload, with ffmpeg, Pillow and torch, and every unit used to run
as the login user with that user's passwordless sudo and the server's whole
environment. A bug in any decoder was root on the box and every secret on
it. Now a worker sees the repository read-only and nothing else of the home
directory, writes only to instance/ and data/, has no network, cannot see the
server's process, cannot gain privileges (which is what stops sudo), and is
started with instance/worker.env: the server's settings with every secret
left out. The server itself is held the same way, keeping its network and its
secrets. `Sandbox` below is the one place that says what each of those is.
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

#: The server's environment file, and the copy of it a worker is given.
SERVER_ENV = "service.env"
WORKER_ENV = "worker.env"

#: Files in instance/ that hold secrets. A sandboxed worker cannot open them
#: even though instance/ is where it writes.
SECRET_FILES = ("service.env", "secrets.env")

#: The settings a worker may be handed, by prefix. Everything else in the
#: server's environment stays with the server; a name that looks like a
#: secret is dropped even when its prefix is here.
WORKER_SETTINGS = ("PATH", "FIELD_DB", "FIELD_LAT", "FIELD_LON", "FIELD_REGION",
                   "DATA_DIR", "PROGRESS_DIR", "WORKER_", "ANALYZER_", "PHOTO_ID_",
                   "GENERATION_", "DICTATION_", "CROWGPT_")
SECRET_WORDS = ("TOKEN", "SECRET", "KEY", "PASSWORD")


def worker_environment(server_environment: str) -> str:
    """The lines of the server's environment file a worker may have."""
    kept = []
    for line in server_environment.splitlines():
        name = line.split("=", 1)[0].strip()
        if "=" not in line or name.startswith("#"):
            continue
        if not name.startswith(WORKER_SETTINGS) or any(word in name for word in SECRET_WORDS):
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


class Sandbox:
    """The systemd directives that confine a unit, from where the tree lives.

    The repository sits in the login user's home, so the home directory is
    replaced by an empty one and only what a unit needs is bound back in: the
    repository and the interpreters and model caches the venvs point at, all
    read-only, then instance/ and data/ writable on top.
    """

    #: What every unit gets, however much else it is trusted with.
    #: NoNewPrivileges is the line that makes sudo fail.
    BASE = (
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectKernelLogs=yes",
        "ProtectControlGroups=yes",
        "ProtectClock=yes",
        "ProtectHostname=yes",
        "RestrictSUIDSGID=yes",
        "RestrictRealtime=yes",
        "RestrictNamespaces=yes",
        "LockPersonality=yes",
        "CapabilityBoundingSet=",
        "SystemCallArchitectures=native",
    )

    def __init__(self, root: Path):
        self.root = root
        self.repo = root.parent
        self.home = self.repo.parent
        self.instance = root / "instance"

    def filesystem(self) -> list[str]:
        shared = [self.home / ".local" / "share" / "uv",
                  self.home / ".cache" / "huggingface",
                  self.home / ".cache" / "torch"]
        writable = f"{self.instance} -{self.repo / 'data'}"
        return [
            "ProtectSystem=strict",
            "ProtectHome=tmpfs",
            f"BindReadOnlyPaths={self.repo} " + " ".join(f"-{path}" for path in shared),
            f"BindPaths={writable}",
            f"ReadWritePaths={writable}",
        ]

    def without_secrets(self) -> list[str]:
        return ["InaccessiblePaths=" + " ".join(f"-{self.instance / name}" for name in SECRET_FILES),
                f"ReadOnlyPaths=-{self.instance / 'apk'}"]

    def caches(self, unit: str) -> list[str]:
        """Libraries that insist on a cache directory get one of the unit's
        own, since the home directory's are read-only or gone."""
        return [f"CacheDirectory={unit}",
                f"Environment=NUMBA_CACHE_DIR=/var/cache/{unit}/numba",
                f"Environment=MPLCONFIGDIR=/var/cache/{unit}/matplotlib"]

    def worker(self, unit: str, network: bool) -> list[str]:
        lines = [*self.BASE, *self.filesystem(), *self.caches(unit), *self.without_secrets()]
        if not network:
            lines += ["PrivateNetwork=yes"]
        # Its own process table, so the server's process and environment are
        # not there to be read. The worker is then PID 1 of that table, and
        # the kernel only delivers PID 1 a signal it has a handler for:
        # Python has one for SIGINT and none for SIGTERM.
        lines += ["PrivatePIDs=yes", "KillSignal=SIGINT", "TimeoutStopSec=20"]
        return lines

    def server(self) -> list[str]:
        # The server answers the phones; when memory runs out it is the
        # workers that should go.
        return [*self.BASE, *self.filesystem(), *self.caches(SERVER_UNIT), "OOMScoreAdjust=-500"]


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
    #: False keeps a worker out of the full sandbox: it still cannot gain
    #: privileges, but it sees the home directory as the login user does.
    sandboxed: bool = True
    #: True lets a sandboxed unit reach the network.
    network: bool = False

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

    def confinement(self, root: Path) -> list[str]:
        sandbox = Sandbox(root)
        if not self.sandboxed:
            return list(sandbox.BASE)
        return sandbox.worker(self.unit, self.network)

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
            f"EnvironmentFile={root / 'instance' / WORKER_ENV}",
            *(f"Environment={key}={value}" for key, value in self.resolved_environment(root).items()),
            f"ExecStart={self.python(root, hosted=True)} {self.script}",
            *([f"MemoryMax={self.memory_max}"] if self.memory_max else []),
            "Restart=on-failure",
            f"RestartSec={self.restart_seconds}",
            *self.confinement(root),
            "",
            "[Install]",
            "WantedBy=multi-user.target",
        ]
        return "\n".join(lines) + "\n"


def server_unit_text(root: Path, user: str) -> str:
    """The field server's own unit. It was written by hand on the box when
    the server was first hosted; it is here so its sandbox is in the tree
    with the workers' and a deploy keeps it."""
    lines = [
        "[Unit]",
        "Description=CrowGPT field server (API + dashboard)",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        f"User={user}",
        f"WorkingDirectory={root}",
        f"EnvironmentFile={root / 'instance' / SERVER_ENV}",
        f"ExecStart={root / '.venv' / 'bin' / 'fieldserver'}",
        "Restart=on-failure",
        "RestartSec=3",
        *Sandbox(root).server(),
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

    def wanted(self):
        """(unit name, text) for the server and every worker this machine runs."""
        root = self.registry.root
        return [(SERVER_UNIT, server_unit_text(root, self.user)),
                *((worker.unit, worker.unit_text(root, self.user))
                  for worker in self.registry.runnable(hosted=True))]

    def changes(self):
        """(unit name, installed text or None, wanted text) for each unit
        that is not what the registry says."""
        pending = []
        for unit, wanted in self.wanted():
            path = self.unit_dir / f"{unit}.service"
            installed = path.read_text() if path.exists() else None
            if installed != wanted:
                pending.append((unit, installed, wanted))
        return pending

    def diff(self) -> str:
        parts = []
        for unit, installed, wanted in self.changes():
            name = f"{unit}.service"
            parts.append("".join(difflib.unified_diff(
                (installed or "").splitlines(keepends=True), wanted.splitlines(keepends=True),
                f"installed/{name}" if installed is not None else "(not installed)", f"registry/{name}")))
        return "\n".join(parts)

    def write_worker_environment(self) -> bool:
        """instance/worker.env, from the server's environment file with the
        secrets left out. Rewritten on every install, so a setting changed in
        service.env reaches the workers with the next deploy."""
        instance = self.registry.root / "instance"
        source = instance / SERVER_ENV
        if not source.exists():
            return False
        staged = instance / f".{WORKER_ENV}.new"
        staged.unlink(missing_ok=True)
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(worker_environment(source.read_text()))
        staged.replace(instance / WORKER_ENV)
        return True

    def install(self):
        self.write_worker_environment()
        pending = self.changes()
        for unit, _, wanted in pending:
            with tempfile.NamedTemporaryFile("w", suffix=".service") as staged:
                staged.write(wanted)
                staged.flush()
                target = self.unit_dir / f"{unit}.service"
                subprocess.run(["sudo", "install", "-m", "644", staged.name, str(target)], check=True)
            print(f"wrote {unit}.service")
        if pending:
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", "-q", *(unit for unit, _, _ in pending)], check=True)
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
