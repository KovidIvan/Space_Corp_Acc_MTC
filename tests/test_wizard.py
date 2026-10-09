"""Integration tests for setup, configuration versioning, and call consent."""

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core import db as database
from app.core.config import Settings
from app.core.consent import OWNER_CONSENT_VERSION, has_current_owner_consent
from app.main import create_app
from app.models import AgentConfig as AgentConfigRecord
from app.models import AuditEvent, Consent, TelegramLinkToken, WizardRun


@pytest.fixture
def wizard_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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
        owner_name="wizard-owner",
        owner_company="Synthetic Services",
        owner_password="test-only-password",
        session_secret="test-session-secret-with-enough-entropy",
        data_encryption_key=Fernet.generate_key().decode("ascii"),
        database_url="sqlite://",
    )
    with TestClient(create_app(runtime_settings)) as test_client:
        yield test_client
    engine.dispose()


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        data={"username": "wizard-owner", "password": "test-only-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _config() -> dict[str, object]:
    return {
        "version": 1,
        "owner": {"name": "Demo Owner", "company": "Synthetic Services"},
        "template": "small_business",
        "greeting": "Здравствуйте, чем помочь?",
        "disclosure": "Я ИИ-ассистент, разговор обрабатывается локально.",
        "closing": "Спасибо за звонок.",
        "routing": [
            {"id": "vip-handoff", "priority": 10, "action": "handoff", "when": {"is_vip": True}},
            {"id": "default-message", "priority": 100, "action": "take_message"},
        ],
        "handoff_number": "+375291112233",
        "vip_numbers": ["+375 (29) 123-45-67"],
        "working_hours": {"tz": "Europe/Minsk", "days": [1, 2, 3, 4, 5], "start": "09:00", "end": "18:00"},
        "retention_days": 30,
        "store_audio": False,
        "notice_detail": "minimal",
    }


def test_setup_requires_login_and_renders_five_steps(wizard_client: TestClient) -> None:
    assert wizard_client.get("/setup", follow_redirects=False).status_code == 303
    _login(wizard_client)

    response = wizard_client.get("/setup")
    assert response.status_code == 200
    assert response.text.count('class="wizard-step"') == 5
    assert "wizard-timer" in response.text
    assert "Telegram" in response.text
    assert "Согласие" in response.text
    wizard_script = wizard_client.get("/static/setup_wizard.js")
    assert wizard_script.status_code == 200
    assert "api/wizard/complete" in wizard_script.text

    with database.SessionLocal() as db_session:
        runs = list(db_session.scalars(select(WizardRun)))
        assert len(runs) == 1
        assert runs[0].finished_at is None
        assert runs[0].seconds is None


def test_settings_editor_requires_login_and_loads_saved_scenario(wizard_client: TestClient) -> None:
    assert wizard_client.get("/settings", follow_redirects=False).status_code == 303
    _login(wizard_client)
    wizard_client.get("/setup")
    completed = wizard_client.post(
        "/api/wizard/complete",
        json={"agent_config": _config(), "consent_accepted": True},
    )
    assert completed.status_code == 200

    config = wizard_client.get("/api/config").json()
    config["faq"] = [{"id": "synthetic-hours", "question": "Synthetic hours?", "answer": "Synthetic answer."}]
    config["routing"] = [
        {"id": "vip-priority", "priority": 1, "action": "handoff", "when": {"is_vip": True}},
        {"id": "client-faq", "priority": 20, "action": "answer_faq", "when": {"intent": ["client"]}},
        {"id": "default-message", "priority": 100, "action": "take_message"},
    ]
    config["working_hours"] = {
        "tz": "Europe/Minsk",
        "days": [1, 2, 3, 4, 5],
        "start": "08:30",
        "end": "17:30",
    }
    config["retention_days"] = 14
    config["store_audio"] = True
    saved = wizard_client.put("/api/config", json=config)
    assert saved.status_code == 200
    assert saved.json()["faq"][0]["id"] == "synthetic-hours"
    assert saved.json()["routing"][0]["priority"] == 1
    assert saved.json()["working_hours"]["start"] == "08:30"
    assert saved.json()["retention_days"] == 14
    assert saved.json()["store_audio"] is True
    assert saved.json()["vip_numbers"] == config["vip_numbers"]

    editor = wizard_client.get("/settings")
    assert editor.status_code == 200
    assert "Synthetic hours?" in editor.text
    assert 'id="retention-days"' in editor.text
    assert 'id="store-audio"' in editor.text
    assert 'id="delete-all-calls"' in editor.text
    assert "Уведомление об ИИ и обработке звонка" in editor.text
    assert "+375 (29) 123-45-67" not in editor.text
    assert wizard_client.get("/static/settings_editor.js").status_code == 200


def test_telegram_link_requires_login_and_issues_short_lived_deep_link(wizard_client: TestClient) -> None:
    assert wizard_client.get("/api/wizard/telegram-link").status_code == 401
    _login(wizard_client)

    class TelegramFake:
        async def bot_username(self) -> str:
            return "synthetic_bot"

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    wizard_client.app.state.telegram_channel = TelegramFake()
    response = wizard_client.post("/api/wizard/telegram-link")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["url"].startswith("https://t.me/synthetic_bot?start=")
    raw_token = result["url"].split("start=", 1)[1]
    assert len(raw_token) <= 64
    assert wizard_client.get("/api/wizard/telegram-link").json() == {"enabled": True, "linked": False}

    with database.SessionLocal() as db_session:
        token_rows = list(db_session.scalars(select(TelegramLinkToken)))
        assert len(token_rows) == 1
        assert token_rows[0].token_hash != raw_token


def test_websocket_call_is_rejected_without_current_consent(wizard_client: TestClient) -> None:
    with wizard_client.websocket_connect("/ws/call") as websocket:
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "consent_missing"
        assert "согласия" in error["message"].lower()
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()
    assert disconnected.value.code == 1008


def test_consent_config_timer_and_websocket_guard(
    wizard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login(wizard_client)
    assert wizard_client.get("/setup").status_code == 200
    payload = {"agent_config": _config(), "consent_accepted": False}

    rejected = wizard_client.post("/api/wizard/complete", json=payload)
    assert rejected.status_code == 422
    assert wizard_client.get("/api/config").status_code == 404

    payload["consent_accepted"] = True
    completed = wizard_client.post("/api/wizard/complete", json=payload)
    assert completed.status_code == 200
    completion = completed.json()
    assert completion["config_version"] == 1
    assert completion["seconds"] >= 0
    completion_page = wizard_client.get(completion["redirect_url"])
    assert completion_page.status_code == 200
    assert "голосовой обработчик ещё не подключён" not in completion_page.text
    assert "Открыть симулятор звонка" in completion_page.text
    test_call_script = wizard_client.get("/static/setup_test_call.js")
    assert test_call_script.status_code == 200
    assert 'window.location.assign("/call")' in test_call_script.text
    assert "new WebSocket" not in test_call_script.text

    saved = wizard_client.get("/api/config")
    assert saved.status_code == 200
    config = saved.json()
    assert config["version"] == 1
    assert config["owner"]["company"] == "Synthetic Services"
    assert config["vip_numbers"] != ["+375 (29) 123-45-67"]
    assert len(config["vip_numbers"][0]) == 64
    vip_hash = config["vip_numbers"][0]

    config["greeting"] = "Здравствуйте, чем помочь вашей компании?"
    updated = wizard_client.put("/api/config", json=config)
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["vip_numbers"] == [vip_hash]
    setup_again = wizard_client.get("/setup")
    assert f'value="{vip_hash}"' in setup_again.text
    assert "+375 (29) 123-45-67" not in setup_again.text

    with database.SessionLocal() as db_session:
        assert has_current_owner_consent(db_session)
        consent = db_session.scalar(select(Consent))
        assert consent is not None
        assert consent.text_version == OWNER_CONSENT_VERSION
        assert consent.accepted_at is not None
        run = db_session.scalar(select(WizardRun))
        assert run is not None
        assert run.finished_at is not None
        assert run.seconds is not None
        stored_config = db_session.scalar(
            select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1)
        )
        assert stored_config is not None
        assert stored_config.version == 2
        assert stored_config.config_json["vip_numbers"][0] != "+375 (29) 123-45-67"
        actions = set(db_session.scalars(select(AuditEvent.action)))
        assert {"config_change", "consent"} <= actions

    assert wizard_client.delete("/api/config/1").status_code == 409
    removed_latest = wizard_client.delete("/api/config/2")
    assert removed_latest.status_code == 200
    assert wizard_client.get("/api/config").json()["version"] == 1

    from app.voice.session import CallSession

    session_calls: list[bool] = []

    async def fake_run(session: CallSession) -> None:
        session_calls.append(True)
        await session.websocket.send_text("session-started")
        await session.websocket.close(code=1000)

    monkeypatch.setattr(CallSession, "run", fake_run)
    with wizard_client.websocket_connect("/ws/call") as websocket:
        assert websocket.receive_text() == "session-started"
    assert session_calls == [True]

    assert wizard_client.delete("/api/config/1").status_code == 200
    assert wizard_client.get("/api/config").status_code == 404
    with wizard_client.websocket_connect("/ws/call") as websocket:
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "internal"
        assert "конфигурация ассистента" in error["message"].lower()
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()
    assert disconnected.value.code == 1008
