"""The gallery is filesystem-backed, so the tests are mostly about absent files.

A gallery is published by a separate process in a separate venv. Every state that
process can leave behind — nothing published, a half-written publish, a manifest
without its clips — has to be a normal answer rather than a 500.
"""

import json

import pytest

from fieldserver.api import gallery


@pytest.fixture
def galleries(tmp_path, monkeypatch):
    root = tmp_path / "gallery"
    root.mkdir()
    monkeypatch.setattr(gallery, "GALLERY_ROOT", root)
    return root


def publish(root, name, clips=("a.wav", "b.wav"), **extra):
    folder = root / name
    (folder / "clips").mkdir(parents=True)
    for clip in clips:
        (folder / "clips" / clip).write_bytes(b"RIFF....WAVEfmt ")
    (folder / "meta.json").write_text(json.dumps({
        "name": name, "title": extra.pop("title", name),
        "model": "model-mono-v2",
        "clips": [{"file": c, "rank": i + 1, "birdnet": 0.9 - i * 0.1,
                   "seconds": 2.5, "churn": 0.86, "churn_gap": 0.01}
                  for i, c in enumerate(clips)],
        **extra}))
    return folder


class TestAuth:
    def test_the_data_needs_an_operator(self, client, recordist, galleries):
        publish(galleries, "one")
        assert client.get("/api/gallery").status_code == 401
        assert client.get(
            "/api/gallery", headers=recordist.headers).status_code == 403

    def test_the_page_shell_needs_nothing(self, client):
        # Every byte of data behind it is gated; gating the shell too would only
        # mean a blank page and a prompt that cannot be answered.
        assert client.get("/gallery/").status_code in (200, 503)

    def test_the_bare_path_redirects(self, client):
        response = client.get("/gallery")
        assert response.status_code == 308
        assert response.headers["Location"].endswith("/gallery/")


class TestListing:
    def test_nothing_published_is_an_empty_list(self, client, operator, galleries):
        assert client.get("/api/gallery",
                          headers=operator.headers).get_json() == []

    def test_a_missing_root_is_also_an_empty_list(self, client, operator, tmp_path,
                                                 monkeypatch):
        monkeypatch.setattr(gallery, "GALLERY_ROOT", tmp_path / "never-made")
        assert client.get("/api/gallery",
                          headers=operator.headers).get_json() == []

    def test_the_listing_omits_the_clip_list(self, client, operator, galleries):
        publish(galleries, "one", clips=("a.wav", "b.wav", "c.wav"))
        row = client.get("/api/gallery", headers=operator.headers).get_json()[0]
        assert row["clip_count"] == 3
        assert "clips" not in row

    def test_a_half_written_publish_is_skipped_not_fatal(self, client, operator,
                                                        galleries):
        publish(galleries, "good")
        (galleries / "aborted" / "clips").mkdir(parents=True)   # clips, no manifest
        (galleries / "broken").mkdir()
        (galleries / "broken" / "meta.json").write_text('{"name": ')
        names = [r["name"] for r in client.get(
            "/api/gallery", headers=operator.headers).get_json()]
        assert names == ["good"]


class TestOneGallery:
    def test_it_carries_its_clips(self, client, operator, galleries):
        publish(galleries, "one")
        body = client.get("/api/gallery/one", headers=operator.headers).get_json()
        assert [c["file"] for c in body["clips"]] == ["a.wav", "b.wav"]
        assert body["model"] == "model-mono-v2"

    def test_an_unknown_gallery_is_a_404(self, client, operator, galleries):
        publish(galleries, "one")
        assert client.get("/api/gallery/nope",
                          headers=operator.headers).status_code == 404


class TestClips:
    def test_a_clip_is_served_as_audio(self, client, operator, galleries):
        publish(galleries, "one")
        response = client.get("/api/gallery/one/clips/a.wav",
                              headers=operator.headers)
        assert response.status_code == 200
        assert response.mimetype == "audio/wav"

    def test_traversal_is_refused(self, client, operator, galleries):
        publish(galleries, "one")
        response = client.get("/api/gallery/one/clips/../meta.json",
                              headers=operator.headers)
        assert response.status_code in (403, 404)

    def test_a_clip_of_an_unknown_gallery_is_a_404(self, client, operator, galleries):
        publish(galleries, "one")
        assert client.get("/api/gallery/nope/clips/a.wav",
                          headers=operator.headers).status_code == 404

    def test_a_manifest_without_its_clips_directory_is_a_404(self, client, operator,
                                                            galleries):
        # The other half of an interrupted publish: manifest written, clips gone.
        folder = publish(galleries, "one")
        for clip in (folder / "clips").iterdir():
            clip.unlink()
        (folder / "clips").rmdir()
        assert client.get("/api/gallery/one/clips/a.wav",
                          headers=operator.headers).status_code == 404
