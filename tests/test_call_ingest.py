"""Integration tests for the local CallResult ingestion endpoint."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import db as database
from app.core.config import Settings
from app.core.security import decrypt_text
from app.interfaces import Notice
from app.main import create_app
from app.models import AuditEvent, CallRecord


@pytest.fixture
def ingest_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    runtime_settings = Settings(
        _env_file=None,
        owner_name="ingest-owner",
        owner_company="Synthetic Company",
        owner_password="test-only-password",
        session_secret="test-session-secret-with-enough-entropy",
        data_encryption_key=Fernet.generate_key().decode("ascii"),
        database_url="sqlite://",
    )
    with TestClient(create_app(runtime_settings), client=("127.0.0.1", 51000)) as test_client:
        yield test_client
    engine.dispose()


def _call_result(call_id: str = "ingest-call-001", *, no_record: bool = False) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "started_at": "2026-10-06T12:00:00Z",
        "ended_at": "2026-10-06T12:00:12Z",
        "duration_s": 12.0,
        "caller": {"masked": "+7 *** ***-12-34", "hash": "synthetic-hmac", "is_vip": False},
        "transcript": [
            {
                "who": "caller",
                "text": "Synthetic private transcript",
                "words": [{"w": "Synthetic", "p": 0.98}],
            },
            {"who": "agent", "text": "Synthetic reply"},
        ],
        "intent": "client",
        "urgency": "high",
        "slots": {"name": "Synthetic Person", "reason": "Synthetic request", "callback_number": "+375291234567"},
        "summary_ru": "Synthetic private summary",
        "action": "take_message",
        "no_record": no_record,
    }


def test_ingest_encrypts_call_content_and_audits_without_dashboard_login(ingest_client: TestClient) -> None:
    payload = _call_result()
    response = ingest_client.post("/api/calls/ingest", json=payload)

    assert response.status_code == 201
    assert response.json() == {"call_id": "ingest-call-001", "created": True}
    assert ingest_client.get("/api/calls/ingest-call-001").status_code == 401

    key = ingest_client.app.state.settings.data_encryption_key.get_secret_value()
    with database.SessionLocal() as db:
        call = db.get(CallRecord, "ingest-call-001")
        assert call is not None
        assert call.caller_masked == "+7 *** ***-12-34"
        assert call.caller_hash == "synthetic-hmac"
        assert call.urgency == "high"
        assert call.transcript_enc is not None and "Synthetic private transcript" not in call.transcript_enc
        assert call.summary_enc is not None and "Synthetic private summary" not in call.summary_enc
        assert call.slots_enc is not None and "Synthetic Person" not in call.slots_enc
        assert "Synthetic private transcript" in decrypt_text(call.transcript_enc, key)
        assert "Synthetic private summary" == decrypt_text(call.summary_enc, key)
        assert "Synthetic Person" in decrypt_text(call.slots_enc, key)
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "call_ingest"))
        assert event is not None and event.target == call.id
        assert event.details == {"no_record": False}


def test_no_record_ingest_keeps_metadata_and_only_encrypted_callback_request(
    ingest_client: TestClient,
) -> None:
    payload = _call_result("no-record-call", no_record=True)
    response = ingest_client.post("/api/calls/ingest", json=payload)

    assert response.status_code == 201
    with database.SessionLocal() as db:
        call = db.get(CallRecord, "no-record-call")
        assert call is not None
        assert call.no_record is True
        assert call.caller_masked == "+7 *** ***-12-34"
        assert call.caller_hash == "synthetic-hmac"
        assert call.transcript_enc is None
        assert call.summary_enc is None


def test_no_record_call_cannot_be_edited(ingest_client: TestClient) -> None:
    response = ingest_client.post("/api/calls/ingest", json=_call_result("no-record-edit", no_record=True))
    assert response.status_code == 201

    ingest_client.post(
        "/api/auth/login",
        data={"username": "ingest-owner", "password": "test-only-password"},
        follow_redirects=False,
    )
    edit_response = ingest_client.patch("/api/calls/no-record-edit", json={"summary": "Do not save"})

    assert edit_response.status_code == 409
    with database.SessionLocal() as db:
        call = db.get(CallRecord, "no-record-edit")
        assert call is not None and call.no_record and call.summary_enc is None
        assert call.slots_enc is not None
        assert "+375291234567" not in call.slots_enc
        stored_slots = json.loads(
            decrypt_text(call.slots_enc, ingest_client.app.state.settings.data_encryption_key.get_secret_value())
        )
        assert stored_slots == {"callback_number": "+375291234567"}


def test_no_record_without_callback_request_stores_no_slots(ingest_client: TestClient) -> None:
    payload = _call_result("no-callback-call", no_record=True)
    payload["slots"]["callback_number"] = None

    response = ingest_client.post("/api/calls/ingest", json=payload)

    assert response.status_code == 201
    with database.SessionLocal() as db:
        call = db.get(CallRecord, "no-callback-call")
        assert call is not None
        assert call.transcript_enc is None
        assert call.summary_enc is None
        assert call.slots_enc is None


def test_duplicate_call_result_is_idempotent(ingest_client: TestClient) -> None:
    payload = _call_result("duplicate-call")

    first = ingest_client.post("/api/calls/ingest", json=payload)
    duplicate = ingest_client.post("/api/calls/ingest", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json() == {"call_id": "duplicate-call", "created": False}
    with database.SessionLocal() as db:
        calls = list(db.scalars(select(CallRecord).where(CallRecord.id == "duplicate-call")))
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.action == "call_ingest")))
        assert len(calls) == 1
        assert len(events) == 1


def test_ingest_notifies_only_after_commit_with_minimal_notice(ingest_client: TestClient) -> None:
    class RecordingChannel:
        def __init__(self) -> None:
            self.notices: list[Notice] = []
            self.call_was_committed = False

        async def notify(self, notice: Notice) -> None:
            with database.SessionLocal() as db:
                self.call_was_committed = db.get(CallRecord, notice.call_id) is not None
            self.notices.append(notice)

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    channel = RecordingChannel()
    ingest_client.app.state.telegram_channel = channel

    response = ingest_client.post("/api/calls/ingest", json=_call_result("notice-call"))

    assert response.status_code == 201
    assert channel.call_was_committed is True
    assert len(channel.notices) == 1
    assert channel.notices[0].call_id == "notice-call"
    assert channel.notices[0].caller_masked == "+7 *** ***-12-34"
    assert channel.notices[0].summary == ""


def test_duplicate_ingest_does_not_send_duplicate_notice(ingest_client: TestClient) -> None:
    class RecordingChannel:
        def __init__(self) -> None:
            self.notices: list[Notice] = []

        async def notify(self, notice: Notice) -> None:
            self.notices.append(notice)

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    channel = RecordingChannel()
    ingest_client.app.state.telegram_channel = channel
    payload = _call_result("single-notice-call")

    assert ingest_client.post("/api/calls/ingest", json=payload).status_code == 201
    assert ingest_client.post("/api/calls/ingest", json=payload).status_code == 200
    assert len(channel.notices) == 1


def test_notification_failure_does_not_undo_saved_call(ingest_client: TestClient) -> None:
    class FailingChannel:
        async def notify(self, notice: Notice) -> None:
            raise RuntimeError("synthetic notification failure")

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    ingest_client.app.state.telegram_channel = FailingChannel()

    response = ingest_client.post("/api/calls/ingest", json=_call_result("saved-before-notice"))

    assert response.status_code == 201
    with database.SessionLocal() as db:
        assert db.get(CallRecord, "saved-before-notice") is not None


def test_ingest_rejects_non_loopback_clients(ingest_client: TestClient) -> None:
    remote_client = TestClient(ingest_client.app, client=("192.0.2.10", 51000))

    response = remote_client.post("/api/calls/ingest", json=_call_result("remote-call"))

    assert response.status_code == 403
    with database.SessionLocal() as db:
        assert db.get(CallRecord, "remote-call") is None


def test_ingest_validates_call_result_contract(ingest_client: TestClient) -> None:
    payload = _call_result("invalid-call")
    payload["urgency"] = "critical"

    response = ingest_client.post("/api/calls/ingest", json=payload)

    assert response.status_code == 422
    with database.SessionLocal() as db:
        assert db.get(CallRecord, "invalid-call") is None
