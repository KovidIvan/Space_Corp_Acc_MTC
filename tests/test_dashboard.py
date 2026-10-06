"""Integration tests for the authenticated local dashboard."""

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import db as database
from app.core.config import Settings
from app.core.demo_data import seed_demo_calls
from app.main import create_app
from app.models import AuditEvent, CallRecord


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    settings = Settings(
        _env_file=None,
        owner_name="dashboard-owner",
        owner_company="Synthetic Company",
        owner_password="test-only-password",
        session_secret="test-session-secret-with-enough-entropy",
        data_encryption_key=Fernet.generate_key().decode("ascii"),
        database_url="sqlite://",
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client
    engine.dispose()


def test_dashboard_requires_login_and_local_htmx_is_served(client: TestClient) -> None:
    assert client.get("/calls", follow_redirects=False).status_code == 303
    assert client.get("/api/calls").status_code == 401

    asset = client.get("/static/vendor/htmx.min.js")
    assert asset.status_code == 200
    assert "htmx" in asset.text.lower()


def test_login_lists_filters_and_displays_encrypted_demo_calls(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        data={"username": "dashboard-owner", "password": "test-only-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/calls"

    dashboard = client.get("/calls")
    assert dashboard.status_code == 200
    assert dashboard.text.count("/calls/demo-call-") == 5

    filtered = client.get("/calls/rows?urgency=high")
    assert filtered.status_code == 200
    assert filtered.text.count("/calls/demo-call-") == 2
    assert "demo-call-2" not in filtered.text

    detail = client.get("/calls/demo-call-1")
    assert detail.status_code == 200
    assert "Краткое содержание" in detail.text
    assert "low-confidence" in detail.text
    assert "пятницы" in detail.text


def test_failed_login_does_not_create_session(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        data={"username": "dashboard-owner", "password": "incorrect-password"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert client.get("/api/calls").status_code == 401


def test_demo_seed_is_idempotent_and_call_content_is_encrypted(client: TestClient) -> None:
    settings = client.app.state.settings
    key = settings.data_encryption_key.get_secret_value()
    with database.SessionLocal() as db_session:
        assert db_session.scalar(select(CallRecord.id).limit(1)) == "demo-call-1"
        assert db_session.scalar(select(AuditEvent.id).limit(1)) is None
        assert seed_demo_calls(db_session, key) == 0
        records = list(db_session.scalars(select(CallRecord)))
        assert len(records) == 5
        assert all("договор" not in (record.summary_enc or "") for record in records)
