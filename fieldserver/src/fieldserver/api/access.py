"""Requesting the app, and handing it over.

Two halves. The public one, under /preview, is what a stranger sees: a form
that takes an email, and later a page their invite link opens, carrying the
enrollment token and the APK. The operator one, under /api/fleet, is the
queue Ben works from the dashboard: approve, which mints the invite and
emails it when a mailer is configured, or decline.

What an invite hands over is the fleet's *shared* enrollment token, the same
one every phone has typed since the beginning. The invite does not make the
token any less shared; it only decides who is told it. Per-contributor
tokens are the next step and a different change.

"Latest" APK is the newest .apk in instance/apk/, which `make apk-publish`
fills, so publishing a build is a copy rather than a config change.
"""

import html
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import abort, jsonify, request, send_file

from ..core.mail import Mailer
from ..core.secrets import ENROLL_SECRET
from ..core.throttle import Throttle
from ..stores.contributors import FLEET_ROLES

#: Submissions, not failures: five requests an hour from one address is a
#: person retrying, more is a script.
SUBMISSIONS_PER_HOUR = 5
APK_TYPE = "application/vnd.android.package-archive"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CrowGPT field app</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #17130f; color: #f7f0e6;
         font: 17px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 28rem; padding: 2rem 1.25rem; }
  h1 { font-size: 1.5rem; margin: 0 0 .5rem; }
  h1 span { color: #e08a3c; }
  p, li { color: #c8bcab; }
  p { margin: .5rem 0; }
  .build, .small { color: #97897a; font-size: .9rem; }
  .error { color: #f0a090; }
  form { margin-top: 1.25rem; display: flex; flex-direction: column; gap: .75rem; }
  label { font-size: .85rem; color: #97897a; }
  input, textarea, button { font: inherit; padding: .7rem .9rem; border-radius: 12px; width: 100%%; box-sizing: border-box; }
  input, textarea { border: 1px solid #524335; background: #201a15; color: #f7f0e6; }
  button { border: 0; background: #e08a3c; color: #17130f; font-weight: 600; cursor: pointer; }
  code { display: block; padding: .7rem .9rem; border-radius: 12px; background: #201a15;
         border: 1px solid #524335; color: #f7f0e6; font-size: 1rem; word-break: break-all; user-select: all; }
  ol { padding-left: 1.25rem; }
</style>
</head>
<body>
<main>
  <h1><span>Crow</span>GPT field app</h1>
  %(body)s
</main>
</body>
</html>
"""

REQUEST_FORM = """
  <p>The field app is in a closed preview. Leave an email and Ben will send
  you an invite with the app and what it needs to join.</p>
  %(error)s
  <form method="post" action="/preview/request">
    <label>Email<input type="email" name="email" value="%(email)s" required autocomplete="email"></label>
    <label>Name<input type="text" name="name" value="%(name)s" autocomplete="name"></label>
    <label>Where would you record, and what crows are there?
      <textarea name="note" rows="3">%(note)s</textarea></label>
    <button type="submit">Request access</button>
  </form>
"""

THANKS = """
  <p>Thanks. Your request is in the queue; if it is approved, the invite goes
  to <strong>%(email)s</strong>.</p>
  <p class="small">Already asked from this address? That earlier request is the
  one that counts, and it is still open.</p>
"""

INVITE = """
  <p>You are in. Two things get this phone recording crows into the project:
  the app, and the token it asks for on first launch.</p>
  <label>Enrollment token</label>
  <code>%(token)s</code>
  <p class="small">Type or paste it into the app when it asks. It joins the
  phone to the fleet once and is not shown in the app again.</p>
  <form method="post" action="/preview/%(invite)s/apk">
    <button type="submit">Download the app (Android APK)</button>
  </form>
  <p class="build">%(build)s</p>
  <ol>
    <li>Open the downloaded file; Android asks to allow installs from this browser.</li>
    <li>On first launch, enter your name and the token above.</li>
    <li>Record. Captures sync to the project when you tap Sync.</li>
  </ol>
"""

NOT_FOUND = """
  <p>This invite link is not valid. If Ben sent it to you, ask for a fresh one.</p>
"""


def latest_apk(apk_dir: Path):
    builds = sorted(apk_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    return builds[-1] if builds else None


def describe(apk) -> str:
    if apk is None:
        return "No build has been published yet; check back later."
    stamp = datetime.fromtimestamp(apk.stat().st_mtime, tz=timezone.utc)
    size_mb = apk.stat().st_size / (1024 * 1024)
    return f"Build {apk.name}, {size_mb:.0f} MB, published {stamp:%Y-%m-%d}."


def page(body: str, status: int = 200):
    return PAGE % {"body": body}, status


def invite_text(invite_url: str) -> str:
    return (
        "You asked to try the CrowGPT field app, and you are in.\n\n"
        f"Open this link on your Android phone: {invite_url}\n\n"
        "It has the app and the enrollment token the app asks for on first "
        "launch. The link is yours; please do not pass it on.\n\n"
        "Ben\nhttps://crowgpt.org\n"
    )


def register(app, d) -> None:
    access = d.access
    current_actor = d.current_actor
    apk_dir = d.instance_dir / "apk"
    submissions = Throttle(allowed=SUBMISSIONS_PER_HOUR, per_seconds=3600)
    mailer = Mailer.from_env()

    def current_operator() -> dict:
        _, contributor = current_actor()
        if contributor["role"] not in FLEET_ROLES:
            abort(403, "operator role required")
        return contributor

    def invite_url(token: str) -> str:
        return request.url_root.rstrip("/") + f"/preview/{token}"

    def form(values=None, error=""):
        values = values or {}
        return REQUEST_FORM % {
            "email": html.escape(values.get("email", "")),
            "name": html.escape(values.get("name", "")),
            "note": html.escape(values.get("note", "")),
            "error": f'<p class="error">{error}</p>' if error else "",
        }

    # --- public ---

    @app.get("/preview")
    def preview_request_form():
        return page(form())

    @app.post("/preview/request")
    def preview_request():
        caller = request.remote_addr or "unknown"
        values = {k: (request.form.get(k) or "").strip() for k in ("email", "name", "note")}
        if submissions.blocked(caller):
            return page(form(values, "Too many requests from here; try again in an hour."), 429)
        email = values["email"].lower()
        if not EMAIL.match(email):
            return page(form(values, "That does not look like an email address."), 400)
        submissions.record_failure(caller)
        access.request(email, name=values["name"][:120] or None,
                       note=values["note"][:2000] or None, requester_ip=caller)
        return page(THANKS % {"email": html.escape(email)})

    @app.get("/preview/<token>")
    def preview_invite(token):
        row = access.by_token(token)
        if not row or row["status"] != "approved":
            return page(NOT_FOUND, 404)
        return page(INVITE % {"token": html.escape(ENROLL_SECRET), "invite": html.escape(token),
                              "build": describe(latest_apk(apk_dir))})

    @app.post("/preview/<token>/apk")
    def preview_download(token):
        row = access.by_token(token)
        if not row or row["status"] != "approved":
            return page(NOT_FOUND, 404)
        apk = latest_apk(apk_dir)
        if apk is None:
            return page(INVITE % {"token": html.escape(ENROLL_SECRET), "invite": html.escape(token),
                                  "build": describe(None)}, 404)
        access.record_download(token)
        return send_file(apk, mimetype=APK_TYPE, as_attachment=True,
                         download_name=apk.name, max_age=0)

    # --- operator ---

    def with_link(row: dict) -> dict:
        out = dict(row)
        out["invite_url"] = invite_url(row["invite_token"]) if row.get("invite_token") else None
        return out

    @app.get("/api/fleet/access-requests")
    def list_access_requests():
        current_operator()
        return jsonify({
            "requests": [with_link(r) for r in access.list_all()],
            "mail_configured": mailer is not None,
            "build": describe(latest_apk(apk_dir)),
        })

    @app.post("/api/fleet/access-requests/<int:request_id>/approve")
    def approve_access_request(request_id):
        """Approve, and email the invite if there is a mailer; either way the
        link comes back for Ben to pass on himself. Approving an approved
        request re-sends the same link rather than minting a second."""
        current_operator()
        row = access.approve(request_id)
        if not row:
            abort(404, "no such request")
        emailed = False
        if mailer is not None:
            try:
                mailer.send(row["email"], "Your CrowGPT field app invite",
                            invite_text(invite_url(row["invite_token"])))
                row = access.mark_emailed(request_id)
                emailed = True
            except Exception as error:  # noqa: BLE001 — the reason goes on the row
                row = access.mark_emailed(request_id, error=str(error)[:300])
        return jsonify({"request": with_link(row), "emailed": emailed})

    @app.post("/api/fleet/access-requests/<int:request_id>/decline")
    def decline_access_request(request_id):
        current_operator()
        row = access.decline(request_id)
        if not row:
            abort(404, "no such request")
        return jsonify({"request": with_link(row)})
