"""The promo site — a built static bundle, open to anyone, that describes the project.

Served by the field server for the same reason the dashboard is: one process on
one port, and the page is a URL rather than a thing to deploy. It reads no
stores and takes no token; every number on it is baked in at build time, so a
visitor never touches the corpus.
"""

from pathlib import Path

from flask import redirect, send_from_directory

#: From the package, not from this file's parent — these routes live in api/,
#: and "next to me" would be a directory that does not exist.
PROMO_DIR = Path(__file__).resolve().parents[1] / "static" / "promo"

NOT_BUILT = (
    "<h1>Promo site not built</h1>"
    "<p>Run <code>make -C promo build</code>, "
    "or <code>make field</code>, which builds it for you.</p>"
)


def register(app, d) -> None:
    """Attach this section's routes. Nothing from `d` is needed: it is a static site."""

    def index():
        """The promo page.

        A built bundle rather than a served file, so a checkout that has not run
        the build has nothing to show. Say so plainly, the way the dashboard
        does: a bare 404 reads as "the server is broken".
        """
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
        return send_from_directory(PROMO_DIR, asset)
