"""Tests for privacy, outbound URL, security, configuration, and audit helpers."""

import logging

import httpx
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core.audit import create_audit_event, verify_chain
from app.core.config import Settings
from app.core.logging import PiiMaskFilter, mask_pii
from app.core.safe_http import SafeHttpClient, is_allowed_url, validate_outbound_url
from app.core.security import decrypt_text, encrypt_text, hash_password, verify_password


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
