"""Copy only demo configuration into systemd's existing env file, never print it.

Run on the VPS after editing instance/secrets.env with nvim. No shell evaluation.
"""
import os
import shlex
from pathlib import Path

instance = Path(__file__).resolve().parents[1] / "instance"
names = {"FIELD_TURNSTILE_SITE_KEY", "FIELD_TURNSTILE_SECRET", "FIELD_DEMO_TURNSTILE_REQUIRED"}
values = {}
for line in (instance / "secrets.env").read_text().splitlines():
    words = shlex.split(line, comments=True)
    if words[:1] == ["export"]:
        words = words[1:]
    if len(words) == 1 and "=" in words[0]:
        key, value = words[0].split("=", 1)
        if key in names:
            if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." for c in value):
                raise SystemExit(f"Invalid or empty value for {key}; edit secrets.env")
            values[key] = value
if values.keys() != names or values["FIELD_DEMO_TURNSTILE_REQUIRED"] not in {"0", "1"}:
    raise SystemExit("Set both Turnstile keys and FIELD_DEMO_TURNSTILE_REQUIRED=0 or 1")
target = instance / "service.env"
lines = [line for line in target.read_text().splitlines() if line.split("=", 1)[0] not in names]
temporary = instance / ".service.env.demo-update"
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as output:
    output.write("\n".join(lines + [f"{key}={values[key]}" for key in sorted(names)]) + "\n")
temporary.replace(target)
print("Demo configuration synchronized; restart crowgpt-field to apply.")
