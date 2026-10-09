"""Authenticated audit log API and hash-chain verification."""

from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_owner
from app.core.audit import record_audit_event, verify_chain
from app.core.db import get_db
from app.models import AuditEvent, Owner

router = APIRouter(prefix="/api/audit", tags=["audit"])


def collect_audit_log(db: Session, limit: int = 100) -> dict[str, Any]:
    """Verify the persisted chain and return the newest events without private payloads."""
    records = list(db.scalars(select(AuditEvent).order_by(AuditEvent.ts, AuditEvent.id)))
    chain_events = []
    for event in records:
        timestamp = event.ts
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        chain_events.append(
            {
                "ts": timestamp,
                "actor": event.actor,
                "action": event.action,
                "target": event.target,
                "details": event.details,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
        )
    return {
        "chain_valid": verify_chain(chain_events),
        "events": [
            {
                "ts": event.ts.isoformat(),
                "actor": event.actor,
                "action": event.action,
                "target": event.target,
                "details": event.details,
                "hash": event.hash,
            }
            for event in reversed(records[-limit:])
        ],
    }


@router.get("")
def get_audit_log(
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Return recent audit events and the integrity status for the complete chain."""
    record_audit_event(db, owner.id, "view", "audit")
    db.flush()
    result = collect_audit_log(db)
    db.commit()
    return result
