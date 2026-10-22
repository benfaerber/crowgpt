"""Shared fixtures.

Every test gets its own database under pytest's `tmp_path`, so nothing leaks
between them and any test can be run alone. That matters more than it sounds:
these were previously one long script per file, where an early failure silently
changed what every later assertion was actually testing.
"""

import shutil
from dataclasses import dataclass

import pytest

from fieldserver.core import schema
from fieldserver.app import DEFAULT_ENROLL_TOKEN, DEFAULT_OPERATOR_TOKEN, create_app


@pytest.fixture(scope="session")
def _migrated_template(tmp_path_factory):
    """One migrated database per test session, copied per test.

    Running Alembic in every test took the suite from ten seconds to eighty —
    280 tests each rebuilding nineteen tables. The migrations are deterministic,
    so building once and copying the file gives every test the same schema for
    the cost of a file copy.
    """
    template = tmp_path_factory.mktemp("template") / "template.db"
    schema.upgrade(template)
    return template


@pytest.fixture
def db_path(tmp_path, _migrated_template):
    path = tmp_path / "field.db"
    shutil.copy(_migrated_template, path)
    return path


@pytest.fixture
def app(db_path):
    return create_app(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@dataclass
class Enrollment:
    """One enrolled device, and everything the API handed back with it."""

    device: dict
    contributor: dict
    token: str
    claim_code: str | None

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def enroll(client):
    """Enroll a device. Pass `claim_code=` to join an existing contributor."""

    def _enroll(**body) -> Enrollment:
        response = client.post(
            "/api/devices/register",
            json={"enroll_token": DEFAULT_ENROLL_TOKEN, **body},
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        payload = response.get_json()
        return Enrollment(
            device=payload["device"],
            contributor=payload["contributor"],
            token=payload["device_token"],
            claim_code=payload.get("claim_code"),
        )

    return _enroll


@pytest.fixture
def recordist(enroll) -> Enrollment:
    return enroll(contributor_name="Ben", label="Pixel 10", platform="android")


@pytest.fixture
def stranger(enroll) -> Enrollment:
    return enroll(contributor_name="Someone else")


@pytest.fixture
def operator(enroll) -> Enrollment:
    return enroll(contributor_name="Op", is_operator=True,
                  operator_token=DEFAULT_OPERATOR_TOKEN)
