"""A preview build of the app, behind a word somebody can be told out loud.

A tester gets a URL and a password, types the password, and the phone
downloads the APK. That is the whole feature: no account, no enrollment,
nothing the password unlocks except the file. The enrollment token is still
what joins the fleet, and the app asks for it on first launch as before.

"Latest" is the newest .apk in instance/apk/, which `make apk-publish` fills.
Publishing a build is a copy, not a restart or a config change, so the page
cannot be stale against the server's idea of what the current build is: there
is no such idea, only the directory.
"""

import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import abort, request, send_file

from ..core.secrets import PREVIEW_SECRET
from ..core.throttle import Throttle

#: Fewer than the enrollment routes allow: this password is chosen to be said
#: aloud, so it is shorter, so a guesser gets fewer tries.
WRONG_GUESSES = 5
GUESS_WINDOW_SEC = 60
APK_TYPE = "application/vnd.android.package-archive"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CrowGPT preview build</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #17130f; color: #f7f0e6;
         font: 17px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 26rem; padding: 2rem 1.25rem; }
  h1 { font-size: 1.5rem; margin: 0 0 .5rem; }
  h1 span { color: #e08a3c; }
  p { color: #c8bcab; margin: .5rem 0; }
  .build { color: #97897a; font-size: .9rem; }
  .error { color: #f0a090; }
  form { margin-top: 1.25rem; display: flex; flex-direction: column; gap: .75rem; }
  input, button { font: inherit; padding: .7rem .9rem; border-radius: 12px; }
  input { border: 1px solid #524335; background: #201a15; color: #f7f0e6; }
  button { border: 0; background: #e08a3c; color: #17130f; font-weight: 600; cursor: pointer; }
  ol { color: #c8bcab; padding-left: 1.25rem; }
</style>
</head>
<body>
<main>
  <h1><span>Crow</span>GPT preview build</h1>
  %(body)s
</main>
</body>
</html>
"""

FORM = """
  <p>A test build of the field app, for Android. Enter the preview password to
  download it.</p>
  <p class="build">%(build)s</p>
  %(error)s
  <form method="post" action="/preview">
    <input type="password" name="password" placeholder="Preview password"
           autocomplete="off" autofocus required>
    <button type="submit">Download the APK</button>
  </form>
  <ol>
    <li>Open the downloaded file; Android asks to allow installs from this browser.</li>
    <li>On first launch, enter the server and the enrollment token from Ben.</li>
  </ol>
"""


def latest_apk(apk_dir: Path):
    builds = sorted(apk_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    return builds[-1] if builds else None


def describe(apk) -> str:
    if apk is None:
        return "No build has been published yet."
    stamp = datetime.fromtimestamp(apk.stat().st_mtime, tz=timezone.utc)
    size_mb = apk.stat().st_size / (1024 * 1024)
    return f"Latest: {apk.name}, {size_mb:.0f} MB, published {stamp:%Y-%m-%d %H:%M} UTC."


def page(apk, error: str = "", status: int = 200):
    error_html = f'<p class="error">{error}</p>' if error else ""
    body = FORM % {"build": describe(apk), "error": error_html}
    return PAGE % {"body": body}, status


def register(app, d) -> None:
    apk_dir = d.instance_dir / "apk"
    guesses = Throttle(allowed=WRONG_GUESSES, per_seconds=GUESS_WINDOW_SEC)

    def enabled() -> bool:
        return bool(PREVIEW_SECRET)

    @app.get("/preview")
    def preview_form():
        if not enabled():
            return PAGE % {"body": "<p>Preview builds are not enabled on this server.</p>"}, 503
        return page(latest_apk(apk_dir))

    @app.post("/preview")
    def preview_download():
        if not enabled():
            abort(503, "preview builds are not enabled on this server")
        caller = request.remote_addr or "unknown"
        if guesses.blocked(caller):
            return page(latest_apk(apk_dir),
                        "Too many wrong passwords. Wait a minute and try again.", 429)
        offered = request.form.get("password") or ""
        if not secrets.compare_digest(offered, PREVIEW_SECRET):
            guesses.record_failure(caller)
            return page(latest_apk(apk_dir), "Wrong password.", 403)
        apk = latest_apk(apk_dir)
        if apk is None:
            return page(None, "There is no build to download yet.", 404)
        return send_file(apk, mimetype=APK_TYPE, as_attachment=True,
                         download_name=apk.name, max_age=0)
