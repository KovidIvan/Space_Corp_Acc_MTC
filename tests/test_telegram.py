"""Unit tests for safe Telegram API access and owner-chat linking tokens."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.channels.telegram import (
    TelegramApiError,
    TelegramBotApi,
    TelegramChannel,
    consume_link_token,
    create_link_token,
    mark_call_handled,
)
from app.core.db import Base
from app.core.safe_http import SafeHttpClient
from app.interfaces import Notice
from app.models import AuditEvent, CallRecord, Owner, TelegramLink, TelegramLinkToken


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        db.add(Owner(id="owner-1", name="Synthetic Owner", company="Synthetic Co", password_hash="hash"))
        db.commit()
    return factory


def test_owner_link_token_is_hashed_expires_and_can_only_be_consumed_once() -> None:
    factory = _session_factory()
    with factory() as db:
        token, expires_at = create_link_token(db, "owner-1")
        db.commit()
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()

        stored = db.get(TelegramLinkToken, token_hash)
        assert stored is not None
        assert stored.expires_at.replace(tzinfo=UTC) == expires_at
        assert stored.token_hash != token
        assert consume_link_token(db, token, "123456") is True
        assert consume_link_token(db, token, "123456") is False
        assert db.get(TelegramLink, "123456") is not None


def test_expired_or_malformed_owner_link_tokens_are_rejected() -> None:
    factory = _session_factory()
    with factory() as db:
        token, _ = create_link_token(db, "owner-1")
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        db.flush()
        stored = db.get(TelegramLinkToken, token_hash)
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        assert consume_link_token(db, token, "123456") is False
        assert consume_link_token(db, "not a valid token", "123456") is False
        assert db.get(TelegramLink, "123456") is None


def test_telegram_bot_api_uses_allowlisted_host_and_validates_username() -> None:
    requested_urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True, "result": {"username": "synthetic_bot"}})

    async def run() -> str:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        bot = TelegramBotApi("test-token", http=SafeHttpClient(client))
        username = await bot.bot_username()
        await bot.close()
        return username

    assert asyncio.run(run()) == "synthetic_bot"
    assert len(requested_urls) == 1
    assert requested_urls[0].startswith("https://api.telegram.org/bottest-token/getMe")


def test_telegram_api_errors_do_not_disclose_bot_token() -> None:
    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="failure")

    async def run() -> str:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        bot = TelegramBotApi("secret-test-token", http=SafeHttpClient(client))
        try:
            await bot.bot_username()
        except TelegramApiError as error:
            return str(error)
        finally:
            await bot.close()
        raise AssertionError("Expected TelegramApiError")

    assert "secret-test-token" not in asyncio.run(run())


def test_notice_is_minimal_masked_and_includes_mark_handled_button() -> None:
    factory = _session_factory()
    with factory() as db:
        db.add(TelegramLink(chat_id="123456"))
        db.commit()
    sent_payloads: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        import json

        sent_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        channel = TelegramChannel("test-token", SafeHttpClient(client), factory)
        await channel.notify(
            Notice(
                call_id="call-123",
                urgency="high",
                intent="client",
                summary="Full private caller summary",
                caller_masked="+7 *** ***-12-34",
            )
        )
        await channel.close()

    asyncio.run(run())

    assert len(sent_payloads) == 1
    payload = sent_payloads[0]
    assert payload["chat_id"] == "123456"
    assert payload["text"] == "Новый звонок\nТип: client\nСрочность: high\nНомер: +7 *** ***-12-34"
    assert "Full private caller summary" not in str(payload)
    assert payload["reply_markup"] == {
        "inline_keyboard": [[{"text": "Отметить обработанным", "callback_data": "handled:call-123"}]]
    }


def test_notice_does_not_forward_an_unmasked_caller_number() -> None:
    factory = _session_factory()
    with factory() as db:
        db.add(TelegramLink(chat_id="123456"))
        db.commit()
    sent_texts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        import json

        sent_texts.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        channel = TelegramChannel("test-token", SafeHttpClient(client), factory)
        await channel.notify(Notice("call-1", "normal", "partner", "+375291234567", "+375291234567"))
        await channel.close()

    asyncio.run(run())
    assert len(sent_texts) == 1
    assert "+375291234567" not in sent_texts[0]
    assert "Номер: скрыт" in sent_texts[0]


def test_mark_handled_requires_linked_chat_and_audits_once() -> None:
    factory = _session_factory()
    with factory() as db:
        db.add(TelegramLink(chat_id="linked-chat"))
        db.add(CallRecord(id="call-1", started_at=datetime.now(UTC), status="completed"))
        db.commit()

        assert mark_call_handled(db, "unlinked-chat", "call-1") == "unauthorized"
        call = db.get(CallRecord, "call-1")
        assert call is not None and call.handled is False
        assert mark_call_handled(db, "linked-chat", "missing-call") == "not_found"
        assert mark_call_handled(db, "linked-chat", "call-1") == "handled"
        assert mark_call_handled(db, "linked-chat", "call-1") == "already_handled"
        events = list(db.scalars(select(AuditEvent)))
        assert len(events) == 1
        assert events[0].actor == "telegram_owner"
        assert events[0].action == "handled"


def test_bot_updates_link_owner_and_handle_callback() -> None:
    factory = _session_factory()
    with factory() as db:
        token, _ = create_link_token(db, "owner-1")
        db.add(CallRecord(id="call-2", started_at=datetime.now(UTC), status="completed"))
        db.commit()

    sent_messages: list[tuple[str, str]] = []
    callback_answers: list[tuple[str, str]] = []

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
        channel = TelegramChannel("test-token", SafeHttpClient(http_client), factory)

        async def send_message(chat_id: str, text: str, reply_markup: dict[str, object] | None = None) -> None:
            sent_messages.append((chat_id, text))

        async def answer_callback(callback_query_id: str, text: str) -> None:
            callback_answers.append((callback_query_id, text))

        channel.bot.send_message = send_message
        channel.bot.answer_callback = answer_callback
        await channel._handle_update(
            {
                "message": {
                    "chat": {"id": 123456, "type": "private"},
                    "text": f"/start {token}",
                }
            }
        )
        await channel._handle_update(
            {
                "callback_query": {
                    "id": "callback-1",
                    "from": {"id": 123456},
                    "message": {"chat": {"id": 123456, "type": "private"}},
                    "data": "handled:call-2",
                }
            }
        )
        await channel._handle_update(
            {
                "callback_query": {
                    "id": "callback-2",
                    "from": {"id": 654321},
                    "message": {"chat": {"id": 123456, "type": "private"}},
                    "data": "handled:call-2",
                }
            }
        )
        await channel.close()

    asyncio.run(run())

    assert sent_messages == [("123456", "Telegram подключён. Уведомления будут приходить сюда.")]
    assert callback_answers == [
        ("callback-1", "Обращение отмечено как обработанное."),
        ("callback-2", "У вас нет доступа к этому действию."),
    ]
    with factory() as db:
        linked_call = db.get(CallRecord, "call-2")
        assert linked_call is not None and linked_call.handled is True


def test_notice_delivery_failure_is_nonfatal_and_does_not_log_bot_token(caplog) -> None:
    factory = _session_factory()
    with factory() as db:
        db.add(TelegramLink(chat_id="123456"))
        db.commit()

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="failed")

    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        channel = TelegramChannel("secret-test-token", SafeHttpClient(client), factory)
        await channel.notify(Notice("call-1", "high", "client", "private details", "+7 *** ***-12-34"))
        await channel.close()

    asyncio.run(run())
    assert "Telegram notice delivery failed" in caplog.text
    assert "secret-test-token" not in caplog.text
    assert "private details" not in caplog.text
