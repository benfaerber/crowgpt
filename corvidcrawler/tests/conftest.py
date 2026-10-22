import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Nothing a test does may touch the real corpus or its progress files."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PROGRESS_DIR", str(tmp_path / "progress"))
    monkeypatch.delenv("XENOCANTO_KEY", raising=False)
    return tmp_path / "data"


class FakeResponse:
    def __init__(self, payload=None, status_code=200, body=b"", headers=None, text=""):
        self.payload = payload
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload

    def iter_content(self, chunk_size=1):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ScriptedSession:
    """Answers each request from a script and remembers what it was asked."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0) if self.responses else FakeResponse(payload=[])
