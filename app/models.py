"""SQLAlchemy models for the local call assistant."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Owner(Base):
    """Business owner account."""

    __tablename__ = "owner"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class AgentConfig(Base):
    """Versioned assistant configuration document."""

    __tablename__ = "agent_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column("json", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class Consent(Base):
    """Owner consent record."""

    __tablename__ = "consent"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    text_version: Mapped[str] = mapped_column(String(100), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CallRecord(Base):
    """Call metadata and encrypted fields."""

    __tablename__ = "call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    caller_masked: Mapped[str | None] = mapped_column(String(100))
    caller_hash: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50))
    urgency: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str | None] = mapped_column(String(50))
    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    no_record: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transcript_enc: Mapped[str | None] = mapped_column(Text)
    summary_enc: Mapped[str | None] = mapped_column(Text)
    slots_enc: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    """Single event in the tamper-evident audit chain."""

    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class TelegramLink(Base):
    """Linked Telegram chat identifier."""

    __tablename__ = "telegram_link"

    chat_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class ChatThread(Base):
    """Encrypted text relay associated with a call."""

    __tablename__ = "chat_thread"

    call_id: Mapped[str] = mapped_column(ForeignKey("call.id"), primary_key=True)
    messages_enc: Mapped[str] = mapped_column(Text, nullable=False)
    call: Mapped[CallRecord] = relationship()


class WizardRun(Base):
    """Setup wizard duration record."""

    __tablename__ = "wizard_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seconds: Mapped[float | None] = mapped_column(Float)
