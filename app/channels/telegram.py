"""Telegram Bot API access and secure owner-link token helpers."""

import asyncio
import hashlib
import logging
import re
import secrets
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.safe_http import SafeHttpClient
from app.interfaces import Notice
from app.models import CallRecord, TelegramLink, TelegramLinkToken

LINK_TOKEN_TTL = timedelta(minutes=10)
BOT_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")
MASKED_CALLER_PATTERN = re.compile(r"^[+\d*() .-]{4,40}$")
LOGGER = logging.getLogger(__name__)


class TelegramApiError(RuntimeError):
    """A Telegram Bot API request failed without exposing its credentials."""


class TelegramBotApi:
    """Small Telegram Bot API client restricted by the shared outbound allowlist."""

    def __init__(self, token: str, http: SafeHttpClient | None = None) -> None:
        self._token = token
        self._http = http or SafeHttpClient()

    async def call(
        self,
        method: str,
        payload: dict[str, object] | None = None,
        *,
        timeout: float = 10.0,
    ) -> dict[str, object] | list[object]:
        """Call one Bot API method and return its result object."""
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        try:
            response = await self._http.request("POST", url, json=payload or {}, timeout=timeout)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            raise TelegramApiError("Telegram API request failed") from None
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise TelegramApiError("Telegram API rejected the request")
        result = body.get("result")
        return result if isinstance(result, (dict, list)) else {}

    async def bot_username(self) -> str:
        """Return the configured bot username after validating Telegram's response."""
        result = await self.call("getMe")
        if not isinstance(result, dict):
            raise TelegramApiError("Telegram bot identity is unavailable")
        username = result.get("username")
        if not isinstance(username, str) or not BOT_USERNAME_PATTERN.fullmatch(username):
            raise TelegramApiError("Telegram bot identity is unavailable")
        return username

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, object] | None = None,
    ) -> None:
        """Send a Telegram message with optional inline keyboard markup."""
        payload: dict[str, object] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self.call("sendMessage", payload)

    async def get_updates(self, offset: int, timeout: int = 20) -> list[dict[str, object]]:
        """Long-poll updates; the HTTP deadline exceeds Telegram's poll timeout."""
        result = await self.call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]},
            timeout=timeout + 15.0,
        )
        return result if isinstance(result, list) else []

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        """Acknowledge a Telegram inline-button callback."""
        await self.call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

    async def close(self) -> None:
        """Close the underlying safe HTTP client."""
        await self._http.aclose()


