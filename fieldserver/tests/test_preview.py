"""The preview page hands out the app to whoever knows the word, and nothing else.

The password guards a file, not the corpus, so the things worth pinning are
the ones that would quietly widen that: an unset password must not mean "no
password", a wrong one must count against the guesser, and the right one must
hand over exactly the newest build.
"""

import time

import pytest

from fieldserver.api import preview

PASSWORD = "field-notes-42"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(preview, "PREVIEW_SECRET", PASSWORD)


@pytest.fixture
def builds(db_path):
    apk_dir = db_path.parent / "apk"
    apk_dir.mkdir()
    old = apk_dir / "crowgpt-field-old.apk"
    old.write_bytes(b"old build")
    new = apk_dir / "crowgpt-field-new.apk"
    new.write_bytes(b"new build")
    # mtime decides "latest", not the name: a republished older name still wins
    # if it is the newer file.
    stale = time.time() - 3600
    import os
    os.utime(old, (stale, stale))
    return new


class TestOff:

    def test_unset_means_off_not_open(self, client, monkeypatch):
        monkeypatch.setattr(preview, "PREVIEW_SECRET", "")
        assert client.get("/preview").status_code == 503
        response = client.post("/preview", data={"password": ""})
        assert response.status_code == 503


class TestOn:

    def test_the_form_says_what_is_published(self, client, enabled, builds):
        body = client.get("/preview").get_data(as_text=True)
        assert "crowgpt-field-new.apk" in body
        assert "password" in body

    def test_the_form_says_when_nothing_is(self, client, enabled):
        body = client.get("/preview").get_data(as_text=True)
        assert "No build has been published yet" in body

    def test_the_right_word_downloads_the_newest_build(self, client, enabled, builds):
        response = client.post("/preview", data={"password": PASSWORD})
        assert response.status_code == 200
        assert response.mimetype == preview.APK_TYPE
        assert "crowgpt-field-new.apk" in response.headers["Content-Disposition"]
        assert response.data == b"new build"

    def test_the_wrong_word_does_not(self, client, enabled, builds):
        response = client.post("/preview", data={"password": "crow"})
        assert response.status_code == 403
        assert b"new build" not in response.data

    def test_the_right_word_with_no_build_is_a_404_not_a_crash(self, client, enabled):
        assert client.post("/preview", data={"password": PASSWORD}).status_code == 404

    def test_guessing_is_cut_off(self, client, enabled, builds):
        for _ in range(preview.WRONG_GUESSES):
            client.post("/preview", data={"password": "nope"})
        blocked = client.post("/preview", data={"password": PASSWORD})
        # The right password after too many wrong ones still fails: the block
        # is checked before the comparison, so a blocked caller learns nothing.
        assert blocked.status_code == 429
        assert b"new build" not in blocked.data
