"""The promo site's local preview — a built static bundle that describes the project.

crowgpt.org is where the promo lives (a Cloudflare Worker, `make -C promo
deploy`). This copy is for previewing a build on the machine that made it, so it
answers only to a loopback host; asked by any other name, field.crowgpt.org
included, it redirects to the same page on crowgpt.org rather than serving a
second, possibly stale, public copy. It reads no stores and takes no token;
every number on it is baked in at build time.
"""

from pathlib import Path

from flask import redirect, request, send_from_directory

from ..core.secrets import LOOPBACK_HOSTS

#: From the package, not from this file's parent — these routes live in api/,
#: and "next to me" would be a directory that does not exist.
PROMO_DIR = Path(__file__).resolve().parents[1] / "static" / "promo"

PUBLIC_SITE = "https://crowgpt.org"

NOT_BUILT = (
    "<h1>Promo site not built</h1>"
    "<p>Run <code>make -C promo build</code>, "
    "or <code>make field</code>, which builds it for you.</p>"
)


class Preview:
    """Whether this request may see the local copy, and where it goes if not."""

    @staticmethod
    def local() -> bool:
        host = request.host.rsplit(":", 1)[0] if not request.host.endswith("]") else request.host
        return host.strip("[]") in LOOPBACK_HOSTS

    @staticmethod
    def elsewhere(asset: str = ""):
        page = asset.removesuffix("index.html")
        return redirect(f"{PUBLIC_SITE}/{page}", code=308)


def register(app, d) -> None:
    """Attach this section's routes. Nothing from `d` is needed: it is a static site."""

    def index():
        """The promo page.

        A built bundle rather than a served file, so a checkout that has not run
        the build has nothing to show. Say so plainly, the way the dashboard
        does: a bare 404 reads as "the server is broken".
        """
        if not Preview.local():
            return Preview.elsewhere()
        if not (PROMO_DIR / "index.html").exists():
            return NOT_BUILT, 503
        return send_from_directory(PROMO_DIR, "index.html")

    # Both spellings, because a link to a site is written both ways and one of
    # them 404ing is a bug report. `/promo/` is the canonical one — relative
    # asset paths resolve against it.
    app.add_url_rule("/promo/", "promo_page", index, methods=["GET"])
    app.add_url_rule("/promo", "promo_page_bare", lambda: redirect("/promo/", code=308),
                     methods=["GET"])

    @app.get("/promo/<path:asset>")
    def promo_asset(asset):
        if not Preview.local():
            return Preview.elsewhere(asset)
        return send_from_directory(PROMO_DIR, asset)
