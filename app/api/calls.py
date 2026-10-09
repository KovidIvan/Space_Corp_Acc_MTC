"""Authenticated call-list and call-detail API endpoints."""

import ipaddress
import json
import logging
from typing import Annotated, Any

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_owner
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.core.security import decrypt_text, encrypt_text
from app.interfaces import Notice
from app.models import CallRecord, ChatThread, Owner
from app.schemas import CallEdit, CallResult

router = APIRouter(prefix="/api/calls", tags=["calls"])
LOGGER = logging.getLogger(__name__)


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


def _require_loopback(request: Request) -> None:
    """Reject CallResult ingestion from clients outside the local machine."""
    client = request.client
    try:
        is_loopback = client is not None and ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local call pipeline required")


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_call_result(
    result: CallResult,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | bool]:
    """Persist a locally produced CallResult and avoid duplicate submissions."""
    _require_loopback(request)
    existing = db.get(CallRecord, result.call_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return {"call_id": existing.id, "created": False}

    encryption_key = request.app.state.settings.data_encryption_key
    if encryption_key is None or not encryption_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Call storage encryption is not configured",
        )

    no_record = result.no_record
    transcript_enc = None
    summary_enc = None
    slots_enc = None
    if not no_record:
        key = encryption_key.get_secret_value()
        transcript_json = json.dumps(
            [segment.model_dump(mode="json", exclude_none=True) for segment in result.transcript],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        slots_json = json.dumps(
            result.slots.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
        )
        transcript_enc = encrypt_text(transcript_json, key)
        summary_enc = encrypt_text(result.summary_ru, key)
        slots_enc = encrypt_text(slots_json, key)
    elif result.slots.callback_number:
        callback_request = json.dumps(
            {"callback_number": result.slots.callback_number},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        slots_enc = encrypt_text(callback_request, encryption_key.get_secret_value())

    call = CallRecord(
        id=result.call_id,
        started_at=result.started_at,
        ended_at=result.ended_at,
        caller_masked=result.caller.masked,
        caller_hash=result.caller.hash,
        status="completed",
        intent=result.intent,
        urgency=result.urgency,
        action=result.action,
        no_record=no_record,
        transcript_enc=transcript_enc,
        summary_enc=summary_enc,
        slots_enc=slots_enc,
    )
    db.add(call)
    record_audit_event(db, "call_pipeline", "call_ingest", result.call_id, {"no_record": no_record})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(CallRecord, result.call_id)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return {"call_id": existing.id, "created": False}

    telegram_channel = request.app.state.telegram_channel
    if telegram_channel is not None:
        try:
            await telegram_channel.notify(
                Notice(
                    call_id=result.call_id,
                    urgency=result.urgency,
                    intent=result.intent,
                    summary="",
                    caller_masked=result.caller.masked,
                )
            )
        except (RuntimeError, SQLAlchemyError):
            LOGGER.warning("Call stored but Telegram notification failed")
    return {"call_id": call.id, "created": True}


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


@router.delete("/all")
def delete_all_calls(
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    """Delete all call records and related chat data while preserving the audit chain."""
    deleted_count = db.scalar(select(func.count()).select_from(CallRecord)) or 0
    db.execute(delete(ChatThread))
    db.execute(delete(CallRecord))
    record_audit_event(db, owner.id, "delete", "calls", {"deleted_count": deleted_count})
    db.commit()
    return {"deleted_calls": deleted_count}


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


@router.patch("/{call_id}")
def edit_call(
    call_id: str,
    update: CallEdit,
    request: Request,
    owner: Annotated[Owner, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Update selected call fields, encrypt private content, and audit changed field names."""
    call = db.get(CallRecord, call_id)
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call.no_record:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Calls marked no_record cannot be edited")

    changes = update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No fields to update")

    encryption_key = request.app.state.settings.data_encryption_key
    if encryption_key is None or not encryption_key.get_secret_value():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Call storage encryption is not configured")

    key = encryption_key.get_secret_value()
    try:
        if "transcript" in changes:
            transcript_json = json.dumps(
                [segment.model_dump(mode="json", exclude_none=True) for segment in update.transcript or []],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            call.transcript_enc = encrypt_text(transcript_json, key)
        if "summary" in changes:
            call.summary_enc = encrypt_text(update.summary or "", key)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid call content") from error

    for field in ("intent", "urgency", "action"):
        if field in changes:
            setattr(call, field, changes[field])
    call.edited = True
    record_audit_event(
        db,
        owner.id,
        "edit",
        call.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    return {"id": call.id, "edited": call.edited, "fields": sorted(changes)}
