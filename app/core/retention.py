"""Retention cleanup for expired call records."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.models import AgentConfig, CallRecord, ChatThread

DEFAULT_RETENTION_DAYS = 30


def retention_days(db: Session) -> int:
    """Read the current retention policy, falling back safely to 30 days."""
    config = db.scalar(select(AgentConfig).order_by(AgentConfig.version.desc()).limit(1))
    try:
        days = int(config.config_json.get("retention_days", DEFAULT_RETENTION_DAYS)) if config else DEFAULT_RETENTION_DAYS
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
    return max(days, 0)


def delete_expired_calls(db: Session, now: datetime | None = None) -> int:
    """Delete calls older than the active policy and append a non-sensitive audit entry."""
    days = retention_days(db)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    expired_ids = list(
        db.scalars(select(CallRecord.id).where(CallRecord.ended_at.is_not(None), CallRecord.ended_at < cutoff))
    )
    if not expired_ids:
        return 0

    db.execute(delete(ChatThread).where(ChatThread.call_id.in_(expired_ids)))
    db.execute(delete(CallRecord).where(CallRecord.id.in_(expired_ids)))
    record_audit_event(
        db,
        "retention_job",
        "retention_delete",
        "calls",
        {"deleted_count": len(expired_ids), "retention_days": days},
    )
    db.commit()
    return len(expired_ids)
