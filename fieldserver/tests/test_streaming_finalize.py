import hashlib
from pathlib import Path


def test_large_chunked_video_finalizes_without_reading_it_all(client, recordist, monkeypatch):
    capture = client.post("/api/captures", json={"client_uuid": "large-video"},
                          headers=recordist.headers).json
    media = client.post(f"/api/captures/{capture['id']}/media",
                        json={"client_uuid": "large-video-media", "kind": "video", "format": "mp4"},
                        headers=recordist.headers).json
    chunk = b"video-bytes" * (256 * 1024 // 11)
    total = len(chunk) * 80  # More than the server's per-request body limit.
    expected = hashlib.sha256()
    def whole_file_is_forbidden(*args, **kwargs):
        raise AssertionError("finalize must stream, not allocate the entire capture")
    monkeypatch.setattr(Path, "read_bytes", whole_file_is_forbidden)
    for offset in range(0, total, len(chunk)):
        result = client.put(f"/api/media/{media['id']}", data=chunk,
                            headers={**recordist.headers,
                                     "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{total}"})
        assert result.status_code == 200
        expected.update(chunk)
    assert result.json["upload_state"] == "complete"
    assert result.json["bytes"] == total
    assert result.json["sha256"] == expected.hexdigest()
