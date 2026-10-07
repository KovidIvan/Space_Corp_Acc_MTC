"""Tests for privacy, outbound URL, security, configuration, and audit helpers."""

import logging
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from uvicorn.logging import AccessFormatter

from app.core import db as database
from app.core.audit import create_audit_event, verify_chain
from app.core.bootstrap import ensure_owner_account
from app.core.config import Settings
from app.core.logging import PiiMaskFilter, mask_pii
from app.core.safe_http import SafeHttpClient, is_allowed_url, validate_outbound_url
from app.core.security import decrypt_text, encrypt_text, hash_password, verify_password
from app.models import Owner


def test_mask_pii_covers_phone_email_and_long_digit_runs() -> None:
    text = "Телефон +7 (999) 123-45-67, email ivan@example.com, код 1234567890"
    masked = mask_pii(text)

    assert "+7 (999) 123-45-67" not in masked
    assert "ivan@example.com" not in masked
    assert "1234567890" not in masked
    assert "[PHONE]" in masked
    assert "[EMAIL]" in masked
    assert "[DIGITS]" in masked


def test_pii_log_filter_renders_and_masks_format_arguments() -> None:
    record = logging.LogRecord("test", logging.INFO, "test.py", 1, "caller=%s", ("+79991234567",), None)

    assert PiiMaskFilter().filter(record)
    assert "+79991234567" not in record.getMessage()


def test_pii_log_filter_preserves_uvicorn_access_formatter_arguments() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "uvicorn/protocols/http/h11_impl.py",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("+7 (000) 123-45-67", "GET", "/call?email=synthetic@example.test", "1.1", 200),
        None,
    )

    assert PiiMaskFilter().filter(record)
    rendered = AccessFormatter(
        '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        use_colors=False,
    ).format(record)

    assert "+7 (000) 123-45-67" not in rendered
    assert "synthetic@example.test" not in rendered
    assert "[PHONE]" in rendered
    assert "[EMAIL]" in rendered
    assert record.msg == '%s - "%s %s HTTP/%s" %d'
    assert len(record.args) == 5


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/api",
        "http://127.0.0.1:8000/health",
        "http://[::1]:8000/health",
        "https://api.telegram.org/botTOKEN/sendMessage",
    ],
)
def test_allowlisted_urls(url: str) -> None:
    assert is_allowed_url(url)
    assert validate_outbound_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://api.telegram.org/botTOKEN/sendMessage",
        "https://api.telegram.org.evil.example/",
        "file:///etc/passwd",
        "http://127.0.0.1.evil.example/",
        "http://user:password@localhost/",
    ],
)
def test_non_allowlisted_urls(url: str) -> None:
    assert not is_allowed_url(url)
    with pytest.raises(ValueError):
        validate_outbound_url(url)


@pytest.mark.asyncio
async def test_safe_http_client_does_not_follow_redirects_to_nonallowlisted_host() -> None:
    requested_hosts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return httpx.Response(302, headers={"Location": "https://example.com/"}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=True)
    safe_client = SafeHttpClient(client)
    response = await safe_client.request("GET", "http://localhost/start")
    await safe_client.aclose()

    assert response.status_code == 302
    assert requested_hosts == ["localhost"]


def test_fernet_text_round_trip_and_invalid_key() -> None:
    key = Fernet.generate_key()
    token = encrypt_text("синтетический текст", key)

    assert decrypt_text(token, key) == "синтетический текст"
    with pytest.raises(InvalidToken):
        decrypt_text(token, Fernet.generate_key())


def test_password_hashing() -> None:
    password_hash = hash_password("synthetic-password")

    assert verify_password("synthetic-password", password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password("anything", "not-a-valid-hash")


def test_settings_profile_and_defaults() -> None:
    settings = Settings(_env_file=None, profile="gpu_mid", offline_mode=False)

    assert settings.profile == "gpu_mid"
    assert settings.offline_mode is False
    assert settings.max_concurrent_calls == 1


def test_settings_load_dotenv_from_project_root_independent_of_working_directory() -> None:
    expected_env_file = Path(__file__).resolve().parents[1] / ".env"

    assert Settings.model_config["env_file"] == expected_env_file


def test_relative_sqlite_database_is_shared_across_working_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    first_cwd = tmp_path / "first-cwd"
    second_cwd = tmp_path / "second-cwd"
    first_cwd.mkdir()
    second_cwd.mkdir()
    monkeypatch.setattr(database, "PROJECT_ROOT", project_root)
    runtime_settings = Settings(
        _env_file=None,
        owner_name="synthetic-owner",
        owner_company="Synthetic Company",
        owner_password="synthetic-test-password",
    )

    monkeypatch.chdir(first_cwd)
    first_engine = database._create_engine("sqlite:///./data/accounts.db")
    database.init_db(first_engine)
    with sessionmaker(bind=first_engine)() as db_session:
        first_owner = ensure_owner_account(db_session, runtime_settings)
        owner_id = first_owner.id

    monkeypatch.chdir(second_cwd)
    second_engine = database._create_engine("sqlite:///./data/accounts.db")
    with sessionmaker(bind=second_engine)() as db_session:
        second_owner = db_session.scalar(select(Owner).where(Owner.id == owner_id))

    assert first_engine.url.database == second_engine.url.database
    assert Path(first_engine.url.database) == project_root / "data" / "accounts.db"
    assert second_owner is not None
    assert second_owner.name == runtime_settings.owner_name
    assert verify_password("synthetic-test-password", second_owner.password_hash)
    first_engine.dispose()
    second_engine.dispose()


def test_settings_parse_dotenv_values_without_exposing_them(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OWNER_NAME=Test Owner\n"
        "OWNER_COMPANY=Test Company\n"
        "OWNER_PASSWORD=synthetic-password\n"
        "SESSION_SECRET=synthetic-session-secret\n"
        "DATA_ENCRYPTION_KEY=synthetic-encryption-key\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.dashboard_configured


def test_audit_hash_chain_detects_tampering_and_link_breaks() -> None:
    first = create_audit_event({"actor": "owner", "action": "view", "target": "call-1"})
    second = create_audit_event(
        {"actor": "owner", "action": "edit", "target": "call-1", "details": {"field": "summary"}},
        first["hash"],
    )

    assert verify_chain([first, second])
    assert verify_chain([])

    tampered = [first, {**second, "details": {"field": "transcript"}}]
    broken_link = [first, {**second, "prev_hash": "0" * 64}]
    assert not verify_chain(tampered)
    assert not verify_chain(broken_link)