class TelegramChannel:
    """Telegram integration entry point; all Bot API traffic uses SafeHttpClient."""

    def __init__(
        self,
        token: str,
        http: SafeHttpClient | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.bot = TelegramBotApi(token, http)
        self._session_factory = session_factory
        self._poll_task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def bot_username(self) -> str:
        """Return the username used to build an owner-link deep link."""
        return await self.bot.bot_username()

    async def notify(self, notice: Notice) -> None:
        """Send a minimal masked call notice to every linked private owner chat."""
        if self._session_factory is None:
            return
        with self._session_factory() as db:
            chat_ids = list(db.scalars(select(TelegramLink.chat_id)))
        caller = _safe_masked_caller(notice.caller_masked)
        urgency = notice.urgency if notice.urgency in {"low", "normal", "high"} else "не указана"
        valid_intents = {
            "client",
            "partner",
            "vendor_sales",
            "spam",
            "job_candidate",
            "other",
            "unclear",
        }
        intent = notice.intent if notice.intent in valid_intents else "не указан"
        text = f"Новый звонок\nТип: {intent}\nСрочность: {urgency}\nНомер: {caller}"
        keyboard = {
            "inline_keyboard": [
                [{"text": "Отметить обработанным", "callback_data": f"handled:{notice.call_id}"}]
            ]
        }
        for chat_id in chat_ids:
            try:
                await self.bot.send_message(chat_id, text, keyboard)
            except TelegramApiError:
                LOGGER.warning("Telegram notice delivery failed")

    async def start(self) -> None:
        """Start the long-polling update handler without blocking application startup."""
        if self._session_factory is not None and self._poll_task is None:
            self._stopping.clear()
            self._poll_task = asyncio.create_task(self._poll_updates())

    async def stop(self) -> None:
        """Stop long polling and close its safe HTTP transport."""
        self._stopping.set()
        if self._poll_task is not None:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        await self.bot.close()

    async def _poll_updates(self) -> None:
        offset = 0
        while not self._stopping.is_set():
            try:
                updates = await self.bot.get_updates(offset)
                for update in updates:
                    if not isinstance(update, dict):
                        continue
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = max(offset, update_id + 1)
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except TelegramApiError:
                LOGGER.warning("Telegram update polling failed")
                await asyncio.sleep(3)
            except (SQLAlchemyError, TypeError, ValueError, RuntimeError):
                LOGGER.warning("Telegram update processing failed")
                await asyncio.sleep(3)

    async def _handle_update(self, update: dict[str, object]) -> None:
        if self._session_factory is None:
            return
        message = update.get("message")
        if isinstance(message, dict):
            await self._handle_message(message)
            return
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            await self._handle_callback(callback)

    async def _handle_message(self, message: dict[str, object]) -> None:
        chat = message.get("chat")
        text = message.get("text")
        if not isinstance(chat, dict) or chat.get("type") != "private" or not isinstance(text, str):
            return
        start = re.fullmatch(r"/start(?:@\w+)?(?:\s+([A-Za-z0-9_-]{1,64}))?", text.strip())
        if not start:
            return
        chat_id = str(chat.get("id", ""))
        token = start.group(1) or ""
        if not chat_id:
            return
        with self._session_factory() as db:
            linked = consume_link_token(db, token, chat_id)
        reply = "Telegram подключён. Уведомления будут приходить сюда." if linked else "Ссылка недействительна или устарела. Создайте новую в настройках."
        try:
            await self.bot.send_message(chat_id, reply)
        except TelegramApiError:
            LOGGER.warning("Telegram link confirmation failed")

    async def _handle_callback(self, callback: dict[str, object]) -> None:
        callback_id = callback.get("id")
        data = callback.get("data")
        user = callback.get("from")
        message = callback.get("message")
        chat = message.get("chat") if isinstance(message, dict) else None
        status = "unauthorized"
        if (
            isinstance(data, str)
            and isinstance(user, dict)
            and isinstance(chat, dict)
            and chat.get("type") == "private"
            and str(user.get("id", "")) == str(chat.get("id", ""))
        ):
            match = re.fullmatch(r"handled:([A-Za-z0-9_-]{1,64})", data)
            if match and self._session_factory is not None:
                with self._session_factory() as db:
                    status = mark_call_handled(db, str(chat.get("id", "")), match.group(1))
        if isinstance(callback_id, str):
            try:
                answer = {
                    "handled": "Обращение отмечено как обработанное.",
                    "already_handled": "Обращение уже обработано.",
                    "not_found": "Звонок не найден.",
                }.get(status, "У вас нет доступа к этому действию.")
                await self.bot.answer_callback(callback_id, answer)
            except TelegramApiError:
                LOGGER.warning("Telegram callback acknowledgement failed")

    async def close(self) -> None:
        """Close the Telegram Bot API transport."""
        await self.bot.close()


def _safe_masked_caller(caller: str | None) -> str:
    if not caller or not MASKED_CALLER_PATTERN.fullmatch(caller) or "*" not in caller:
        return "скрыт"
    if sum(character.isdigit() for character in caller) > 6:
        return "скрыт"
    return caller


def create_link_token(db: Session, owner_id: str) -> tuple[str, datetime]:
    """Create a short-lived single-use token and persist only its SHA-256 digest."""
    now = datetime.now(UTC)
    db.execute(
        delete(TelegramLinkToken).where(
            TelegramLinkToken.owner_id == owner_id,
            TelegramLinkToken.consumed_at.is_(None),
        )
    )
    token = secrets.token_urlsafe(32)
    expires_at = now + LINK_TOKEN_TTL
    db.add(
        TelegramLinkToken(
            token_hash=hashlib.sha256(token.encode("ascii")).hexdigest(),
            owner_id=owner_id,
            created_at=now,
            expires_at=expires_at,
        )
    )
    return token, expires_at


def consume_link_token(db: Session, token: str, chat_id: str) -> bool:
    """Consume a valid owner-link token once and persist its private Telegram chat."""
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", token):
        return False
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    link_token = db.get(TelegramLinkToken, token_hash)
    if link_token is None or link_token.consumed_at is not None:
        return False
    expires_at = link_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if expires_at <= now:
        return False

    link_token.consumed_at = now
    link = db.get(TelegramLink, chat_id)
    if link is None:
        db.add(TelegramLink(chat_id=chat_id, linked_at=now))
    else:
        link.linked_at = now
    record_audit_event(db, link_token.owner_id, "telegram_link", "telegram", {"linked": True})
    db.commit()
    return True


def is_linked_chat(db: Session, chat_id: str) -> bool:
    """Return whether a Telegram chat is linked to the local owner."""
    return db.scalar(select(TelegramLink.chat_id).where(TelegramLink.chat_id == chat_id)) is not None


def mark_call_handled(db: Session, chat_id: str, call_id: str) -> str:
    """Mark a call handled only when the callback comes from a linked chat."""
    if not is_linked_chat(db, chat_id):
        return "unauthorized"
    call = db.get(CallRecord, call_id)
    if call is None:
        return "not_found"
    if call.handled:
        return "already_handled"

    call.handled = True
    record_audit_event(db, "telegram_owner", "handled", call.id, {"source": "telegram"})
    db.commit()
    return "handled"
