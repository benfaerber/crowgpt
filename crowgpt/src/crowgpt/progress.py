"""One file per run that always says what is happening and roughly when it ends.

Written for the case where the run is unattended: it starts before bed and the
only question in the morning — or at 2am on a phone — is whether it is still
going, how far it got, and whether anything has failed. So every stage writes
its own ETA from its own measured rate rather than from a guess made up front,
and a crash leaves the traceback in the file instead of only in a terminal
nobody is watching.

Each run owns exactly one record: `progress_dir()/<slug>.json`, overwritten
rather than appended because it answers "where is it now". There is no text
half any more — runs used to also write a PROGRESS.txt wherever they pleased,
which left stale copies all over the tree. A terminal that wants the old
`cat`-able view runs this module directly:

    python3 crowgpt/src/crowgpt/progress.py

which renders every run in the progress directory, active first.
"""

import json
import os
import re
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent

_SLUG = re.compile(r"[^a-z0-9]+")


def progress_dir() -> Path:
    """Where every run's JSON lands, one file per run.

    A single shared PROGRESS.json was the design until two runs wrote it at
    once — a scan and a finetune overwrote each other's state and the
    dashboard flickered between them. Now each run owns `<slug>.json` in this
    directory and the server lists the directory, so runs coexist. Rides the
    corpus location (gitignored, DATA_DIR-overridable) because a run in any
    venv or repo can reach it there without knowing this repo's layout.
    """
    override = os.environ.get("PROGRESS_DIR")
    if override:
        return Path(override).expanduser()
    data = os.environ.get("DATA_DIR")
    base = Path(data).expanduser() if data else REPO / "data"
    return base / "progress"


def slugify(title) -> str:
    return _SLUG.sub("-", str(title).lower()).strip("-") or "run"


def _clock(seconds):
    if seconds is None or seconds != seconds or seconds < 0:
        return "?"
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    return f"{seconds / 3600:.1f}h"


class Run:
    """The whole run: a list of stages, one of them current."""

    def __init__(self, title, stages):
        self.title = title
        self.slug = slugify(title)
        self.stages = list(stages)
        self.started = time.monotonic()
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.state = {name: {"status": "waiting", "note": ""} for name in self.stages}
        self.durations = {}
        self.current = None
        self.notes = []
        self.write()

    def stage(self, name):
        return Stage(self, name)

    def note(self, line):
        """A finding worth seeing without opening anything else."""
        self.notes.append(line)
        self.write()

    def failed(self, name, exc):
        self.state[name]["status"] = "FAILED"
        self.state[name]["note"] = f"{type(exc).__name__}: {exc}"
        self.notes.append("TRACEBACK\n" + traceback.format_exc())
        self.write()

    def _eta(self):
        """Whole-run ETA, or None when it would be a lie.

        Averaging elapsed time over completed stages is only meaningful if those
        stages did work. A resumed run finishes three of them in zero seconds by
        reusing what is on disk, which drags the average to nothing and projects
        the whole run finishing in seven minutes. Better to show no estimate
        than a wrong one — the per-stage ETA is measured from its own rate and
        is the honest number anyway.
        """
        worked = [n for n in self.stages
                  if self.state[n]["status"] == "done" and self.durations.get(n, 0) > 5]
        if len(worked) < 2:
            return None
        spent = sum(self.durations[n] for n in worked)
        remaining = [n for n in self.stages if self.state[n]["status"] in ("waiting", "running")]
        return spent / len(worked) * len(remaining)

    def write(self):
        """The run's whole state, as JSON in the shared progress dir.

        Written to `progress_dir()/<slug>.json` rather than posted anywhere: a
        run is a separate process in a separate venv, often under systemd, and
        it should not need the field server to be up in order to make
        progress. The server lists the directory when someone opens the page,
        which is what lets several runs report at once. This file is the ONE
        canonical record — no beside-copies, which is how the flicker of
        2026-08-09 happened.
        """
        elapsed = time.monotonic() - self.started
        remaining = self._eta()
        payload = {
            "title": self.title,
            "slug": self.slug,
            "started_at": self.started_at,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed),
            "eta_seconds": None if remaining is None else round(remaining),
            "current": self.current,
            "finished": all(self.state[n]["status"] in ("done", "FAILED") for n in self.stages),
            "failed": any(self.state[n]["status"] == "FAILED" for n in self.stages),
            "stages": [
                {
                    "name": name,
                    "status": self.state[name]["status"],
                    "note": self.state[name]["note"],
                    "done": self.state[name].get("done"),
                    "total": self.state[name].get("total"),
                    "eta_seconds": self.state[name].get("eta_seconds"),
                    "extra": self.state[name].get("extra"),
                    "took_seconds": round(self.durations[name]) if name in self.durations else None,
                }
                for name in self.stages
            ],
            "notes": self.notes,
        }
        body = json.dumps(payload, indent=2) + "\n"
        # Never let a status write kill the run it reports on.
        try:
            shared = progress_dir()
            shared.mkdir(parents=True, exist_ok=True)
            (shared / f"{self.slug}.json").write_text(body)
        except OSError:
            pass


