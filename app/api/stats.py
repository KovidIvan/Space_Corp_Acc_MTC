"""Authenticated call statistics API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_owner
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.models import CallRecord, Owner

router = APIRouter(prefix="/api/stats", tags=["stats"])
ESTIMATED_MINUTES_SAVED_PER_HANDLED_CALL = 5


def collect_call_stats(db: Session) -> dict[str, Any]:
    """Aggregate counts from call metadata without decrypting private fields."""
    total = db.scalar(select(func.count()).select_from(CallRecord)) or 0
    handled = db.scalar(
        select(func.count()).select_from(CallRecord).where(CallRecord.handled.is_(True))
    ) or 0
    by_intent = db.execute(
        select(CallRecord.intent, func.count())
        .group_by(CallRecord.intent)
        .order_by(CallRecord.intent)
    ).all()
    by_urgency = db.execute(
        select(CallRecord.urgency, func.count())
        .group_by(CallRecord.urgency)
        .order_by(CallRecord.urgency)
    ).all()
    return {
        "calls": total,
        "by_intent": [{"key": key or "unknown", "count": count} for key, count in by_intent],
        "by_urgency": [
            {"key": key or "unknown", "count": count} for key, count in by_urgency
        ],
        "handled": handled,
        "unhandled": total - handled,
        "estimated_minutes_saved": handled * ESTIMATED_MINUTES_SAVED_PER_HANDLED_CALL,
    }


@router.get("")
def get_call_stats(
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Return aggregate call statistics for the signed-in owner."""
    stats = collect_call_stats(db)
    record_audit_event(db, owner.id, "view", "stats")
    db.commit()
    return stats
