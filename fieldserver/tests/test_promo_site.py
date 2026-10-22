"""The promo site is served, and serving it gives nothing away.

It is the one page on this server written for strangers, so the thing worth
pinning is not that it renders — it is that it stays a static bundle: no token,
no store, and no way to walk out of its directory into the corpus sitting two
folders up.
"""

from fieldserver.api.promo import PROMO_DIR


class TestItIsServed:

    def test_the_page_is_open_to_anyone(self, client):
        # No Authorization header anywhere in this file, on purpose.
        response = client.get("/promo/")
        assert response.status_code in (200, 503)

    def test_the_bare_path_redirects_to_the_canonical_one(self, client):
        # A link gets written both ways and one of them 404ing is a bug report.
        # 308 rather than 302 so the method is preserved and caches keep it.
        response = client.get("/promo")
        assert response.status_code == 308
        assert response.headers["Location"].endswith("/promo/")

    def test_an_unbuilt_checkout_says_so_instead_of_404ing(self, client, monkeypatch):
        monkeypatch.setattr("fieldserver.api.promo.PROMO_DIR", PROMO_DIR / "nowhere")
        response = client.get("/promo/")
        assert response.status_code == 503
        assert "make -C promo build" in response.get_data(as_text=True)


class TestItGivesNothingAway:

    def test_it_will_not_serve_its_way_out_of_its_own_directory(self, client):
        # media/ and field.db live above static/. The encoded forms are the ones
        # that matter: `..` in a plain path is normalised away before routing,
        # while `%2e%2e` arrives at the view still meaning "up one". Both are
        # pointed at the dashboard bundle, which *does* exist — so a 404 here is
        # a refusal rather than a miss.
        for escape in ("%2e%2e/app/index.html", "..%2fapp%2findex.html",
                       "../../../field.db", "etc/passwd"):
            response = client.get(f"/promo/{escape}")
            assert response.status_code in (400, 403, 404), escape

    def test_a_missing_asset_is_a_404_not_the_page(self, client):
        # An SPA fallback here would answer 200 to every path under /promo,
        # which turns a broken asset link into a silently blank page.
        assert client.get("/promo/assets/does-not-exist.js").status_code == 404