class Stage:
    """One stage, reporting its own rate and ETA as it goes."""

    def __init__(self, run, name):
        self.run = run
        self.name = name
        self.started = None
        self.total = None
        self.first_done = None

    def __enter__(self):
        self.started = time.monotonic()
        self.run.current = self.name
        self.run.state[self.name].update(status="running", note="starting")
        self.run.write()
        return self

    def __exit__(self, kind, value, tb):
        self.run.durations[self.name] = time.monotonic() - self.started
        took = _clock(time.monotonic() - self.started)
        if kind is None:
            slot = self.run.state[self.name]
            slot["status"] = "done"
            slot["note"] = f"{slot['note'].split('  |  ')[0]}  |  took {took}".lstrip(" |")
            if slot["note"].startswith("starting"):
                slot["note"] = f"took {took}"
            self.run.current = None
            self.run.write()
            return False
        self.run.failed(self.name, value)
        return False

    def update(self, done, total=None, extra=""):
        """Progress within the stage, with an ETA from the rate so far.

        The rate is measured from the first `done` this stage SAW, not from
        zero — a resumed run's counter starts hundreds of thousands of steps
        in, and dividing that by seconds of wall clock read as "~11s left" on
        a job with two days to go."""
        self.total = total or self.total
        if self.first_done is None:
            self.first_done = done
        elapsed = time.monotonic() - self.started
        note = f"{done}" + (f"/{self.total}" if self.total else "")
        remaining = None
        made = done - self.first_done
        if self.total and made > 0:
            remaining = elapsed / made * (self.total - done)
            note += f"  ~{_clock(remaining)} left"
        if extra:
            note += f"  |  {extra}"
        slot = self.run.state[self.name]
        slot["note"] = note
        # Kept as numbers as well as prose. The text file is for `cat`; a
        # progress bar needs a fraction, and re-parsing "11000/40000  ~1.8h left"
        # out of a formatted string is the kind of thing that breaks silently
        # the first time the format changes.
        slot["done"] = done
        slot["total"] = self.total
        slot["eta_seconds"] = None if remaining is None else round(remaining)
        slot["extra"] = extra
        self.run.write()

    def say(self, text):
        self.run.state[self.name]["note"] = text
        self.run.write()


def render(payload) -> str:
    """A run's JSON as the screenful the text files used to be.

    Display lives here, at read time, so nothing on disk is a format anyone
    has to parse — the JSON stays numbers and the prose is rebuilt on demand.
    """
    title = payload.get("title", "?")
    lines = [title, "=" * len(title)]
    head = f"updated {payload.get('updated_at', '?')[-14:-6]}   " \
           f"running for {_clock(payload.get('elapsed_seconds'))}"
    lines.append(head)
    remaining = payload.get("eta_seconds")
    if remaining and payload.get("current"):
        done_at = datetime.now() + timedelta(seconds=remaining)
        lines.append(f"whole run: roughly {_clock(remaining)} left, "
                     f"around {done_at:%H:%M} (crude — trust the stage line)")
    lines.append("")
    for stage in payload.get("stages", []):
        mark = {"waiting": "[ ]", "running": "[>]", "done": "[x]",
                "FAILED": "[!]"}.get(stage.get("status"), "[?]")
        lines.append(f"  {mark} {stage.get('name', '?'):<28} {stage.get('note', '')}")
    notes = payload.get("notes")
    if notes:
        lines += ["", "NOTES", ""]
        lines += [f"  {line}" for note in notes for line in note.splitlines()]
    return "\n".join(lines) + "\n"


def main() -> int:
    """Render the active runs — or, with none active, the freshest record.

    The audience is `watch -n 2`, so this is a status screen, not an archive:
    finished runs leave their files behind and the panel wants the story now.
    """
    folder = progress_dir()
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime,
                   reverse=True) if folder.is_dir() else []
    runs = []
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        age = time.time() - path.stat().st_mtime
        active = age < 600 and not payload.get("finished")
        runs.append((path, payload, age, active))
    if not runs:
        print(f"no runs reporting in {folder}")
        return 0
    show = [r for r in runs if r[3]] or runs[:1]
    for path, payload, age, active in show:
        print(render(payload), end="")
        state = "ACTIVE" if active else \
            "FAILED" if payload.get("failed") else \
            "finished" if payload.get("finished") else "stale — no writes"
        print(f"  ({state}, last write {_clock(age)} ago — {path.name})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
