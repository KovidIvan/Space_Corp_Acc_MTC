"""Authenticated call-list and call-detail API endpoints."""

import json
from typing import Annotated, Any

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_owner
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.core.security import decrypt_text
from app.models import CallRecord, Owner

router = APIRouter(prefix="/api/calls", tags=["calls"])


def _call_query(
    db: Session,
    urgency: str | None,
    intent: str | None,
    handled: bool | None,
) -> list[CallRecord]:
    query = select(CallRecord)
    if urgency:
        query = query.where(CallRecord.urgency == urgency)
    if intent:
        query = query.where(CallRecord.intent == intent)
    if handled is not None:
        query = query.where(CallRecord.handled.is_(handled))
    return list(db.scalars(query.order_by(CallRecord.started_at.desc()).limit(100)))


@router.get("")
def list_calls(
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
    urgency: Annotated[str | None, Query()] = None,
    intent: Annotated[str | None, Query()] = None,
    handled: Annotated[bool | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Return filtered call summaries without decrypting private content."""
    record_audit_event(db, owner.id, "view", "calls")
    db.commit()
    return [
        {
            "id": call.id,
            "started_at": call.started_at.isoformat(),
            "caller_masked": call.caller_masked,
            "intent": call.intent,
            "urgency": call.urgency,
            "handled": call.handled,
            "edited": call.edited,
        }
        for call in _call_query(db, urgency, intent, handled)
    ]


@router.get("/{call_id}")
def get_call(
    call_id: str,
    request: Request,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Return one call's decrypted transcript and summary to the local owner."""
    call = db.get(CallRecord, call_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    encryption_key = request.app.state.settings.data_encryption_key
    if encryption_key is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Dashboard is not configured")

    try:
        transcript = json.loads(decrypt_text(call.transcript_enc, encryption_key.get_secret_value())) if call.transcript_enc else []
        summary = decrypt_text(call.summary_enc, encryption_key.get_secret_value()) if call.summary_enc else ""
    except (InvalidToken, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Call data could not be read") from error

    record_audit_event(db, owner.id, "view", call.id)
    db.commit()
    return {
        "id": call.id,
        "started_at": call.started_at.isoformat(),
        "caller_masked": call.caller_masked,
        "intent": call.intent,
        "urgency": call.urgency,
        "handled": call.handled,
        "edited": call.edited,
        "transcript": transcript,
        "summary": summary,
    }
